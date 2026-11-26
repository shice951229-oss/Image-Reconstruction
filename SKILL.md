---
name: Image-Reconstruction
description: Zero-cost, publication-grade scientific figure and 3D cover reconstruction into clean, native editable SVG (directly openable in Adobe Illustrator / Inkscape / Figma with zero missing-link or font popups). Supports dual-track architecture: (1) PureVector-2D for 2D scientific diagrams, flowcharts, mechanism figures, and plots (100% pure native SVG geometry, math subscripts/superscripts, and local ROI vector tracing via vtracer), and (2) CineHybrid-3D for 3D rendered journal covers, volumetric lighting artwork, and microscopy illustrations (stroke-masked harmonic inpainting + sd-turbo strength=0.01 lossless 3D background regeneration via SVG 1.1 xlink:href + filter-free soft gradient vector arrows + single-font refined editable typography), followed by headless PNG rendering and mandatory 1:1 visual QA.
---

# Image-Reconstruction

This skill produces **clean, semantic, Illustrator-native editable SVG artwork at zero API cost** using a **Dual-Track Architecture**:

1. **Track A — `PureVector-2D`（纯原生矢量重建模式，默认用于 2D 科研插图）**:
   - **Target**: Scientific diagrams, flowcharts, mechanism schematics, mathematical curve plots, and multi-panel roadmaps.
   - **Pipeline**:
     `original image -> pixel/color/OCR inspection -> 100% pure native SVG code (frames, gradients, Bezier/sine curves, arrows, flat icons, native <tspan> math text) + local vtracer vector ROI for small anatomical art -> headless PNG render -> 1:1 visual QA -> Illustrator-ready pure vector SVG`
2. **Track B — `CineHybrid-3D`（3D 光影无损混合分层模式，专用于 3D 渲染期刊封面与连续体积光影插画）**:
   - **Target**: 3D rendered journal covers (e.g., *Nature* / *Cell* / *Science* covers), continuous volumetric lighting, bokeh depth-of-field blur, glowing cells, and micro-particle scenes where whole-image polygon vectorization (`vtracer`) would create "oil-painting" color-band quantization.
   - **Pipeline**:
     `original 3D image -> inspect OCR/arrow boxes -> surgical stroke-masked Laplace harmonic inpainting -> local sd-turbo (strength=0.01, steps=100, CUDA) lossless 3D regeneration -> SVG 1.1 xlink:href Base64 3D layer + filter-free dual-stroke gradient vector arrows + single-font slender live <text> -> headless PNG render -> 1:1 visual QA -> Illustrator-ready layered hybrid SVG`

---

## Core Principles

1. **Choose the right track for the visual physics**:
   - Use **`PureVector-2D`** whenever the figure is built from cards, frames, plots, curves, arrows, flat icons, or isolated anatomical sub-illustrations (zero `<image>` nodes).
   - Use **`CineHybrid-3D`** whenever the scene is a continuous 3D volumetric render or journal cover where preserving sub-pixel bokeh, glow, and micro-particles without posterization is essential, while all text, mastheads, and overlay arrows must be native editable vectors.
2. **Zero broken borders, zero color patches (`PureVector-2D`)**: Never rely on whole-image bitmap auto-tracing for boxes, cards, axes, mathematical curves, dashed lines, arrows, or text. Author them directly as clean native SVG primitives (`<rect rx>`, `<linearGradient>`, `<path>`, `<line>`, `<text>`).
3. **Zero missing-glyph boxes (`☒`)**: Never use obscure Unicode subscript/superscript codepoints (`ᵢ`, `ₚ`, `ₛ`, `ᵧ`, `₋`, `₀`, `ₘ`, `²`) that standard fonts lack. Always use standard ASCII/Greek characters (`i`, `p`, `sys`, `state`, `0`, `2+`, `θ`, `μ`, `β`, `π`, `τ`, `λ`, `γ`, `∝`, `→`, `↔`, `−`, `×`, `·`) styled with native `<tspan font-size="..." dy="...">` vertical offsets and native `<line>` overbars (e.g., for $\bar{w}_\pi$).
4. **Zero Adobe Illustrator popup dialogs or hidden layers**:
   - **No missing-link popup**: When embedding a `CineHybrid-3D` 3D layer, always declare `xmlns:xlink="http://www.w3.org/1999/xlink"` on `<svg>` and use `xlink:href="data:image/png;base64,..."` (never bare SVG 2 `href`).
   - **No disappearing text/arrow layers**: Never attach `<feDropShadow>` or `<filter>` to `<g>` groups (Illustrator hides them). Use filter-free dual-stroke semi-transparent glow (`stroke-opacity="0.22"` wide under-stroke + slender core stroke).
   - **No missing-font popup**: Never put uninstalled macOS fonts like `'Helvetica Neue'` in `font-family`. Always use a single installed Windows font name (`font-family="Segoe UI"` for sans-serif, `font-family="Georgia"` for serif).
