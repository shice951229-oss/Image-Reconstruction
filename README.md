# Image-Reconstruction

**Zero-cost, publication-grade scientific figure reconstruction into clean, native editable SVG** — directly openable in **Adobe Illustrator**, **Inkscape**, or **Figma** to edit and export as `.ai`, `.pdf`, `.eps`, or high-DPI `.tiff`.

**零费用、出版级科研插图原生矢量重建 Skill** —— 无需任何付费位图描摹 API，直接生成结构清晰、图层规范、文字与公式原生可编辑的 SVG 文件，拖入 **Adobe Illustrator** 即可秒开编辑并导出投稿级 `.ai` / `.pdf` / `.eps` / 600 DPI `.tiff`。

---

## Why Image-Reconstruction? / 为什么需要它？

Traditional bitmap auto-tracing APIs (e.g., whole-image vectorizers) often fail on scientific figures:
- **Broken 1 px borders & dashed lines** (thin gray frames get merged into the background)
- **Patchy color blocks** (gradient cards break into uneven rectangular shards)
- **Uneditable geometry** (a single rounded card becomes dozens of fragmented paths)
- **Missing-glyph boxes (`☒`)** when obscure Unicode subscripts/superscripts are used
- **Per-image API fees**

**Image-Reconstruction** solves all of these with a **Hybrid Native-Vector Architecture** at **$0 cost**:
1. **Pure Native SVG Structure (Tier 1)**: Cards (`<rect rx>`), linear gradients (`<linearGradient>`), clipped headers (`<clipPath>`), axes, smooth mathematical curves (Bezier / sine waves), connectors, arrows, flat icons, and live editable typography are authored directly in clean semantic SVG code.
2. **Zero Missing Glyphs**: Uses standard ASCII/Greek characters with native `<tspan font-size dy>` subscripts/superscripts and vector overbars (`w̄`) — never produces `☒` in Adobe Illustrator.
3. **Free Local Hybrid ROI Tracing (Tier 2)**: Complex shaded anatomical or organic sub-illustrations (e.g., brain gyri, corticospinal tract, spinal cord, muscle, synapses) are cropped into tight ROIs and vectorized locally with open-source [`vtracer`](https://github.com/visioncortex/vtracer) (or extracted from existing SVGs with automatic `fill="none"` preservation), then embedded as named `<g id="Art_...">` groups.
4. **Seamless Stroke-Masked Inpainting**: When text overlaps an anatomical ROI, `seamless_inpaint_clean.py` uses pixel-level stroke masking + Laplace harmonic diffusion (never flat rectangular fills) so gradients and borders stay 100% seamless.
5. **Mandatory Visual QA Loop**: Automatically renders a 1:1 PNG preview via headless Edge/Chrome (`render_svg_preview.py`) so the agent visually inspects and polishes alignment, curve bounds, and spacing against the original figure before delivery.

---

## Repository Structure / 目录结构

```text
Image-Reconstruction/
├── SKILL.md                                   # Core agent skill instructions
├── README.md                                  # Documentation (EN / ZH)
├── LICENSE                                    # MIT License
├── requirements.txt                           # Python dependencies
├── references/
│   ├── svg-illustrator-best-practices.md      # Illustrator-ready SVG authoring guide
│   └── neural-regeneration-protocol.md        # Optional local-first VAE / Diffusion protocol & QA
├── scripts/
│   ├── inspect_image.py                       # Canvas size, hex color sampling, Windows OCR boxes
│   ├── trace_local_roi.py                     # Local free vtracer ROI vectorization & SVG ROI extractor
│   ├── seamless_inpaint_clean.py              # Stroke-masked Laplace harmonic diffusion text removal (+ mask export)
│   ├── neural_regeneration.py                 # Optional local-first VAE / Diffusion backend, QA & audit manifest CLI
│   └── render_svg_preview.py                  # Headless Edge/Chrome SVG -> PNG preview renderer
└── tests/
    └── test_neural_regeneration.py            # Automated tests for pad/crop, state machine, QA, fallback & redaction
```

---

## Installation / 安装方法

### 1. Clone into your Agent Skills directory / 克隆到全局 Skills 目录

- **Antigravity**:
  ```bash
  git clone https://github.com/shice951229-oss/Image-Reconstruction.git ~/.gemini/config/skills/Image-Reconstruction
  ```
- **Codex / Claude Code**:
  ```bash
  git clone https://github.com/shice951229-oss/Image-Reconstruction.git ~/.codex/skills/Image-Reconstruction
  ```

### 2. Install Python dependencies / 安装依赖

```bash
pip install -r requirements.txt
```

> Requires Python 3.10+ and Microsoft Edge or Google Chrome installed for headless PNG visual QA rendering.

---

## Usage / 使用方式

In your AI coding agent chat, upload a scientific diagram, flowchart, mechanism figure, or roadmap image and say:

- Chinese: `用 Image-Reconstruction 重建这张图`
- English: `Reconstruct this scientific figure as an editable native SVG using Image-Reconstruction.`

Open the delivered `.svg` directly in **Adobe Illustrator** (or Inkscape / Figma) to fine-tune any layer, text, curve, or color and save as `.ai`, `.pdf`, `.eps`, or high-DPI `.tiff`.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
