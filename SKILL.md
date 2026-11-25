---
name: Image-Reconstruction
description: Zero-cost, publication-grade scientific figure reconstruction into clean, native editable SVG (directly openable in Adobe Illustrator / Inkscape / Figma to save as AI, PDF, EPS, or high-DPI TIFF). Reconstructs frames, gradients, axes, smooth mathematical curves, connectors, flat vector icons, and native subscript/superscript typography in pure SVG code, while seamlessly integrating complex anatomical/photorealistic sub-illustrations via local ROI vector extraction or local tracing, followed by headless PNG rendering and mandatory visual verification. Use when the user asks to reconstruct, vectorize, redraw, or convert a scientific diagram, flowchart, mechanism figure, or roadmap image into editable vector artwork without paid tracing APIs.
---

# Image-Reconstruction

`original image -> pixel/color/text geometry inspection -> pure native SVG code (frames, gradients, curves, arrows, flat icons, native math text) + local vector ROI for complex anatomical art -> headless PNG render -> visual diff & polish -> Illustrator-ready SVG`

This skill produces **clean, semantic, Illustrator-native vector artwork at zero API cost**. Unlike blind whole-image bitmap auto-tracing (which breaks 1 px borders, creates patchy color blocks, and fragments boxes into hundreds of uneditable shards), every structural element is authored as true editable vector geometry (`<rect rx>`, `<linearGradient>`, `<path>` Bezier curves, `<line>`, `<text>` with native `<tspan>` subscripts/superscripts).

## Core Principles

1. **Zero broken borders, zero color patches**: Never rely on whole-image bitmap auto-tracing for boxes, cards, axes, mathematical curves, dashed lines, arrows, or text. Author them directly as clean native SVG primitives.
2. **Zero missing-glyph boxes (`☒`)**: Never use obscure Unicode subscript/superscript codepoints (`ᵢ`, `ₚ`, `ₛ`, `ᵧ`, `₋`, `₀`, `ₘ`, `²`) that standard serif fonts (`Georgia`, `Times New Roman`) lack. Always use standard ASCII/Greek characters (`i`, `p`, `sys`, `state`, `0`, `2+`, `θ`, `μ`, `β`, `π`, `τ`, `λ`, `∝`, `→`, `↔`, `−`, `×`, `·`) styled with native `<tspan font-size="..." dy="...">` vertical offsets and native `<line>` overbars (e.g., for $\bar{w}_\pi$).
3. **Hybrid strategy for complex organic/anatomical illustrations**:
   - **Flat geometric/line icons** (sun, moon, waves, bar charts, targets, gears, calendars, coins, network nodes, flasks, sprouts, clocks, simple brains): draw cleanly as native SVG vector paths.
   - **Complex shaded anatomical/realistic sub-illustrations** (detailed brain gyri, corticospinal tract, spinal cord cross-section, muscle fibers, realistic hands, synapses): keep them strictly isolated in local ROIs via `scripts/trace_local_roi.py` (either extracting pure vector paths from an existing local SVG, tracing the cropped ROI locally with free open-source `vtracer`, or clean local harmonic-inpainted cutout if needed) and wrap each in its own named `<g id="Art_...">` group.
4. **Always close the loop with visual verification**: After generating the SVG, render a 1:1 PNG preview with `scripts/render_svg_preview.py` and visually inspect it with `read_file` against the original image. Fix every spacing, clipping, curve-bound, arrow-fill, or overbar alignment issue before delivering.

## Step-by-Step Workflow

### Step 1: Inspect Original Geometry, Palette, and Text Positions
Run the bundled inspector on the source image:
```bash
python scripts/inspect_image.py --image <original.jpg|png> --output-json <work_dir>/inspection.json
```
This records:
- Exact canvas `width` and `height` (always match the SVG `viewBox="0 0 W H"` to the original canvas).
- Pixel-accurate OCR text bounding boxes (`[x, y, w, h]`) via Windows WinRT OCR (when available) for exact baseline alignment.
- Use `--sample name:x,y` flags (or a short Python snippet) to sample exact Hex colors for headers, gradients, borders, pills, shaded bands, and text fills directly from the source image.

