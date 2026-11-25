#!/usr/bin/env python3
"""Automated test suite for the local-first neural regeneration optional branch."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import neural_regeneration as nr  # noqa: E402


def make_synthetic_figure(path: Path, size: tuple[int, int] = (67, 53)) -> None:
    """Create a small fixed synthetic scientific figure with crisp borders, shape, and text-like mark."""
    w, h = size
    im = Image.new("RGB", (w, h), (242, 247, 252))
    draw = ImageDraw.Draw(im)
    # Outer card border
    draw.rectangle([4, 4, w - 5, h - 5], outline=(40, 80, 120), width=2)
    # Inner shaded plot box
    draw.rectangle([10, 12, w - 11, h - 18], fill=(225, 238, 248), outline=(90, 130, 170), width=1)
    # Diagonal curve / arrow line
    draw.line([(12, h - 22), (w - 14, 16)], fill=(20, 90, 160), width=2)
    # Dark text-like strokes in bottom strip
    draw.rectangle([16, h - 13, 36, h - 9], fill=(20, 25, 35))
    im.save(path)


class TestNeuralRegeneration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.src_img = self.tmp / "fig_small.png"
        # Intentionally non-multiple of 8 and 16 to verify reversible padding & crop-back
        make_synthetic_figure(self.src_img, size=(67, 53))
        self.boxes_json = self.tmp / "boxes.json"
        self.boxes_json.write_text(
            json.dumps([{"x": 12, "y": 38, "w": 30, "h": 10, "mode": "dark_text"}]),
            encoding="utf-8",
        )
        self.ocr_baseline = self.tmp / "ocr_base.json"
        self.ocr_baseline.write_text(
            json.dumps({"ocr_lines": [{"bbox": [16, 40, 20, 5], "text": "Label A"}]}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_reversible_pad_and_crop_preserves_dimensions_and_pixels(self) -> None:
        im = Image.open(self.src_img)
        padded, info = nr.reversible_pad_image(im, multiple=16)
        self.assertEqual(padded.size[0] % 16, 0)
        self.assertEqual(padded.size[1] % 16, 0)
        restored = nr.reversible_crop_image(padded, info)
        self.assertEqual(restored.size, im.size)
        self.assertEqual(restored.mode, im.mode)
        self.assertTrue(np.array_equal(np.array(im), np.array(restored)))

    def test_prepare_and_vae_roundtrip_manifest_and_qa_pass(self) -> None:
        job_dir = self.tmp / "job_vae"
        rc_prep = nr.main(
            [
                "prepare",
                "--job-dir", str(job_dir),
                "--image", str(self.src_img),
                "--boxes-json", str(self.boxes_json),
                "--ocr-baseline-json", str(self.ocr_baseline),
                "--iterations", "30",
            ]
        )
        self.assertEqual(rc_prep, 0)

        rc_run = nr.main(
            [
                "run",
                "--job-dir", str(job_dir),
                "--backend", "mock",
                "--mode", "vae_roundtrip",
                "--seed", "123",
                "--pad-multiple", "16",
            ]
        )
        self.assertEqual(rc_run, 0)

        rc_qa = nr.main(
            [
                "qa",
                "--job-dir", str(job_dir),
                "--candidate-ocr-json", str(self.ocr_baseline),
            ]
        )
        self.assertEqual(rc_qa, 0)

        rc_acc = nr.main(["accept", "--job-dir", str(job_dir), "--notes", "1:1 verified"])
        self.assertEqual(rc_acc, 0)

        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["original"]["width"], 67)
        self.assertEqual(manifest["original"]["height"], 53)
        self.assertEqual(manifest["artifact"]["width"], 67)
        self.assertEqual(manifest["artifact"]["height"], 53)
        self.assertTrue(Path(manifest["cleaned"]["mask_path"]).is_file())
        self.assertTrue(Path(manifest["cleaned"]["boxes_path"]).is_file())
        self.assertEqual(manifest["backend"]["mode"], "vae_roundtrip")
        self.assertEqual(manifest["backend"]["seed"], 123)
        self.assertEqual(manifest["decision"], "accepted")
        self.assertEqual(manifest["review_notes"], "1:1 verified")
        statuses = [s["status"] for s in manifest["job"]["state_history"]]
        self.assertEqual(statuses, ["prepared", "queued", "running", "succeeded"])

    def test_mock_state_transitions_failed_and_timed_out_and_svg_fallback(self) -> None:
        for outcome in ("failed", "timed_out"):
            job_dir = self.tmp / f"job_{outcome}"
            self.assertEqual(nr.main(["prepare", "--job-dir", str(job_dir), "--image", str(self.src_img)]), 0)
            rc_run = nr.main(
                [
                    "run",
                    "--job-dir", str(job_dir),
                    "--backend", "mock",
                    "--mode", "diffusion_img2img",
                    "--strength", "0.10",
                    "--mock-outcome", outcome,
                ]
            )
            self.assertEqual(rc_run, 1)
            manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
            statuses = [s["status"] for s in manifest["job"]["state_history"]]
            self.assertEqual(statuses, ["prepared", "queued", "running", outcome])
            self.assertEqual(manifest["decision"], "unverified")
            self.assertTrue(Path(manifest["fallback_path"]).is_file())

            # Verify fallback SVG generation + PNG preview still succeeds cleanly
            fallback_svg = job_dir / "fallback.svg"
            fallback_svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="67" height="53" viewBox="0 0 67 53">'
                '<rect x="0" y="0" width="67" height="53" fill="#FFFFFF"/>'
                '<rect x="4" y="4" width="59" height="45" fill="none" stroke="#285078" stroke-width="2"/>'
                "</svg>",
                encoding="utf-8",
            )
            preview_png = job_dir / "fallback_preview.png"
            proc = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(SCRIPTS_DIR / "render_svg_preview.py"),
                    "--svg", str(fallback_svg),
                    "--png", str(preview_png),
                    "--width", "67",
                    "--height", "53",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertTrue(preview_png.is_file())

    def test_qa_rejects_resize_crop_shift_color_drift_and_ocr_drift(self) -> None:
        # 1. Resize perturbation
        for perturbation in ("resize", "crop_shift", "color_drift"):
            job_dir = self.tmp / f"job_{perturbation}"
            nr.main(["prepare", "--job-dir", str(job_dir), "--image", str(self.src_img)])
            nr.main(
                [
                    "run",
                    "--job-dir", str(job_dir),
                    "--backend", "mock",
                    "--mode", "vae_roundtrip",
                    "--mock-perturbation", perturbation,
                ]
            )
            rc_qa = nr.main(["qa", "--job-dir", str(job_dir)])
            self.assertEqual(rc_qa, 1, f"Expected QA to reject {perturbation}")
            manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["qa"]["passed"])
            self.assertEqual(manifest["decision"], "rejected")
            # Accepting a rejected artifact must fail
            self.assertEqual(nr.main(["accept", "--job-dir", str(job_dir)]), 1)

        # 2. OCR box drift perturbation
        job_dir = self.tmp / "job_ocr_drift"
        nr.main(
            [
                "prepare",
                "--job-dir", str(job_dir),
                "--image", str(self.src_img),
                "--ocr-baseline-json", str(self.ocr_baseline),
            ]
        )
        nr.main(["run", "--job-dir", str(job_dir), "--backend", "mock", "--mode", "vae_roundtrip"])
        drifted_ocr = self.tmp / "ocr_drifted.json"
        drifted_ocr.write_text(
            json.dumps({"ocr_lines": [{"bbox": [40, 40, 20, 5], "text": "Label A"}]}),
            encoding="utf-8",
        )
        rc_qa = nr.main(
            [
                "qa",
                "--job-dir", str(job_dir),
                "--candidate-ocr-json", str(drifted_ocr),
                "--max-ocr-shift-px", "5.0",
            ]
        )
        self.assertEqual(rc_qa, 1)
        manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["qa"]["checks"]["ocr_drift_ok"])
        self.assertEqual(manifest["decision"], "rejected")

    def test_conservative_strength_cap_enforced(self) -> None:
        job_dir = self.tmp / "job_cap"
        nr.main(["prepare", "--job-dir", str(job_dir), "--image", str(self.src_img)])
        with self.assertRaises(ValueError):
            nr.main(
                [
                    "run",
                    "--job-dir", str(job_dir),
                    "--backend", "mock",
                    "--mode", "diffusion_img2img",
                    "--strength", "0.35",
                ]
            )

    def test_secret_redaction_never_writes_tokens_to_manifest(self) -> None:
        job_dir = self.tmp / "job_secrets"
        nr.main(["prepare", "--job-dir", str(job_dir), "--image", str(self.src_img)])
        manifest = nr.load_manifest(job_dir)
        manifest["api_key"] = "sk-super-secret-12345"
        manifest["backend"]["authorization"] = "Bearer secret_token_xyz"
        manifest["review_notes"] = "Header had Bearer leaked_token_999 inside note"
        nr.save_manifest(job_dir, manifest)

        raw = (job_dir / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("sk-super-secret-12345", raw)
        self.assertNotIn("secret_token_xyz", raw)
        self.assertNotIn("leaked_token_999", raw)
        self.assertIn("[REDACTED]", raw)

    def test_compute_effective_steps_auto_scales_for_ultra_low_strength(self) -> None:
        # At strength=0.01 (CineHybrid-3D preset), steps=20 must auto-scale to >= 100 so int(steps*strength) >= 1
        self.assertEqual(nr.compute_effective_steps("diffusion_img2img", steps=20, strength=0.01), 100)
        self.assertEqual(nr.compute_effective_steps("diffusion_img2img", steps=120, strength=0.01), 120)
        self.assertEqual(nr.compute_effective_steps("vae_roundtrip", steps=50, strength=0.01), 1)

    def test_cine_hybrid_3d_svg_composer_enforces_illustrator_guardrails(self) -> None:
        spec = {
            "arrows": [
                {"id": "Arrow_1", "x1": 10, "y1": 40, "x2": 50, "y2": 15},
            ],
            "labels": [
                {
                    "x": 30,
                    "y": 25,
                    "text": "CAR-T Cell",
                    "font_family": "'Helvetica Neue', 'Segoe UI', Arial, sans-serif",
                    "font_size": 14,
                    "font_weight": "600",
                    "text_anchor": "middle",
                    "fill": "#F2F7FF",
                },
                {
                    "x": 28,
                    "y": 35,
                    "text": "IL-2, IFN-γ",
                    "font_family": "Segoe UI",
                    "font_size": 11,
                    "font_weight": "500",
                    "rotate": -26,
                },
            ],
            "masthead": [
                {
                    "x": 5,
                    "y": 12,
                    "text": "NATURE",
                    "font_family": "Georgia, 'Times New Roman', serif",
                    "font_size": 24,
                    "font_weight": "400",
                }
            ],
        }
        spec_path = self.tmp / "hybrid_spec.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out_svg = self.tmp / "cine_hybrid.svg"

        rc = nr.main(
            [
                "compose-hybrid-svg",
                "--background-png", str(self.src_img),
                "--spec-json", str(spec_path),
                "--output-svg", str(out_svg),
            ]
        )
        self.assertEqual(rc, 0)
        self.assertTrue(out_svg.is_file())
        svg_text = out_svg.read_text(encoding="utf-8")
        self.assertIn('xmlns:xlink="http://www.w3.org/1999/xlink"', svg_text)
        self.assertIn('xlink:href="data:image/png;base64,', svg_text)
        self.assertNotIn("<feDropShadow", svg_text)
        self.assertNotIn("<filter", svg_text)
        self.assertNotIn("Helvetica Neue", svg_text)
        self.assertIn('font-family="Segoe UI"', svg_text)
        self.assertIn('font-family="Georgia"', svg_text)


if __name__ == "__main__":
    unittest.main()
