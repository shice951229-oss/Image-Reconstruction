#!/usr/bin/env python3
"""Local-first optional VAE / low-strength Diffusion preprocessing branch for Image-Reconstruction.

Pipeline position:
  original image -> inspect -> seamless text/label cleanup (+ mask & OCR baseline)
  -> optional local VAE / Diffusion reconstruction -> automated & manual QA
  -> restore original editable SVG <text> -> native SVG reconstruction (Tier 2 ROI only)

On dependency error, timeout, runtime failure, or QA rejection, the manifest is
marked `unverified` or `rejected` and the workflow safely falls back to the
standard local SVG reconstruction path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import seamless_inpaint_clean  # noqa: E402

SCHEMA_VERSION = "1.0"
DEFAULT_DIFFUSION_STRENGTH = 0.01
MAX_SCIENTIFIC_STRENGTH = 0.20
DEFAULT_PAD_MULTIPLE = 8
CINE_HYBRID_DEFAULT_MODEL = "stabilityai/sd-turbo"
FORBIDDEN_FONT_TOKENS = ("helvetica neue",)

SECRET_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key|authorization|bearer|credential)", re.I)
BEARER_VALUE_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]+", re.I)


def compute_effective_steps(mode: str, steps: int, strength: float) -> int:
    """Ensure int(effective_steps * strength) >= 1 so ultra-low-strength img2img (e.g. 0.01) never runs 0 steps."""
    if mode == "vae_roundtrip":
        return 1
    min_needed = int(math.ceil(1.0 / max(float(strength), 1e-6)))
    return max(int(steps), min_needed)


def sanitize_single_system_font(font_family: str | None, default: str = "Segoe UI") -> str:
    """Enforce a single installed Windows system font name (no CSS fallback list or uninstalled Helvetica Neue)."""
    if not font_family:
        return default
    candidates = [c.strip().strip("'\"") for c in str(font_family).split(",") if c.strip()]
    for cand in candidates:
        if cand.lower() not in FORBIDDEN_FONT_TOKENS:
            return cand
    return default


def compose_cine_hybrid_svg(
    background_png: Path,
    spec: dict[str, Any],
    output_svg: Path,
) -> dict[str, Any]:
    """Compose a CineHybrid-3D Illustrator-ready SVG 1.1 file:
    - Layer_3D_Artwork: Base64 PNG via SVG 1.1 xmlns:xlink + xlink:href (zero missing-link dialog)
    - Layer_Vector_Arrows: userSpaceOnUse multi-stop opacity gradients + dual-stroke soft glow (zero <feDropShadow>)
    - Layer_Labels & Layer_Masthead: live editable <text> with single Windows system font names (zero font error dialog)
    """
    with Image.open(background_png) as im:
        w, h = im.size
    b64_data = base64.b64encode(background_png.read_bytes()).decode("ascii")

    arrows: list[dict[str, Any]] = list(spec.get("arrows") or [])
    labels: list[dict[str, Any]] = list(spec.get("labels") or [])
    masthead: list[dict[str, Any]] = list(spec.get("masthead") or [])

    defs_lines: list[str] = []
    arrow_lines: list[str] = []

    for idx, arr in enumerate(arrows, start=1):
        grad_id = str(arr.get("gradient_id") or f"cineArrowGrad{idx}")
        x1 = float(arr["x1"])
        y1 = float(arr["y1"])
        x2 = float(arr["x2"])
        y2 = float(arr["y2"])
        gx2 = float(arr.get("grad_x2", x2))
        gy2 = float(arr.get("grad_y2", y2))
        stops = arr.get("stops") or [
            {"offset": "0%", "color": "#FFD88A", "opacity": 0.0},
            {"offset": "35%", "color": "#FFE2A3", "opacity": 0.55},
            {"offset": "80%", "color": "#FFF0C8", "opacity": 0.92},
            {"offset": "100%", "color": "#FFF8E2", "opacity": 1.0},
        ]
        defs_lines.append(
            f'    <linearGradient id="{html.escape(grad_id)}" x1="{x1:g}" y1="{y1:g}" '
            f'x2="{gx2:g}" y2="{gy2:g}" gradientUnits="userSpaceOnUse">'
        )
        for st in stops:
            defs_lines.append(
                f'      <stop offset="{html.escape(str(st["offset"]))}" '
                f'stop-color="{html.escape(str(st["color"]))}" '
                f'stop-opacity="{float(st.get("opacity", 1.0)):g}"/>'
            )
        defs_lines.append("    </linearGradient>")

        glow_width = float(arr.get("glow_width", 6.5))
        glow_opacity = float(arr.get("glow_opacity", 0.22))
        core_width = float(arr.get("core_width", 2.7))
        head_fill = str(arr.get("head_fill", "#FFF6DC"))
        head_points = arr.get("head_points")
        if not head_points:
            # Automatic deterministic triangle arrowhead aligned with (x1,y1)->(x2,y2)
            dx, dy = x2 - x1, y2 - y1
            length = max(math.hypot(dx, dy), 1e-6)
            ux, uy = dx / length, dy / length
            px, py = -uy, ux
            tip_x = x2 + ux * 10.0
            tip_y = y2 + uy * 10.0
            base_x = x2 - ux * 4.0
            base_y = y2 - uy * 4.0
            p1 = (tip_x, tip_y)
            p2 = (base_x + px * 6.0, base_y + py * 6.0)
            p3 = (base_x - px * 6.0, base_y - py * 6.0)
            head_points = f"{p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f} {p3[0]:.1f},{p3[1]:.1f}"

        arrow_id = html.escape(str(arr.get("id") or f"Arrow_{idx}"))
        arrow_lines.extend(
            [
                f'    <g id="{arrow_id}">',
                f'      <line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
                f'stroke="url(#{html.escape(grad_id)})" stroke-opacity="{glow_opacity:g}" '
                f'stroke-width="{glow_width:g}" stroke-linecap="round"/>',
                f'      <line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
                f'stroke="url(#{html.escape(grad_id)})" stroke-width="{core_width:g}" stroke-linecap="round"/>',
                f'      <polygon points="{html.escape(str(head_points))}" fill="{html.escape(head_fill)}"/>',
                "    </g>",
            ]
        )

    def _render_text_items(items: list[dict[str, Any]], default_font: str) -> list[str]:
        out: list[str] = []
        for item in items:
            x = float(item["x"])
            y = float(item["y"])
            text_val = html.escape(str(item["text"]))
            font_family = html.escape(sanitize_single_system_font(item.get("font_family"), default=default_font))
            font_size = float(item.get("font_size", 20))
            font_weight = html.escape(str(item.get("font_weight", "400")))
            fill = html.escape(str(item.get("fill", "#FFFFFF")))
            anchor = item.get("text_anchor")
            letter_spacing = item.get("letter_spacing")
            rotate = item.get("rotate")

            attrs = [
                f'x="{x:g}"',
                f'y="{y:g}"',
            ]
            if anchor:
                attrs.append(f'text-anchor="{html.escape(str(anchor))}"')
            attrs.extend(
                [
                    f'font-family="{font_family}"',
                    f'font-size="{font_size:g}"',
                    f'font-weight="{font_weight}"',
                ]
            )
            if letter_spacing is not None:
                attrs.append(f'letter-spacing="{float(letter_spacing):g}"')
            attrs.append(f'fill="{fill}"')
            if rotate is not None:
                attrs.append(f'transform="rotate({float(rotate):g} {x:g} {y:g})"')
            out.append(f"    <text {' '.join(attrs)}>{text_val}</text>")
        return out

    label_lines = _render_text_items(labels, default_font="Segoe UI")
    masthead_lines = _render_text_items(masthead, default_font="Georgia")

    svg_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
    ]
    if defs_lines:
        svg_parts.append("  <defs>")
        svg_parts.extend(defs_lines)
        svg_parts.append("  </defs>")

    svg_parts.extend(
        [
            "  <!-- Layer 1: CineHybrid-3D Lossless 3D Artwork via SVG 1.1 xlink:href -->",
            '  <g id="Layer_3D_Artwork">',
            f'    <image x="0" y="0" width="{w}" height="{h}" preserveAspectRatio="none" '
            f'xlink:href="data:image/png;base64,{b64_data}"/>',
            "  </g>",
        ]
    )
    if arrow_lines:
        svg_parts.append("  <!-- Layer 2: Filter-Free Soft Gradient Vector Arrows -->")
        svg_parts.append('  <g id="Layer_Vector_Arrows">')
        svg_parts.extend(arrow_lines)
        svg_parts.append("  </g>")
    if label_lines:
        svg_parts.append("  <!-- Layer 3: Refined Editable Scientific Labels -->")
        svg_parts.append('  <g id="Layer_Labels">')
        svg_parts.extend(label_lines)
        svg_parts.append("  </g>")
    if masthead_lines:
        svg_parts.append("  <!-- Layer 4: Editable Journal Masthead -->")
        svg_parts.append('  <g id="Layer_Masthead">')
        svg_parts.extend(masthead_lines)
        svg_parts.append("  </g>")

    svg_parts.append("</svg>\n")
    svg_text = "\n".join(svg_parts)
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    output_svg.write_text(svg_text, encoding="utf-8")

    return {
        "ok": True,
        "scheme": "CineHybrid-3D",
        "output_svg": str(output_svg),
        "width": w,
        "height": h,
        "illustrator_checks": {
            "has_xmlns_xlink": 'xmlns:xlink="http://www.w3.org/1999/xlink"' in svg_text,
            "has_xlink_href_base64": 'xlink:href="data:image/png;base64,' in svg_text,
            "zero_fe_drop_shadow": "<feDropShadow" not in svg_text and "<filter" not in svg_text,
            "zero_missing_font_stack": "helvetica neue" not in svg_text.lower(),
        },
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sanitize_for_manifest(obj: Any) -> Any:
    """Recursively strip credentials, API keys, and Bearer tokens before writing manifest or logs."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if SECRET_KEY_RE.search(str(k)):
                continue
            cleaned[k] = sanitize_for_manifest(v)
        return cleaned
    if isinstance(obj, list):
        return [sanitize_for_manifest(item) for item in obj]
    if isinstance(obj, str):
        return BEARER_VALUE_RE.sub("[REDACTED]", obj)
    return obj