### Step 2: Classify Visual Components (Pure Native vs. Local Hybrid ROI)
Partition the figure into two tiers:
- **Tier 1 (Pure Native SVG Code — 100% of structure)**:
  - Outer cards, rounded rectangles, clipped header gradient bars (`<clipPath>` + `<linearGradient>`).
  - Axes, grid/ceiling dashed lines, shaded bands, smooth mathematical curves (Bezier / sampled sine waves clipped cleanly inside plot axes).
  - Connectors, elbow arrows with rounded corners (`Q`), bidirectional arrows, dividers.
  - Flat icons and all text, labels, legends, and mathematical formulas with native `<tspan>` subscripts/superscripts.
- **Tier 2 (Local Organic/Anatomical ROIs — only when complex shaded illustrations exist)**:
  - Identify tight ROI bounding boxes `[x0, y0, x1, y1]` around each organic sub-illustration.
  - If an anatomical ROI overlaps text, first run `scripts/seamless_inpaint_clean.py` (pixel-level stroke mask + Laplace harmonic diffusion — never flat rectangle filling!) on just that region.
  - Convert or extract each ROI as a clean pure-vector `<g id="Art_...">` using `scripts/trace_local_roi.py`:
    - Mode A (local free tracing): `python scripts/trace_local_roi.py --mode vtracer --image <img.png> --roi x0,y0,x1,y1 --output <roi.svg>`
    - Mode B (extract from existing SVG): `python scripts/trace_local_roi.py --mode extract-svg --svg <existing.svg> --roi x0,y0,x1,y1 --output <roi.svg>`
  - **Important SVG inheritance guard**: When extracting stroke-only `<path>` elements from another SVG whose root `<g>` has `fill="none"`, explicitly add `fill="none"` to every path that has `stroke` and no `fill` (otherwise curved arrows turn into solid black blobs). `trace_local_roi.py` handles this automatically.

### Step 3: Author Structured, Illustrator-Ready SVG
Read [references/svg-illustrator-best-practices.md](references/svg-illustrator-best-practices.md) before authoring the SVG.
Key structure rules:
- Organize into semantic top-level `<g id="Layer_...">` groups (`Layer_Background`, `Layer_Title`, `Layer_Connectors`, `Layer_PanelA`, etc.) so Adobe Illustrator exposes a clean Layer/Group hierarchy.
- Use SVG 1.1 compatible gradients, `<clipPath>` for rounded header bars, explicit `stroke-linecap` / `stroke-linejoin`, and `Georgia, 'Times New Roman', serif` (or `Arial, Helvetica, sans-serif` if the source is sans-serif).
- Keep all `<text>` live and editable (never convert text to outlines).

### Step 4: Render Preview and Perform Strict Visual QA
Render the SVG to PNG at exact canvas dimensions:
```bash
python scripts/render_svg_preview.py --svg <output.svg> --png <preview.png> --width <W> --height <H>
```
Then open `<preview.png>` with `read_file` and compare every region against the original image:
1. Check every text line for clipping against card borders or overlap with adjacent columns/curves.
2. Check mathematical equations, subscripts, superscripts, Greek symbols, and overbars (`w̄`) for exact alignment and zero `☒` missing glyphs.
3. Check plot curves against axis bounds (clip curves cleanly inside plot boxes where needed).
4. Check extracted anatomical ROIs for stray background fills or missing `fill="none"` on curved strokes.
5. Check all borders, dashed lines, arrows, and rounded corners for continuity and color fidelity.

Iterate on the SVG and re-render until the visual check passes cleanly.

### Step 5: Deliver
Provide clickable file links to:
1. The final native editable `.svg` (note that the user can drag/open it directly in Adobe Illustrator to edit any box/curve/text and save as `.ai`, `.pdf`, `.eps`, or high-DPI `.tiff`).
2. The verified `.png` preview.
3. A brief summary of layers, editable text/math formatting, and zero API cost.
