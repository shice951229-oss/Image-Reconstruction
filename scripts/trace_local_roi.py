#!/usr/bin/env python3
"""Extract or locally trace complex organic/anatomical sub-illustrations (ROIs) into clean SVG <g> fragments."""

from __future__ import annotations

import argparse
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image

TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


def path_bbox(d: str):
    tokens = TOKEN_RE.findall(d)
    if not tokens:
        return None
    i = 0
    cmd = ""
    cx = cy = sx = sy = 0.0
    xs, ys = [], []

    def f():
        nonlocal i
        val = float(tokens[i])
        i += 1
        return val

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd in ("Z", "z"):
                cx, cy = sx, sy
                continue
        if cmd == "M":
            cx, cy = f(), f(); sx, sy = cx, cy; xs.append(cx); ys.append(cy); cmd = "L"
        elif cmd == "m":
            cx += f(); cy += f(); sx, sy = cx, cy; xs.append(cx); ys.append(cy); cmd = "l"
        elif cmd == "L":
            cx, cy = f(), f(); xs.append(cx); ys.append(cy)
        elif cmd == "l":
            cx += f(); cy += f(); xs.append(cx); ys.append(cy)
        elif cmd == "H":
            cx = f(); xs.append(cx); ys.append(cy)
        elif cmd == "h":
            cx += f(); xs.append(cx); ys.append(cy)
        elif cmd == "V":
            cy = f(); xs.append(cx); ys.append(cy)
        elif cmd == "v":
            cy += f(); xs.append(cx); ys.append(cy)
        elif cmd == "C":
            x1, y1, x2, y2, cx, cy = f(), f(), f(), f(), f(), f()
            xs.extend([x1, x2, cx]); ys.extend([y1, y2, cy])
        elif cmd == "c":
            x1, y1, x2, y2, dx, dy = f(), f(), f(), f(), f(), f()
            xs.extend([cx+x1, cx+x2, cx+dx]); ys.extend([cy+y1, cy+y2, cy+dy]); cx += dx; cy += dy
        elif cmd in ("S", "Q"):
            x1, y1, cx, cy = f(), f(), f(), f(); xs.extend([x1, cx]); ys.extend([y1, cy])
        elif cmd in ("s", "q"):
            x1, y1, dx, dy = f(), f(), f(), f()
            xs.extend([cx+x1, cx+dx]); ys.extend([cy+y1, cy+dy]); cx += dx; cy += dy
        elif cmd == "T":
            cx, cy = f(), f(); xs.append(cx); ys.append(cy)
        elif cmd == "t":
            cx += f(); cy += f(); xs.append(cx); ys.append(cy)
        elif cmd == "A":
            _, _, _, _, _, cx, cy = f(), f(), f(), f(), f(), f(), f(); xs.append(cx); ys.append(cy)
        elif cmd == "a":
            _, _, _, _, _, dx, dy = f(), f(), f(), f(), f(), f(), f(); cx += dx; cy += dy; xs.append(cx); ys.append(cy)
        else:
            break
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def elem_bbox(el):
    tag = el.tag.split("}")[-1]
    if tag == "path" and el.get("d"):
        return path_bbox(el.get("d"))
    if tag == "circle":
        cx, cy, r = float(el.get("cx", 0)), float(el.get("cy", 0)), float(el.get("r", 0))
        return (cx - r, cy - r, cx + r, cy + r)
    if tag == "ellipse":
        cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
        rm = max(float(el.get("rx", 0)), float(el.get("ry", 0)))
        return (cx - rm, cy - rm, cx + rm, cy + rm)
    if tag == "rect":
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        return (x, y, x + float(el.get("width", 0)), y + float(el.get("height", 0)))
    return None


def serialize_elem(el) -> str:
    tag = el.tag.split("}")[-1]
    attrs = []
    has_fill = "fill" in el.attrib
    has_stroke = "stroke" in el.attrib
    for k, v in el.attrib.items():
        if k.startswith("{") or k == "vector-effect":
            continue
        attrs.append(f'{k}="{v}"')
    if has_stroke and not has_fill:
        attrs.append('fill="none"')
    return f"<{tag} {' '.join(attrs)}/>"