5. **Always close the loop with visual verification**: After generating any SVG, render a 1:1 PNG preview with `scripts/render_svg_preview.py` and visually inspect it with `read_file` against the original image.

---

## Track A Workflow: `PureVector-2D`（2D 科研机制图 / 流程图 / 曲线图纯矢量重建）

### Step A1: Inspect Original Geometry, Palette, and Text Positions
```bash
python scripts/inspect_image.py --image <original.jpg|png> --output-json <work_dir>/inspection.json
```
- Records exact canvas `width` and `height` (match `viewBox="0 0 W H"`), OCR bounding boxes (`[x, y, w, h]`), and sampled Hex colors (`--sample name:x,y`).

### Step A2: Partition into Tier 1 (Pure Native Code) & Tier 2 (Local Vector ROIs)
- **Tier 1 (Pure Native SVG Code — 100% of structure)**:
  - Outer cards, rounded rectangles, clipped header gradient bars (`<clipPath>` + `<linearGradient>`).
  - Axes, grid/ceiling dashed lines, shaded bands, smooth mathematical curves (Bezier / sampled sine waves clipped cleanly inside plot axes).
  - Connectors, elbow arrows with rounded corners (`Q`), bidirectional arrows, dividers, flat icons, and all live `<text>` / `<tspan>` formulas.
- **Tier 2 (Local Organic/Anatomical ROIs — only when complex shaded sub-illustrations exist)**:
  - Identify tight ROI bounding boxes `[x0, y0, x1, y1]` around each organic sub-illustration.
  - If text overlaps the ROI, clean just that region first with `scripts/seamless_inpaint_clean.py --mask-output <mask.png>`.
  - Convert or extract each ROI as a clean pure-vector `<g id="Art_...">` using `scripts/trace_local_roi.py`:
    - Local `vtracer`: `python scripts/trace_local_roi.py --mode vtracer --image <img.png> --roi x0,y0,x1,y1 --output <roi.svg>`
    - Extract from existing SVG: `python scripts/trace_local_roi.py --mode extract-svg --svg <existing.svg> --roi x0,y0,x1,y1 --output <roi.svg>`
  - **SVG inheritance guard**: Always ensure stroke-only `<path>` elements carry explicit `fill="none"`.

### Step A3: Author Structured Pure-Vector SVG & Visual QA
- Follow [references/svg-illustrator-best-practices.md](references/svg-illustrator-best-practices.md).
- Render 1:1 preview via `scripts/render_svg_preview.py` and verify zero text clipping, zero `☒` glyphs, and exact curve bounds.

---

## Track B Workflow: `CineHybrid-3D`（3D 渲染期刊封面 / 体积光影无损混合分层重建）

Read [references/neural-regeneration-protocol.md](references/neural-regeneration-protocol.md) and [references/svg-illustrator-best-practices.md](references/svg-illustrator-best-practices.md) when running `CineHybrid-3D`.

### Step B1: Coordinate Inspection & Surgical Stroke-Only Harmonic Inpainting
1. Run `scripts/inspect_image.py` to locate all text labels, masthead text, and overlay arrows.
2. Define tight surgical bounding boxes in `boxes_clean.json` (`mode: "light_text"` for bright labels/arrows on dark 3D backgrounds, or `"dark_text"` on bright backgrounds) so adjacent 3D structures (e.g., cell receptors or spheres) are never touched:
   - **Split multi-line labels into tight single-line boxes** whenever curved anatomical contours, medallions, or pointer lines sit next to shorter lines (keep ~2–3 px vertical margin above/below glyphs so anti-aliased bottom-row pixels never sit on the Laplace boundary and bleed inward).
   - **Elevate `threshold` to `55–65` with `dilate: 1`** on light-background shaded anatomical rims (instead of default `16–22, dilate: 2`) so only dark text strokes are masked without smudging pale grey/pink contour lines.