def reversible_pad_image(im: Image.Image, multiple: int = DEFAULT_PAD_MULTIPLE) -> tuple[Image.Image, dict[str, int]]:
    """Pad right/bottom edges reversibly to a multiple of `multiple` without altering aspect ratio."""
    w, h = im.size
    pad_right = (multiple - (w % multiple)) % multiple
    pad_bottom = (multiple - (h % multiple)) % multiple
    if pad_right == 0 and pad_bottom == 0:
        return im.copy(), {"orig_w": w, "orig_h": h, "pad_right": 0, "pad_bottom": 0}
    arr = np.array(im)
    if arr.ndim == 2:
        padded = np.pad(arr, ((0, pad_bottom), (0, pad_right)), mode="edge")
    else:
        padded = np.pad(arr, ((0, pad_bottom), (0, pad_right), (0, 0)), mode="edge")
    return Image.fromarray(padded, mode=im.mode), {
        "orig_w": w,
        "orig_h": h,
        "pad_right": pad_right,
        "pad_bottom": pad_bottom,
    }


def reversible_crop_image(im: Image.Image, pad_info: dict[str, int]) -> Image.Image:
    """Crop a padded image back to exact original (orig_w, orig_h)."""
    return im.crop((0, 0, int(pad_info["orig_w"]), int(pad_info["orig_h"])))


