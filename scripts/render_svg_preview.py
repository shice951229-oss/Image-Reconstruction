#!/usr/bin/env python3
"""Render an SVG file to a pixel-accurate PNG preview using headless Microsoft Edge or Google Chrome."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote


def find_browser() -> Path | None:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def infer_svg_size(svg_path: Path) -> tuple[int, int]:
    head = svg_path.read_text(encoding="utf-8", errors="ignore")[:2000]
    m = re.search(r'viewBox\s*=\s*"[^"]*?\s+([\d.]+)\s+([\d.]+)\s*"', head)
    if m:
        return int(round(float(m.group(1)))), int(round(float(m.group(2))))
    mw = re.search(r'width\s*=\s*"([\d.]+)', head)
    mh = re.search(r'height\s*=\s*"([\d.]+)', head)
    if mw and mh:
        return int(round(float(mw.group(1)))), int(round(float(mh.group(2))))
    return 1024, 682


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an SVG to a PNG preview for visual QA.")
    parser.add_argument("--svg", required=True, type=Path)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    parser.add_argument("--scale", type=float, default=1.0, help="Device scale factor (e.g., 2.0 for HiDPI)")
    args = parser.parse_args()

    svg_path = args.svg.resolve()
    png_path = args.png.resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)

    w, h = infer_svg_size(svg_path)
    if args.width > 0:
        w = args.width
    if args.height > 0:
        h = args.height

    browser = find_browser()
    if browser is None:
        raise SystemExit("No headless Edge or Chrome browser found for SVG preview rendering.")

    file_url = "file:///" + quote(str(svg_path).replace("\\", "/"), safe=":/")
    cmd = [
        str(browser),
        "--headless",
        "--disable-gpu",
        f"--screenshot={str(png_path)}",
        f"--window-size={w},{h}",
        f"--force-device-scale-factor={args.scale}",
        "--hide-scrollbars",
        file_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not png_path.is_file():
        raise SystemExit(f"Headless SVG render failed: {proc.stderr.strip()}")
    print(f"PREVIEW_RENDER_OK|{png_path}|{w}x{h}@{args.scale}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
