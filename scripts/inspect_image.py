#!/usr/bin/env python3
"""Inspect a source figure: dimensions, exact hex color samples, and Windows OCR text bounding boxes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image


def run_windows_ocr(image_path: Path) -> list[dict]:
    if sys.platform != "win32":
        return []
    ps_script = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
Function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync("{str(image_path)}")) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$items = @()
foreach ($line in $result.Lines) {{
    $minX = ($line.Words | ForEach-Object {{ $_.BoundingRect.X }} | Measure-Object -Minimum).Minimum
    $minY = ($line.Words | ForEach-Object {{ $_.BoundingRect.Y }} | Measure-Object -Minimum).Minimum
    $maxX = ($line.Words | ForEach-Object {{ $_.BoundingRect.X + $_.BoundingRect.Width }} | Measure-Object -Maximum).Maximum
    $maxY = ($line.Words | ForEach-Object {{ $_.BoundingRect.Y + $_.BoundingRect.Height }} | Measure-Object -Maximum).Maximum
    $items += [ordered]@{{
        bbox = @([int]$minX, [int]$minY, [int]($maxX - $minX), [int]($maxY - $minY))
        text = $line.Text
    }}
}}
$items | ConvertTo-Json -Depth 4 -Compress
"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        parsed = json.loads(proc.stdout.strip())
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect image dimensions, sample hex colors, and measure OCR boxes.")
    parser.add_argument("--image", required=True, type=Path, help="Input image path")
    parser.add_argument("--sample", action="append", default=[], help="Sample point as name:x,y (repeatable)")
    parser.add_argument("--no-ocr", action="store_true", help="Skip OCR text box extraction")
    parser.add_argument("--output-json", type=Path, help="Optional path to save inspection JSON")
    args = parser.parse_args()

    img_path = args.image.resolve()
    im = Image.open(img_path).convert("RGB")
    w, h = im.size

    colors = {}
    for spec in args.sample:
        if ":" in spec:
            name, coords = spec.split(":", 1)
        else:
            name, coords = spec, spec
        x_str, y_str = coords.split(",", 1)
        x, y = max(0, min(w - 1, int(x_str))), max(0, min(h - 1, int(y_str)))
        r, g, b = im.getpixel((x, y))
        colors[name] = {"x": x, "y": y, "hex": f"#{r:02X}{g:02X}{b:02X}"}

    ocr_lines = [] if args.no_ocr else run_windows_ocr(img_path)

    report = {
        "image": str(img_path),
        "width": w,
        "height": h,
        "colors": colors,
        "ocr_line_count": len(ocr_lines),
        "ocr_lines": ocr_lines,
    }

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