def load_manifest(job_dir: Path) -> dict[str, Any]:
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found in {job_dir}. Run `prepare` first.")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def save_manifest(job_dir: Path, manifest: dict[str, Any]) -> Path:
    manifest["updated_at"] = utc_now()
    safe_manifest = sanitize_for_manifest(manifest)
    manifest_path = job_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = job_dir / "manifest.json.tmp"
    tmp_path.write_text(json.dumps(safe_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(manifest_path)
    return manifest_path


def _sobel_magnitude(gray: np.ndarray) -> np.ndarray:
    gx = (
        -gray[:-2, :-2] + gray[:-2, 2:]
        - 2.0 * gray[1:-1, :-2] + 2.0 * gray[1:-1, 2:]
        - gray[2:, :-2] + gray[2:, 2:]
    )
    gy = (
        -gray[:-2, :-2] - 2.0 * gray[:-2, 1:-1] - gray[:-2, 2:]
        + gray[2:, :-2] + 2.0 * gray[2:, 1:-1] + gray[2:, 2:]
    )
    return np.hypot(gx, gy)


def compare_ocr_boxes(
    baseline_lines: list[dict[str, Any]],
    candidate_lines: list[dict[str, Any]],
    max_shift_px: float = 8.0,
) -> dict[str, Any]:
    """Compare OCR line counts and bounding-box drift against original baseline."""
    if not baseline_lines and not candidate_lines:
        return {"passed": True, "baseline_count": 0, "candidate_count": 0, "max_drift_px": 0.0}
    count_delta = abs(len(baseline_lines) - len(candidate_lines))
    max_drift = 0.0
    for b_item in baseline_lines:
        bx, by, bw, bh = b_item.get("bbox", [0, 0, 0, 0])
        b_cx, b_cy = bx + bw / 2.0, by + bh / 2.0
        if not candidate_lines:
            max_drift = max(max_drift, max_shift_px + 1.0)
            continue
        best = min(
            (
                float(np.hypot((c.get("bbox", [0, 0, 0, 0])[0] + c.get("bbox", [0, 0, 0, 0])[2] / 2.0) - b_cx,
                               (c.get("bbox", [0, 0, 0, 0])[1] + c.get("bbox", [0, 0, 0, 0])[3] / 2.0) - b_cy))
                for c in candidate_lines
            )
        )
        max_drift = max(max_drift, best)
    passed = (count_delta == 0) and (max_drift <= max_shift_px)
    return {
        "passed": passed,
        "baseline_count": len(baseline_lines),
        "candidate_count": len(candidate_lines),
        "count_delta": count_delta,
        "max_drift_px": round(max_drift, 3),
        "max_allowed_shift_px": max_shift_px,
    }


def run_automated_qa(
    reference_path: Path,
    candidate_path: Path,
    max_mean_rgb_delta: float = 14.0,
    min_edge_corr: float = 0.88,
    baseline_ocr: list[dict[str, Any]] | None = None,
    candidate_ocr: list[dict[str, Any]] | None = None,
    max_ocr_shift_px: float = 8.0,
) -> dict[str, Any]:
    """Run automated dimension, color-mode, color-drift, edge-alignment, and optional OCR QA."""
    with Image.open(reference_path) as ref_im, Image.open(candidate_path) as cand_im:
        dims_ok = ref_im.size == cand_im.size
        orient_ok = (ref_im.size[0] >= ref_im.size[1]) == (cand_im.size[0] >= cand_im.size[1])
        mode_ok = ref_im.mode == cand_im.mode
        alpha_ok = ("A" in ref_im.mode) == ("A" in cand_im.mode)

        checks: dict[str, bool] = {
            "dimensions_match": dims_ok,
            "orientation_match": orient_ok,
            "color_mode_match": mode_ok,
            "alpha_match": alpha_ok,
        }
        metrics: dict[str, Any] = {
            "reference_size": list(ref_im.size),
            "candidate_size": list(cand_im.size),
            "reference_mode": ref_im.mode,
            "candidate_mode": cand_im.mode,
        }

        if dims_ok:
            ref_rgb = np.array(ref_im.convert("RGB"), dtype=np.float32)
            cand_rgb = np.array(cand_im.convert("RGB"), dtype=np.float32)
            mean_abs_delta = float(np.mean(np.abs(ref_rgb - cand_rgb)))
            max_channel_shift = float(np.max(np.abs(np.mean(ref_rgb, axis=(0, 1)) - np.mean(cand_rgb, axis=(0, 1)))))

            ref_gray = 0.299 * ref_rgb[:, :, 0] + 0.587 * ref_rgb[:, :, 1] + 0.114 * ref_rgb[:, :, 2]
            cand_gray = 0.299 * cand_rgb[:, :, 0] + 0.587 * cand_rgb[:, :, 1] + 0.114 * cand_rgb[:, :, 2]

            if ref_gray.shape[0] >= 4 and ref_gray.shape[1] >= 4:
                e1 = _sobel_magnitude(ref_gray).ravel()
                e2 = _sobel_magnitude(cand_gray).ravel()
                s1, s2 = float(np.std(e1)), float(np.std(e2))
                if s1 < 1e-6 and s2 < 1e-6:
                    edge_corr = 1.0
                elif s1 < 1e-6 or s2 < 1e-6:
                    edge_corr = 0.0
                else:
                    edge_corr = float(np.corrcoef(e1, e2)[0, 1])
            else:
                edge_corr = 1.0

            checks["color_drift_ok"] = mean_abs_delta <= max_mean_rgb_delta
            checks["edge_alignment_ok"] = edge_corr >= min_edge_corr
            metrics.update(
                {
                    "mean_abs_rgb_delta": round(mean_abs_delta, 4),
                    "max_mean_channel_shift": round(max_channel_shift, 4),
                    "edge_correlation": round(edge_corr, 4),
                    "max_allowed_rgb_delta": max_mean_rgb_delta,
                    "min_required_edge_corr": min_edge_corr,
                }
            )
        else:
            checks["color_drift_ok"] = False
            checks["edge_alignment_ok"] = False

    if baseline_ocr is not None and candidate_ocr is not None:
        ocr_res = compare_ocr_boxes(baseline_ocr, candidate_ocr, max_shift_px=max_ocr_shift_px)
        checks["ocr_drift_ok"] = bool(ocr_res["passed"])
        metrics["ocr"] = ocr_res

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
        "checked_at": utc_now(),
    }


class RegenerationBackend(ABC):
    """Unified backend contract for local (Diffusers / ComfyUI / Mock) or optional workstation runners."""

    backend_type: str = "base"

    def prepare(
        self,
        job_dir: Path,
        original_image: Path,
        boxes_json: Path | None = None,
        ocr_baseline_json: Path | None = None,
        inpaint_iterations: int = 160,
    ) -> dict[str, Any]:
        job_dir = job_dir.resolve()
        job_dir.mkdir(parents=True, exist_ok=True)
        orig_src = original_image.resolve()
        orig_dst = job_dir / f"original{orig_src.suffix.lower() or '.png'}"
        if orig_src != orig_dst:
            shutil.copy2(orig_src, orig_dst)

        with Image.open(orig_dst) as im:
            w, h = im.size
            color_mode = im.mode

        cleaned_path = job_dir / "cleaned.png"
        mask_path = job_dir / "text_mask.png"
        saved_boxes_path: Path | None = None

        if boxes_json and boxes_json.is_file():
            saved_boxes_path = job_dir / "boxes.json"
            if boxes_json.resolve() != saved_boxes_path:
                shutil.copy2(boxes_json.resolve(), saved_boxes_path)
            boxes = json.loads(saved_boxes_path.read_text(encoding="utf-8"))
            seamless_inpaint_clean.clean_image(
                orig_dst,
                boxes,
                cleaned_path,
                iterations=inpaint_iterations,
                mask_output=mask_path,
            )
        else:
            # No text boxes supplied: copy lossless PNG & emit an empty zero mask for audit completeness
            Image.open(orig_dst).save(cleaned_path)
            Image.fromarray(np.zeros((h, w), dtype=np.uint8), mode="L").save(mask_path)

        saved_ocr_path: Path | None = None
        if ocr_baseline_json and ocr_baseline_json.is_file():
            saved_ocr_path = job_dir / "ocr_baseline.json"
            if ocr_baseline_json.resolve() != saved_ocr_path:
                shutil.copy2(ocr_baseline_json.resolve(), saved_ocr_path)

        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "job_id": f"regen-{uuid.uuid4().hex[:12]}",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "original": {
                "path": str(orig_dst),
                "sha256": sha256_file(orig_dst),
                "width": w,
                "height": h,
                "mode": color_mode,
            },
            "cleaned": {
                "path": str(cleaned_path),
                "sha256": sha256_file(cleaned_path),
                "mask_path": str(mask_path),
                "boxes_path": str(saved_boxes_path) if saved_boxes_path else None,
                "ocr_baseline_path": str(saved_ocr_path) if saved_ocr_path else None,
            },
            "backend": {
                "type": self.backend_type,
                "mode": None,
                "model_id": None,
                "model_revision": None,
                "steps": None,
                "strength": None,
                "seed": None,
                "pad_multiple": DEFAULT_PAD_MULTIPLE,
                "input_resolution": [w, h],
                "color_mode": color_mode,
                "prompt": "",
                "controlnet": None,
                "lora": None,
            },
            "job": {
                "status": "prepared",
                "state_history": [{"status": "prepared", "at": utc_now()}],
                "remote_job_id": None,
                "started_at": None,
                "finished_at": None,
                "error": None,
            },
            "artifact": None,
            "qa": None,
            "decision": "pending",
            "review_notes": "",
            "fallback_path": str(cleaned_path),
        }
        save_manifest(job_dir, manifest)
        return manifest

    @abstractmethod
    def create_job(self, job_dir: Path, manifest: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_job(self, job_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_artifact(self, job_dir: Path, manifest: dict[str, Any]) -> Path | None:
        raise NotImplementedError

    def qa(
        self,
        job_dir: Path,
        manifest: dict[str, Any],
        max_mean_rgb_delta: float = 14.0,
        min_edge_corr: float = 0.88,
        candidate_ocr_json: Path | None = None,
        max_ocr_shift_px: float = 8.0,
    ) -> dict[str, Any]:
        artifact = manifest.get("artifact") or {}
        cand_str = artifact.get("path")
        if not cand_str or not Path(cand_str).is_file():
            qa_res = {
                "passed": False,
                "checks": {"artifact_exists": False},
                "metrics": {},
                "checked_at": utc_now(),
            }
            manifest["qa"] = qa_res
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
            return qa_res

        ref_path = Path(manifest["cleaned"]["path"])
        baseline_ocr = None
        candidate_ocr = None
        if candidate_ocr_json and candidate_ocr_json.is_file():
            candidate_ocr_raw = json.loads(candidate_ocr_json.read_text(encoding="utf-8"))
            candidate_ocr = candidate_ocr_raw.get("ocr_lines", candidate_ocr_raw) if isinstance(candidate_ocr_raw, dict) else candidate_ocr_raw
            ocr_base_str = manifest["cleaned"].get("ocr_baseline_path")
            if ocr_base_str and Path(ocr_base_str).is_file():
                base_raw = json.loads(Path(ocr_base_str).read_text(encoding="utf-8"))
                baseline_ocr = base_raw.get("ocr_lines", base_raw) if isinstance(base_raw, dict) else base_raw

        qa_res = run_automated_qa(
            reference_path=ref_path,
            candidate_path=Path(cand_str),
            max_mean_rgb_delta=max_mean_rgb_delta,
            min_edge_corr=min_edge_corr,
            baseline_ocr=baseline_ocr,
            candidate_ocr=candidate_ocr,
            max_ocr_shift_px=max_ocr_shift_px,
        )
        manifest["qa"] = qa_res
        if not qa_res["passed"]:
            manifest["decision"] = "rejected"
        save_manifest(job_dir, manifest)
        return qa_res

    def cancel(self, job_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        _transition_job(manifest, "cancelled", error="Cancelled by user.")
        if manifest.get("decision") == "pending":
            manifest["decision"] = "unverified"
        save_manifest(job_dir, manifest)
        return manifest


def _transition_job(manifest: dict[str, Any], status: str, error: str | None = None) -> None:
    now = utc_now()
    manifest["job"]["status"] = status
    manifest["job"].setdefault("state_history", []).append({"status": status, "at": now})
    if status == "running" and not manifest["job"].get("started_at"):
        manifest["job"]["started_at"] = now
    if status in {"succeeded", "failed", "timed_out", "cancelled"}:
        manifest["job"]["finished_at"] = now
    if error is not None:
        manifest["job"]["error"] = error


def _record_artifact(manifest: dict[str, Any], artifact_path: Path) -> None:
    with Image.open(artifact_path) as im:
        w, h = im.size
        mode = im.mode
    manifest["artifact"] = {
        "path": str(artifact_path),
        "sha256": sha256_file(artifact_path),
        "width": w,
        "height": h,
        "mode": mode,
    }


def _validate_conservative_params(
    mode: str,
    strength: float,
    allow_high_strength: bool,
    prompt: str,
) -> None:
    if mode not in {"vae_roundtrip", "diffusion_img2img"}:
        raise ValueError(f"Unsupported mode: {mode}")
    if prompt:
        raise ValueError("Semantic text prompts are disabled by default for scientific figure preservation.")
    if mode == "diffusion_img2img":
        if not (0.0 < strength <= 1.0):
            raise ValueError(f"strength must be in (0, 1], got {strength}")
        if strength > MAX_SCIENTIFIC_STRENGTH and not allow_high_strength:
            raise ValueError(
                f"strength={strength} exceeds conservative scientific cap ({MAX_SCIENTIFIC_STRENGTH}). "
                "Pass --allow-high-strength explicitly to override."
            )


class LocalDiffusersBackend(RegenerationBackend):
    """Core local implementation using HuggingFace Diffusers AutoencoderKL / AutoPipelineForImage2Image."""

    backend_type = "local_diffusers"

    def create_job(
        self,
        job_dir: Path,
        manifest: dict[str, Any],
        mode: str = "vae_roundtrip",
        model_id: str = "",
        model_revision: str = "main",
        strength: float = DEFAULT_DIFFUSION_STRENGTH,
        steps: int = 20,
        seed: int = 42,
        pad_multiple: int = DEFAULT_PAD_MULTIPLE,
        allow_high_strength: bool = False,
        device: str = "auto",
        **_: Any,
    ) -> dict[str, Any]:
        _validate_conservative_params(mode, strength, allow_high_strength, prompt="")
        if not model_id:
            raise ValueError("`--model-id` (local path or HuggingFace model ID) is required for local_diffusers.")

        effective_steps = compute_effective_steps(mode, int(steps), float(strength))
        manifest["backend"].update(
            {
                "type": self.backend_type,
                "mode": mode,
                "model_id": model_id,
                "model_revision": model_revision,
                "steps": effective_steps,
                "strength": 0.0 if mode == "vae_roundtrip" else float(strength),
                "seed": int(seed),
                "pad_multiple": int(pad_multiple),
                "prompt": "",
                "controlnet": None,
                "lora": None,
            }
        )
        _transition_job(manifest, "queued")
        save_manifest(job_dir, manifest)

        _transition_job(manifest, "running")
        save_manifest(job_dir, manifest)

        try:
            import torch
            from diffusers import AutoencoderKL, AutoPipelineForImage2Image
        except (ImportError, OSError) as exc:
            _transition_job(
                manifest,
                "failed",
                error=f"Missing local Diffusers runtime ({exc}). Fallback to standard SVG pipeline.",
            )
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
            return manifest

        try:
            resolved_device = device
            if resolved_device == "auto":
                resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if resolved_device == "cuda" else torch.float32

            cleaned_path = Path(manifest["cleaned"]["path"])
            src_im = Image.open(cleaned_path)
            orig_mode = src_im.mode
            alpha_band = src_im.getchannel("A") if "A" in orig_mode else None
            rgb_im = src_im.convert("RGB")
            padded_im, pad_info = reversible_pad_image(rgb_im, multiple=int(pad_multiple))

            if mode == "vae_roundtrip":
                vae = AutoencoderKL.from_pretrained(model_id, revision=model_revision, torch_dtype=dtype)
                if hasattr(vae, "enable_tiling"):
                    vae.enable_tiling()
                vae = vae.to(resolved_device)
                vae.eval()

                arr = np.array(padded_im, dtype=np.float32) / 127.5 - 1.0
                tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(device=resolved_device, dtype=dtype)
                with torch.no_grad():
                    latent = vae.encode(tensor).latent_dist.mean
                    decoded = vae.decode(latent).sample
                out_arr = ((decoded.squeeze(0).permute(1, 2, 0).float().cpu().numpy() + 1.0) * 127.5)
                out_padded = Image.fromarray(np.clip(out_arr, 0, 255).astype(np.uint8), mode="RGB")
            else:
                pipe = AutoPipelineForImage2Image.from_pretrained(
                    model_id,
                    revision=model_revision,
                    torch_dtype=dtype,
                    safety_checker=None,
                )
                if hasattr(pipe, "enable_vae_tiling"):
                    pipe.enable_vae_tiling()
                pipe = pipe.to(resolved_device)
                gen = torch.Generator(device=resolved_device).manual_seed(int(seed))
                g_scale = 0.0 if "turbo" in model_id.lower() else 1.0
                result = pipe(
                    prompt="",
                    image=padded_im,
                    strength=float(strength),
                    num_inference_steps=effective_steps,
                    guidance_scale=g_scale,
                    generator=gen,
                )
                out_padded = result.images[0].convert("RGB")

            out_im = reversible_crop_image(out_padded, pad_info)
            if alpha_band is not None:
                out_im = out_im.convert("RGBA")
                out_im.putalpha(alpha_band)
            elif orig_mode != out_im.mode:
                out_im = out_im.convert(orig_mode)

            artifact_path = job_dir / "reconstructed.png"
            out_im.save(artifact_path)
            _record_artifact(manifest, artifact_path)
            _transition_job(manifest, "succeeded")
            save_manifest(job_dir, manifest)
            return manifest
        except Exception as exc:
            _transition_job(manifest, "failed", error=f"Local Diffusers execution failed: {exc}")
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
            return manifest

    def get_job(self, job_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        return manifest

    def fetch_artifact(self, job_dir: Path, manifest: dict[str, Any]) -> Path | None:
        art = manifest.get("artifact") or {}
        p = art.get("path")
        return Path(p) if p and Path(p).is_file() else None


class ComfyUIBackend(RegenerationBackend):
    """Optional local ComfyUI HTTP queue / workstation adapter (zero secrets written to manifest)."""

    backend_type = "comfyui"

    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout_s: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # Optional token only read transiently from env; never logged or persisted in manifest
        token = os.environ.get("COMFYUI_API_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def create_job(
        self,
        job_dir: Path,
        manifest: dict[str, Any],
        mode: str = "vae_roundtrip",
        model_id: str = "comfyui-local-workflow",
        model_revision: str = "local",
        strength: float = DEFAULT_DIFFUSION_STRENGTH,
        steps: int = 20,
        seed: int = 42,
        pad_multiple: int = DEFAULT_PAD_MULTIPLE,
        allow_high_strength: bool = False,
        workflow_json: Path | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        _validate_conservative_params(mode, strength, allow_high_strength, prompt="")
        manifest["backend"].update(
            {
                "type": self.backend_type,
                "mode": mode,
                "model_id": model_id,
                "model_revision": model_revision,
                "steps": 1 if mode == "vae_roundtrip" else int(steps),
                "strength": 0.0 if mode == "vae_roundtrip" else float(strength),
                "seed": int(seed),
                "pad_multiple": int(pad_multiple),
                "endpoint": self.base_url,
            }
        )
        _transition_job(manifest, "queued")
        save_manifest(job_dir, manifest)

        if not workflow_json or not workflow_json.is_file():
            _transition_job(manifest, "failed", error="ComfyUI requires --workflow-json pointing to a local API workflow.")
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
            return manifest

        try:
            payload = {"prompt": json.loads(workflow_json.read_text(encoding="utf-8")), "client_id": manifest["job_id"]}
            req = urllib.request.Request(
                f"{self.base_url}/prompt",
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            manifest["job"]["remote_job_id"] = body.get("prompt_id")
            _transition_job(manifest, "running")
            save_manifest(job_dir, manifest)
            return manifest
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            _transition_job(manifest, "failed", error=f"ComfyUI unreachable or rejected prompt: {exc}")
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
            return manifest

    def get_job(self, job_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        prompt_id = manifest["job"].get("remote_job_id")
        if not prompt_id:
            return manifest
        try:
            req = urllib.request.Request(f"{self.base_url}/history/{urllib.parse.quote(str(prompt_id))}", headers=self._headers())
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                hist = json.loads(resp.read().decode("utf-8"))
            if prompt_id in hist:
                _transition_job(manifest, "succeeded")
                save_manifest(job_dir, manifest)
        except TimeoutError:
            _transition_job(manifest, "timed_out", error="ComfyUI history poll timed out.")
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
        except (urllib.error.URLError, OSError) as exc:
            _transition_job(manifest, "failed", error=f"ComfyUI status check failed: {exc}")
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
        return manifest

    def fetch_artifact(self, job_dir: Path, manifest: dict[str, Any]) -> Path | None:
        art = manifest.get("artifact") or {}
        if art.get("path") and Path(art["path"]).is_file():
            return Path(art["path"])
        return None

    def cancel(self, job_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        try:
            req = urllib.request.Request(f"{self.base_url}/interrupt", data=b"{}", headers=self._headers(), method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
        return super().cancel(job_dir, manifest)


class MockBackend(RegenerationBackend):
    """Deterministic local test backend for verifying state transitions, pad/crop, QA rejection, and fallback."""

    backend_type = "mock"

    def create_job(
        self,
        job_dir: Path,
        manifest: dict[str, Any],
        mode: str = "vae_roundtrip",
        model_id: str = "mock-local-vae-v1",
        model_revision: str = "test-rev-1",
        strength: float = DEFAULT_DIFFUSION_STRENGTH,
        steps: int = 10,
        seed: int = 42,
        pad_multiple: int = DEFAULT_PAD_MULTIPLE,
        allow_high_strength: bool = False,
        mock_outcome: str = "succeeded",
        mock_perturbation: str = "none",
        **_: Any,
    ) -> dict[str, Any]:
        _validate_conservative_params(mode, strength, allow_high_strength, prompt="")
        effective_steps = compute_effective_steps(mode, int(steps), float(strength))
        manifest["backend"].update(
            {
                "type": self.backend_type,
                "mode": mode,
                "model_id": model_id,
                "model_revision": model_revision,
                "steps": effective_steps,
                "strength": 0.0 if mode == "vae_roundtrip" else float(strength),
                "seed": int(seed),
                "pad_multiple": int(pad_multiple),
                "prompt": "",
                "controlnet": None,
                "lora": None,
            }
        )
        _transition_job(manifest, "queued")
        save_manifest(job_dir, manifest)

        _transition_job(manifest, "running")
        save_manifest(job_dir, manifest)

        if mock_outcome in {"failed", "timed_out"}:
            _transition_job(manifest, mock_outcome, error=f"Simulated mock outcome: {mock_outcome}")
            manifest["decision"] = "unverified"
            save_manifest(job_dir, manifest)
            return manifest

        cleaned_path = Path(manifest["cleaned"]["path"])
        src_im = Image.open(cleaned_path)
        orig_mode = src_im.mode
        padded_im, pad_info = reversible_pad_image(src_im.convert("RGB"), multiple=int(pad_multiple))

        rng = np.random.default_rng(int(seed))
        arr = np.array(padded_im, dtype=np.float32)

        if mock_perturbation == "none":
            # Mild deterministic quantization noise simulating lossless VAE roundtrip
            noise = rng.normal(0.0, 0.8 if mode == "vae_roundtrip" else 1.5, size=arr.shape)
            out_padded = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), mode="RGB")
            out_im = reversible_crop_image(out_padded, pad_info)
        elif mock_perturbation == "resize":
            out_im = src_im.convert("RGB").resize((max(8, src_im.size[0] - 12), max(8, src_im.size[1] - 8)))
        elif mock_perturbation == "crop_shift":
            # Shift image by 10 pixels horizontally and vertically to simulate misaligned crop
            shifted = np.roll(np.array(src_im.convert("RGB")), shift=(10, 10), axis=(0, 1))
            out_im = Image.fromarray(shifted, mode="RGB")
        elif mock_perturbation == "color_drift":
            drifted = np.clip(np.array(src_im.convert("RGB"), dtype=np.float32) + 45.0, 0, 255).astype(np.uint8)
            out_im = Image.fromarray(drifted, mode="RGB")
        else:
            raise ValueError(f"Unknown mock_perturbation: {mock_perturbation}")

        if orig_mode != out_im.mode and mock_perturbation != "resize":
            out_im = out_im.convert(orig_mode)

        artifact_path = job_dir / "reconstructed.png"
        out_im.save(artifact_path)
        _record_artifact(manifest, artifact_path)
        _transition_job(manifest, "succeeded")
        save_manifest(job_dir, manifest)
        return manifest

    def get_job(self, job_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        return manifest

    def fetch_artifact(self, job_dir: Path, manifest: dict[str, Any]) -> Path | None:
        art = manifest.get("artifact") or {}
        p = art.get("path")
        return Path(p) if p and Path(p).is_file() else None


def get_backend(name: str, comfy_url: str = "http://127.0.0.1:8188") -> RegenerationBackend:
    if name == "local_diffusers":
        return LocalDiffusersBackend()
    if name == "comfyui":
        return ComfyUIBackend(base_url=comfy_url)
    if name == "mock":
        return MockBackend()
    raise ValueError(f"Unsupported backend: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-first VAE / Diffusion optional preprocessing CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prep = sub.add_parser("prepare", help="Prepare cleaned copy, binary text mask, and audit manifest.")
    p_prep.add_argument("--job-dir", required=True, type=Path)
    p_prep.add_argument("--image", required=True, type=Path)
    p_prep.add_argument("--boxes-json", type=Path, default=None)
    p_prep.add_argument("--ocr-baseline-json", type=Path, default=None)
    p_prep.add_argument("--iterations", type=int, default=160)

    p_run = sub.add_parser("run", help="Run local VAE / Diffusion (or mock/comfyui) reconstruction.")
    p_run.add_argument("--job-dir", required=True, type=Path)
    p_run.add_argument("--backend", choices=["local_diffusers", "comfyui", "mock"], default="local_diffusers")
    p_run.add_argument("--mode", choices=["vae_roundtrip", "diffusion_img2img"], default="vae_roundtrip")
    p_run.add_argument("--model-id", default="")
    p_run.add_argument("--model-revision", default="main")
    p_run.add_argument("--strength", type=float, default=DEFAULT_DIFFUSION_STRENGTH)
    p_run.add_argument("--steps", type=int, default=20)
    p_run.add_argument("--seed", type=int, default=42)
    p_run.add_argument("--pad-multiple", type=int, default=DEFAULT_PAD_MULTIPLE)
    p_run.add_argument("--allow-high-strength", action="store_true")
    p_run.add_argument("--device", default="auto")
    p_run.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    p_run.add_argument("--workflow-json", type=Path, default=None)
    p_run.add_argument("--mock-outcome", choices=["succeeded", "failed", "timed_out"], default="succeeded")
    p_run.add_argument("--mock-perturbation", choices=["none", "resize", "crop_shift", "color_drift"], default="none")

    p_stat = sub.add_parser("status", help="Query local or remote job status.")
    p_stat.add_argument("--job-dir", required=True, type=Path)
    p_stat.add_argument("--comfy-url", default="http://127.0.0.1:8188")

    p_qa = sub.add_parser("qa", help="Run automated dimension, color, edge, and OCR QA checks.")
    p_qa.add_argument("--job-dir", required=True, type=Path)
    p_qa.add_argument("--max-rgb-delta", type=float, default=14.0)
    p_qa.add_argument("--min-edge-corr", type=float, default=0.88)
    p_qa.add_argument("--candidate-ocr-json", type=Path, default=None)
    p_qa.add_argument("--max-ocr-shift-px", type=float, default=8.0)

    p_acc = sub.add_parser("accept", help="Accept QA-verified artifact for Tier 2 ROI SVG handoff.")
    p_acc.add_argument("--job-dir", required=True, type=Path)
    p_acc.add_argument("--notes", default="")

    p_rej = sub.add_parser("reject", help="Reject artifact and record fallback to original SVG pipeline.")
    p_rej.add_argument("--job-dir", required=True, type=Path)
    p_rej.add_argument("--notes", default="Rejected; falling back to untouched original/cleaned SVG path.")

    p_can = sub.add_parser("cancel", help="Cancel an active job.")
    p_can.add_argument("--job-dir", required=True, type=Path)
    p_can.add_argument("--comfy-url", default="http://127.0.0.1:8188")

    p_hyb = sub.add_parser(
        "compose-hybrid-svg",
        help="Compose CineHybrid-3D Illustrator SVG 1.1 (xlink:href 3D layer + soft gradient arrows + single-font editable text).",
    )
    p_hyb.add_argument("--background-png", required=True, type=Path, help="Reconstructed or cleaned 3D background PNG.")
    p_hyb.add_argument("--spec-json", required=True, type=Path, help="JSON spec with arrows, labels, and masthead.")
    p_hyb.add_argument("--output-svg", required=True, type=Path, help="Output Illustrator-ready SVG 1.1 path.")

    args = parser.parse_args(argv)
    if args.command == "compose-hybrid-svg":
        spec_data = json.loads(args.spec_json.resolve().read_text(encoding="utf-8"))
        res = compose_cine_hybrid_svg(
            background_png=args.background_png.resolve(),
            spec=spec_data,
            output_svg=args.output_svg.resolve(),
        )
        print(json.dumps(res, ensure_ascii=False))
        return 0 if all(res["illustrator_checks"].values()) else 1

    job_dir = args.job_dir.resolve()

    if args.command == "prepare":
        backend = LocalDiffusersBackend()
        manifest = backend.prepare(
            job_dir=job_dir,
            original_image=args.image,
            boxes_json=args.boxes_json,
            ocr_baseline_json=args.ocr_baseline_json,
            inpaint_iterations=args.iterations,
        )
        print(json.dumps({"ok": True, "job_id": manifest["job_id"], "cleaned": manifest["cleaned"]["path"], "mask": manifest["cleaned"]["mask_path"]}, ensure_ascii=False))
        return 0

    manifest = load_manifest(job_dir)

    if args.command == "run":
        backend = get_backend(args.backend, comfy_url=args.comfy_url)
        manifest = backend.create_job(
            job_dir=job_dir,
            manifest=manifest,
            mode=args.mode,
            model_id=args.model_id or ("mock-local-vae-v1" if args.backend == "mock" else ""),
            model_revision=args.model_revision,
            strength=args.strength,
            steps=args.steps,
            seed=args.seed,
            pad_multiple=args.pad_multiple,
            allow_high_strength=args.allow_high_strength,
            device=args.device,
            workflow_json=args.workflow_json,
            mock_outcome=args.mock_outcome,
            mock_perturbation=args.mock_perturbation,
        )
        print(json.dumps(sanitize_for_manifest({"ok": manifest["job"]["status"] == "succeeded", "status": manifest["job"]["status"], "decision": manifest["decision"], "artifact": manifest["artifact"], "fallback_path": manifest["fallback_path"]}), ensure_ascii=False))
        return 0 if manifest["job"]["status"] == "succeeded" else 1

    if args.command == "status":
        btype = manifest.get("backend", {}).get("type") or "local_diffusers"
        backend = get_backend(btype, comfy_url=args.comfy_url)
        manifest = backend.get_job(job_dir, manifest)
        print(json.dumps(sanitize_for_manifest({"job_id": manifest["job_id"], "status": manifest["job"]["status"], "decision": manifest["decision"], "error": manifest["job"].get("error")}), ensure_ascii=False))
        return 0

    if args.command == "qa":
        btype = manifest.get("backend", {}).get("type") or "local_diffusers"
        backend = get_backend(btype)
        qa_res = backend.qa(
            job_dir=job_dir,
            manifest=manifest,
            max_mean_rgb_delta=args.max_rgb_delta,
            min_edge_corr=args.min_edge_corr,
            candidate_ocr_json=args.candidate_ocr_json,
            max_ocr_shift_px=args.max_ocr_shift_px,
        )
        print(json.dumps(sanitize_for_manifest(qa_res), ensure_ascii=False))
        return 0 if qa_res["passed"] else 1

    if args.command == "accept":
        qa_block = manifest.get("qa") or {}
        if not qa_block.get("passed"):
            print(json.dumps({"ok": False, "error": "Cannot accept artifact before automated QA passes.", "fallback_path": manifest["fallback_path"]}, ensure_ascii=False))
            return 1
        manifest["decision"] = "accepted"
        manifest["review_notes"] = args.notes
        save_manifest(job_dir, manifest)
        print(json.dumps({"ok": True, "decision": "accepted", "tier2_roi_input": manifest["artifact"]["path"]}, ensure_ascii=False))
        return 0

    if args.command == "reject":
        manifest["decision"] = "rejected"
        manifest["review_notes"] = args.notes
        save_manifest(job_dir, manifest)
        print(json.dumps({"ok": True, "decision": "rejected", "fallback_path": manifest["fallback_path"]}, ensure_ascii=False))
        return 0

    if args.command == "cancel":
        btype = manifest.get("backend", {}).get("type") or "local_diffusers"
        backend = get_backend(btype, comfy_url=args.comfy_url)
        manifest = backend.cancel(job_dir, manifest)
        print(json.dumps({"ok": True, "status": manifest["job"]["status"], "decision": manifest["decision"]}, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
