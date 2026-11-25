# Illustrator-Ready Native SVG Best Practices

Follow these conventions so generated SVGs open cleanly in **Adobe Illustrator**, **Inkscape**, **Figma**, and modern browsers with identical rendering and effortless editing.

## 1. Document Root & Coordinate System
- Match the source image aspect ratio exactly:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <svg xmlns="http://www.w3.org/2000/svg" width="1024" height="682" viewBox="0 0 1024 682">
  ```
- Include an explicit `<g id="Layer_Background"><rect x="0" y="0" width="1024" height="682" fill="#FFFFFF"/></g>` so artboard exports have a clean white backing.

## 2. Semantic Layering for Easy Editing
- Group major panels/stages into named `<g id="Layer_...">` containers in back-to-front paint order:
  1. `Layer_Background`
  2. `Layer_Connectors` (arrows between cards — keep behind card borders or cleanly touching edges)
  3. `Layer_PanelA` / `Layer_Stage1` / ...
  4. `Layer_Title`
- Inside each card with a colored header bar, avoid drawing an unclipped header rectangle that pokes past rounded corners. Instead:
  ```xml
  <clipPath id="clipCard"><rect x="12" y="56" width="455" height="244" rx="11" ry="11"/></clipPath>
  ...
  <rect x="12" y="56" width="455" height="244" rx="11" ry="11" fill="#FFFFFF"/>
  <g clip-path="url(#clipCard)">
    <rect x="12" y="56" width="455" height="28" fill="url(#gradHdr)"/>
  </g>
  <rect x="12" y="56" width="455" height="244" rx="11" ry="11" fill="none" stroke="#85A2BF" stroke-width="1.2"/>
  ```

## 3. Publication-Grade Math, Subscripts & Superscripts (Zero `☒` Glyphs)
- **Never** use Unicode subscript/superscript letters like `ᵢ`, `ₚ`, `ₛ`, `ᵧ`, `ₘ`, `₀`, `₋`, `²` inside Georgia/Times New Roman — Illustrator displays missing glyphs as `☒`.
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
- Safe symbols well-supported by Georgia & Times New Roman:
  - Greek: `α`, `β`, `γ`, `δ`, `θ`, `λ`, `μ`, `π`, `σ`, `τ`, `ω`, `Δ`, `Σ` (`∑`)
  - Operators/Arrows: `×`, `·`, `±`, `−` (minus `\u2212`), `–` (en-dash `\u2013`), `∝`, `→`, `←`, `↔`, `≥`, `≤`, `½`, `•`, `…`

## 4. Curves, Plots & Connectors
- Clip plot curves cleanly inside the plot region `<clipPath id="clipPlot">` so dashed troughs never spill below the X-axis.
- For periodic physiological waves (e.g., μ/β oscillations), compute dense smooth polyline/path coordinates via `math.sin` in Python rather than hand-guessing control points.
- For right-angle elbow connectors, add small quadratic rounded bends (`Q`) so transitions look refined and publication-ready.
- Avoid SVG `<marker>` for arrowheads when targeting Adobe Illustrator — Illustrator sometimes mishandles marker scaling or color inheritance. Draw explicit `<polygon>` arrowheads instead so color, angle, and size are 100% deterministic.

## 5. Integrating Extracted Vector Sub-Illustrations & Embedded 3D Backgrounds
- When importing paths from another SVG, check every `<path>` with a `stroke` and no explicit `fill`: always attach `fill="none"` so curved stroke arrows do not render as solid black shapes.
- Filter out bounding-box-sized solid white background rectangles so sub-illustrations blend seamlessly over tinted or gradient cards.
- **CRITICAL Adobe Illustrator SVG 1.1 rule for `<image>`**: When embedding a raster/3D background layer (`data:image/png;base64,...`), **ALWAYS** declare `xmlns:xlink="http://www.w3.org/1999/xlink"` on `<svg>` and use **`xlink:href="data:image/png;base64,..."`** (NEVER bare SVG 2 `href="..."`). Illustrator ignores bare `href` on `<image>` and pops up `"Could not find linked file ''"`.