3. Run `neural_regeneration.py prepare` (which invokes `seamless_inpaint_clean.py` with 240 Laplace harmonic diffusion iterations and exports `text_mask.png`), and visually inspect `<job_dir>/cleaned.png` (plus zoomed crops of dense anatomical rims) before running `sd-turbo`:
   ```bash
   python scripts/neural_regeneration.py prepare --job-dir <job_dir> --image <original.jpg|png> --boxes-json <boxes_clean.json> --ocr-baseline-json <inspection.json> --iterations 240
   ```

### Step B2: Ultra-Low-Strength (`0.01`) Local `sd-turbo` 3D Regeneration & Automated QA
Run a single deterministic ultra-low-strength pass through local `stabilityai/sd-turbo` (`strength=0.01`, `steps=100` so `int(steps * strength) == 1`, `guidance_scale=0.0`, empty prompt `""`, reversible right/bottom edge padding to multiple of 8 and exact crop-back):
```bash
python scripts/neural_regeneration.py run --job-dir <job_dir> --backend local_diffusers --mode diffusion_img2img --model-id stabilityai/sd-turbo --strength 0.01 --steps 100 --seed 2026 --device auto
python scripts/neural_regeneration.py qa --job-dir <job_dir> --min-edge-corr 0.85
```
- This reconstructs a 100% clean, non-posterized 3D background (`<job_dir>/reconstructed.png`) with `mean_abs_rgb_delta < 5.0` and `edge_correlation >= 0.85`, preserving fine micro-structures, bokeh glow, and micro-particles.
- **Optional stronger texture re-synthesis (`strength=0.1`)**: When stronger neural texture smoothing/re-synthesis is explicitly desired, use `--strength 0.1 --steps 20` (`2` denoising steps, within the `<= 0.20` conservative cap). Note that `strength=0.1` softens fine high-frequency details (`mean_abs_rgb_delta ≈ 6.9`, `edge_correlation ≈ 0.79`), so run `qa` with `--min-edge-corr 0.75` if selecting this preset.
- If local Diffusers/models are unavailable or fail, automatically fall back to `<job_dir>/cleaned.png`.

### Step B3: Illustrator SVG 1.1 Layered Assembly (`compose-hybrid-svg` or Custom SVG)
Assemble the 4 semantic Illustrator layers (either via `python scripts/neural_regeneration.py compose-hybrid-svg --background-png <reconstructed.png> --spec-json <spec.json> --output-svg <output.svg>` or direct SVG authoring):
1. **`<g id="Layer_3D_Artwork">`**: Embed `reconstructed.png` as Base64 using SVG 1.1 `xmlns:xlink="http://www.w3.org/1999/xlink"` and `xlink:href="data:image/png;base64,..."`.
2. **`<g id="Layer_Vector_Arrows">` / `<g id="Layer_Cytokine_Arrows">`**: Author multi-stop `userSpaceOnUse` opacity gradients (`stop-opacity="0.0"` at tail -> `0.55` at 35% -> `0.92` at 80% -> `1.0` at tip) + dual-stroke soft glow (`stroke-opacity="0.22"` width `6.5` under-stroke + width `2.7` core stroke + `<polygon>` head). **Zero `<feDropShadow>` filters**.
3. **`<g id="Layer_Labels">`**: Author refined slender `<text>` labels (`font-family="Segoe UI"`, weights `400`/`500`/`600`, exact rotation transforms such as `transform="rotate(-26 cx cy)"`).
4. **`<g id="Layer_Masthead">`**: Author journal masthead `<text>` (`font-family="Georgia"`, weight `400`, exact letter-spacing).

### Step B4: Headless 1:1 Visual QA & Delivery
```bash
python scripts/render_svg_preview.py --svg <output.svg> --png <preview.png> --width <W> --height <H>
```
Inspect `<preview.png>` with `read_file` against the original 3D image to verify:
- Zero residual text/arrow ghosts on the 3D background.
- Natural long-fade tail and slender weight on all gradient vector arrows.
- Crisp, slender typography matching original positions and angles.
- Deliver clickable links to the final `.svg` and `.png` preview.