def extract_from_svg(svg_path: Path, roi: tuple[float, float, float, float], group_id: str) -> str:
    rx0, ry0, rx1, ry1 = roi
    root = ET.parse(svg_path).getroot()
    items = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("path", "circle", "ellipse", "rect"):
            continue
        bb = elem_bbox(el)
        if not bb:
            continue
        x0, y0, x1, y1 = bb
        if x0 >= rx0 and y0 >= ry0 and x1 <= rx1 and y1 <= ry1:
            if (x1 - x0) > (rx1 - rx0) * 0.90 and (y1 - y0) > (ry1 - ry0) * 0.90:
                continue
            items.append("  " + serialize_elem(el))
    return f'<g id="{group_id}">\n' + "\n".join(items) + "\n</g>\n"


def trace_roi_vtracer(image_path: Path, roi: tuple[int, int, int, int], group_id: str, bg_threshold: int = 245) -> str:
    try:
        import vtracer
    except ImportError as exc:
        raise SystemExit(
            "Local open-source 'vtracer' is not installed. Run `pip install vtracer` or use --mode extract-svg."
        ) from exc

    rx0, ry0, rx1, ry1 = roi
    im = Image.open(image_path).convert("RGBA")
    crop = im.crop((rx0, ry0, rx1, ry1))

    # Strip near-white background around the cropped anatomical ROI for seamless placement
    if bg_threshold > 0:
        px = crop.load()
        cw, ch = crop.size
        for y in range(ch):
            for x in range(cw):
                r, g, b, a = px[x, y]
                if r >= bg_threshold and g >= bg_threshold and b >= bg_threshold:
                    px[x, y] = (r, g, b, 0)

    with tempfile.TemporaryDirectory() as tmp:
        crop_png = Path(tmp) / "roi.png"
        traced_svg = Path(tmp) / "roi.svg"
        crop.save(crop_png)
        if hasattr(vtracer, "convert_file") and hasattr(vtracer, "Config"):
            cfg = vtracer.Config(
                hierarchical="stacked",
                mode="spline",
                filter_speckle=4,
                color_precision=6,
                layer_difference=16,
                corner_threshold=60,
                length_threshold=4.0,
                max_iterations=10,
                splice_threshold=45,
                path_precision=2,
            )
            vtracer.convert_file(str(crop_png), str(traced_svg), cfg)
        elif hasattr(vtracer, "convert_image_to_svg_py"):
            vtracer.convert_image_to_svg_py(
                str(crop_png),
                str(traced_svg),
                colormode="color",
                hierarchical="stacked",
                mode="spline",
                filter_speckle=4,
                color_precision=6,
                layer_difference=16,
                corner_threshold=60,
                length_threshold=4.0,
                max_iterations=10,
                splice_threshold=45,
                path_precision=2,
            )
        else:
            raise SystemExit("Unsupported vtracer API version.")
        root = ET.parse(traced_svg).getroot()
        items = []
        for el in root:
            tag = el.tag.split("}")[-1]
            if tag in ("path", "circle", "ellipse", "rect", "polygon"):
                items.append("  " + serialize_elem(el))
    return f'<g id="{group_id}" transform="translate({rx0},{ry0})">\n' + "\n".join(items) + "\n</g>\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract or locally trace an anatomical ROI into a clean SVG <g>.")
    parser.add_argument("--mode", choices=["extract-svg", "vtracer"], required=True)
    parser.add_argument("--svg", type=Path, help="Existing vector SVG (for extract-svg mode)")
    parser.add_argument("--image", type=Path, help="Source raster image (for vtracer mode)")
    parser.add_argument("--roi", required=True, help="Bounding box as x0,y0,x1,y1")
    parser.add_argument("--group-id", default="Art_ROI", help="SVG <g> id")
    parser.add_argument("--bg-threshold", type=int, default=245, help="Near-white cutoff for vtracer transparency (0 disables)")
    parser.add_argument("--output", required=True, type=Path, help="Output SVG fragment path")
    args = parser.parse_args()

    x0, y0, x1, y1 = [float(v) for v in args.roi.split(",")]
    if args.mode == "extract-svg":
        if not args.svg:
            raise SystemExit("--svg is required for extract-svg mode")
        frag = extract_from_svg(args.svg.resolve(), (x0, y0, x1, y1), args.group_id)
    else:
        if not args.image:
            raise SystemExit("--image is required for vtracer mode")
        frag = trace_roi_vtracer(args.image.resolve(), (int(x0), int(y0), int(x1), int(y1)), args.group_id, args.bg_threshold)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(frag, encoding="utf-8")
    print(f"WROTE_ROI_GROUP|{args.output}|elements={frag.count('<') - 2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
