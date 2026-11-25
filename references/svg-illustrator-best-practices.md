# Illustrator-Ready Native SVG Best Practices

Follow these conventions so generated SVGs open cleanly in **Adobe Illustrator**, **Inkscape**, **Figma**, and modern browsers with identical rendering, zero warning dialogs, and effortless layer editing.

## 1. Dual-Track Architecture (`PureVector-2D` vs. `CineHybrid-3D`)
- **Track A (`PureVector-2D` — Default for 2D scientific diagrams, flowcharts, mechanism figures, and plots)**:
  - 100% pure vector geometry (`<rect>`, `<path>`, `<line>`, `<polygon>`, `<linearGradient>`, `<clipPath>`, `<text>`/`<tspan>`).
  - Complex shaded anatomical sub-illustrations are isolated in tight ROIs and converted to vector `<g id="Art_...">` groups via `scripts/trace_local_roi.py` (`vtracer`).
  - Contains **zero `<image>` raster nodes**.
- **Track B (`CineHybrid-3D` — Dedicated to 3D rendered journal covers, volumetric lighting, and microscopy art)**:
  - Whole-image polygon tracing (`vtracer`) quantizes continuous 3D volumetric lighting, bokeh depth-of-field blur, and micro-particles into posterized "oil-painting" bands.
  - Instead, `CineHybrid-3D` separates the figure into:
    1. `Layer_3D_Artwork`: Stroke-masked harmonic inpainted + local `sd-turbo (strength=0.01, steps=100)` lossless 3D background embedded via SVG 1.1 `xlink:href="data:image/png;base64,..."`.
    2. `Layer_Vector_Arrows` / `Layer_Cytokine_Arrows`: Filter-free dual-stroke `userSpaceOnUse` multi-stop opacity gradient vector arrows.
    3. `Layer_Labels` & `Layer_Masthead`: Slender live editable `<text>` using single installed Windows system font names.

## 2. Document Root & Coordinate System
- Match the source image aspect ratio and pixel dimensions exactly:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1024" height="682" viewBox="0 0 1024 682">
  ```
- For `PureVector-2D` diagrams, include an explicit `<g id="Layer_Background"><rect x="0" y="0" width="1024" height="682" fill="#FFFFFF"/></g>`.

## 3. Semantic Layering & Card Clipping
- Group major panels/stages into named `<g id="Layer_...">` containers in back-to-front paint order (`Layer_Background` / `Layer_3D_Artwork`, `Layer_Connectors` / `Layer_Vector_Arrows`, `Layer_PanelA`, `Layer_Labels`, `Layer_Title` / `Layer_Masthead`).
- Inside each card with a colored header bar, clip the header rectangle inside `<clipPath>` so it never pokes past rounded corners:
  ```xml
  <clipPath id="clipCard"><rect x="12" y="56" width="455" height="244" rx="11" ry="11"/></clipPath>
  <rect x="12" y="56" width="455" height="244" rx="11" ry="11" fill="#FFFFFF"/>
  <g clip-path="url(#clipCard)">
    <rect x="12" y="56" width="455" height="28" fill="url(#gradHdr)"/>
  </g>
  <rect x="12" y="56" width="455" height="244" rx="11" ry="11" fill="none" stroke="#85A2BF" stroke-width="1.2"/>
  ```

## 4. Publication-Grade Math, Subscripts & Superscripts (Zero `☒` Glyphs)
- **Never** use Unicode subscript/superscript letters like `ᵢ`, `ₚ`, `ₛ`, `ᵧ`, `ₘ`, `₀`, `₋`, `²` — Illustrator displays missing glyphs as `☒`.
- **Always** use standard ASCII/Greek characters with `<tspan>` baseline shifts (`dy`), resetting the baseline immediately after (`dy="-..."`):
  - Subscript:
    ```xml
    <tspan font-style="italic">S</tspan><tspan font-style="italic" font-size="9.5" dy="2.5">sys</tspan><tspan dy="-2.5">)</tspan>
    ```
  - Superscript:
    ```xml
    Mg<tspan font-size="6.8" dy="-3">2+</tspan><tspan dy="3"> unblock</tspan>
    ```
  - Overbar (e.g., $\bar{w}_\pi$): render a crisp native `<line>` directly above the italic `w`, and visually verify its exact horizontal alignment on the rendered PNG preview.

## 5. Adobe Illustrator Zero-Popup & Zero-Hidden-Layer Guardrails
1. **Zero Missing-Link Dialog (`无法找到链接的文件 ''`)**:
   - Adobe Illustrator's SVG importer follows SVG 1.1 and fails to parse bare SVG 2 `href="data:image/png;base64,..."` on `<image>`, popping up an empty missing-file warning.
   - Always declare `xmlns:xlink="http://www.w3.org/1999/xlink"` on the root `<svg>` tag and use `xlink:href="data:image/png;base64,..."`.
2. **Zero Disappearing Layers (Ban `<feDropShadow>` & SVG 2 `<filter>`)**:
   - Adobe Illustrator ignores or completely hides `<g>` layers that reference `<feDropShadow>` filters.
   - To create soft glowing arrows in `CineHybrid-3D`, use **filter-free dual-stroke multi-stop opacity gradients** (`gradientUnits="userSpaceOnUse"`, `stop-opacity` from `0.0` -> `0.55` -> `0.92` -> `1.0`) with a wide soft under-stroke (`stroke-width="6.5" stroke-opacity="0.22"`) and a slender core stroke (`stroke-width="2.7"`), topped with an explicit `<polygon>` arrowhead.
3. **Zero Missing-Font Dialog (`Helvetica Neue: 出现未知问题`)**:
   - Adobe Illustrator does **not** evaluate CSS font fallback chains like `font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif"` like a browser; if any listed font (`Helvetica Neue`) is absent on Windows, Illustrator raises a font error dialog.
   - Always specify a **single installed Windows system font name**:
     - Sans-serif labels: `font-family="Segoe UI"` (or `font-family="Arial"`) with refined weights (`400`, `500`, `600`).
     - Serif mastheads / formulas: `font-family="Georgia"` (or `font-family="Times New Roman"`).
4. **Stroke-Only Path Inheritance Guard**:
   - When importing paths from another SVG, check every `<path>` with a `stroke` and no explicit `fill`: always attach `fill="none"` so curved stroke arrows do not render as solid black shapes.
