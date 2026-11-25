#!/usr/bin/env python3
"""Seamless stroke-masked Laplace harmonic diffusion text removal (zero rectangular color patches)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter


def dilate(mask: np.ndarray, iters: int = 2) -> np.ndarray:
    out = mask.copy()
    for _ in range(iters):
        p = np.pad(out, 1, mode="constant", constant_values=False)
        out = (
            p[:-2, :-2] | p[:-2, 1:-1] | p[:-2, 2:]
            | p[1:-1, :-2] | p[1:-1, 1:-1] | p[1:-1, 2:]
            | p[2:, :-2] | p[2:, 1:-1] | p[2:, 2:]
        )
    return out


def clean_image(
    image_path: Path,
    boxes: list[dict],
    output_path: Path,
    iterations: int = 160,
    mask_output: Path | None = None,
) -> None:
    im = Image.open(image_path).convert("RGB")
    arr = np.array(im, dtype=np.float32)
    bg_light = np.array(im.filter(ImageFilter.MaxFilter(size=15)), dtype=np.float32)
    bg_dark = np.array(im.filter(ImageFilter.MinFilter(size=11)), dtype=np.float32)

    h_img, w_img = arr.shape[:2]
    full_mask = np.zeros((h_img, w_img), dtype=bool)

    for box in boxes:
        x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
        mode = box.get("mode", "dark_text")
        x0, y0 = max(1, x), max(1, y)
        x1, y1 = min(w_img - 1, x + w), min(h_img - 1, y + h)
        region = arr[y0:y1, x0:x1]
        if mode == "light_text":
            diff = np.max(region - bg_dark[y0:y1, x0:x1], axis=2)
            m = dilate(diff > float(box.get("threshold", 20.0)), iters=int(box.get("dilate", 2)))
        else:
            diff = np.max(bg_light[y0:y1, x0:x1] - region, axis=2)
            m = dilate(diff > float(box.get("threshold", 16.0)), iters=int(box.get("dilate", 2)))
        full_mask[y0:y1, x0:x1] |= m

    res = arr.copy()
    for box in boxes:
        x, y, w, h = int(box["x"]), int(box["y"]), int(box["w"]), int(box["h"])
        x0, y0 = max(1, x), max(1, y)
        x1, y1 = min(w_img - 1, x + w), min(h_img - 1, y + h)
        m = full_mask[y0:y1, x0:x1]
        unmasked = arr[y0:y1, x0:x1][~m]
        if len(unmasked) > 0:
            res[y0:y1, x0:x1][m] = np.median(unmasked, axis=0)

    inner_m = full_mask[1:-1, 1:-1]
    for _ in range(iterations):
        avg = 0.25 * (res[:-2, 1:-1] + res[2:, 1:-1] + res[1:-1, :-2] + res[1:-1, 2:])
        res[1:-1, 1:-1][inner_m] = avg[inner_m]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(res, 0, 255).astype(np.uint8)).save(output_path)

    if mask_output is not None:
        mask_output.parent.mkdir(parents=True, exist_ok=True)
        mask_img = (full_mask.astype(np.uint8) * 255)
        Image.fromarray(mask_img, mode="L").save(mask_output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove text strokes seamlessly via Laplace harmonic diffusion.")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--boxes-json", required=True, type=Path, help="JSON list of {x,y,w,h,mode}")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mask-output", type=Path, default=None, help="Optional binary mask PNG output for audit")
    parser.add_argument("--iterations", type=int, default=160)
    args = parser.parse_args()

    boxes = json.loads(args.boxes_json.read_text(encoding="utf-8"))
    clean_image(
        args.image.resolve(),
        boxes,
        args.output.resolve(),
        args.iterations,
        args.mask_output.resolve() if args.mask_output else None,
    )
    print(f"SEAMLESS_CLEAN_OK|{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
