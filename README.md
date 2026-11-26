# Image-Reconstruction

**Zero-cost, publication-grade scientific figure & 3D cover reconstruction into clean, native editable SVG** — directly openable in **Adobe Illustrator**, **Inkscape**, or **Figma** with **zero missing-link, missing-font, or filter popups** to edit and export as `.ai`, `.pdf`, `.eps`, or high-DPI `.tiff`.

**零费用、出版级科研插图与 3D 期刊封面可编辑 SVG 重建 Skill** —— 无需任何付费描摹 API，支持 **双轨架构**：既可将 2D 科研机制图/流程图/曲线图 100% 重建为纯原生矢量（**`PureVector-2D`**），也可将 3D 渲染期刊封面/体积光影插画重建为光影零色块量化、文字与柔和渐变箭头原生可编辑的分层 SVG（**`CineHybrid-3D`**），拖入 **Adobe Illustrator** 秒开无弹窗。

---

## Dual-Track Architecture / 双轨重建架构

| Mode / 模式名称 | Target Scenarios / 适用场景 | Core Mechanism / 核心技术方案 |
| :--- | :--- | :--- |
| **`PureVector-2D`**<br>（纯原生矢量重建模式） | 2D scientific diagrams, flowcharts, mechanism schematics, mathematical curve plots, multi-panel roadmaps<br>（2D 科研机制图、流程图、函数曲线图、技术路线图） | **100% Pure Vector (`0` `<image>` nodes)**: Cards (`<rect rx>`), clipped headers (`<clipPath>` + `<linearGradient>`), smooth Bezier/sine curves, elbow connectors, native `<tspan>` subscripts/superscripts (`0` `☒` missing glyphs) + local free `vtracer` ROI vectorization for small anatomical icons. |
| **`CineHybrid-3D`**<br>（3D 光影无损混合分层模式） | 3D rendered journal covers (*Nature* / *Cell* / *Science* style), continuous volumetric lighting, bokeh depth-of-field blur, glowing cells & micro-particles<br>（3D 渲染期刊封面、连续体积光影、景深散景与微米粒子插画） | **4-Step Lossless 3D + Native Vector Overlay**:<br>1. Surgical stroke-masked Laplace harmonic inpainting (`240` iterations, `text_mask.png`) removes old text/arrows with zero background damage.<br>2. Ultra-low-strength local `stabilityai/sd-turbo` (`strength=0.01, steps=100`, CUDA) regenerates lossless 3D texture without "oil-painting" posterization (`mean_abs_rgb_delta < 4.0`).<br>3. SVG 1.1 `xlink:href` Base64 `Layer_3D_Artwork` + filter-free dual-stroke multi-stop opacity gradient `Layer_Vector_Arrows` (`0` `<feDropShadow>`) + single Windows system font (`Segoe UI` / `Georgia`) slender editable `Layer_Labels` & `Layer_Masthead`.<br>4. Headless Edge 1:1 PNG visual QA verification. |

---

## Why Dual-Track? / 为什么采用双轨方案？

1. **For 2D Diagrams (`PureVector-2D`)**: Whole-image bitmap auto-tracing breaks 1 px borders, turns gradient headers into patchy shards, and fragments boxes into uneditable paths. Authoring structure directly in native SVG code + isolating small anatomical sub-illustrations with local `vtracer` delivers 100% pure vector precision at **$0 cost**.
2. **For 3D Covers (`CineHybrid-3D`)**: Running polygon vectorization (`vtracer`) across a full 3D volumetric render quantizes continuous bokeh blur and radial cell glow into flat "oil-painting" color bands. `CineHybrid-3D` preserves 100% of the continuous 3D lighting in an audited `sd-turbo` SVG 1.1 `xlink:href` bottom layer while reconstructing all mastheads, scientific labels, and soft long-fade golden arrows as crisp, slender, Illustrator-native vectors on top.

### `CineHybrid-3D` Strength Presets / 强度档位参考

| Preset / 档位 | Parameters / 参数 | Denoising Steps / 去噪步数 | Observed Metrics / 实测指标 | Trade-off & Recommendation / 适用场景与取舍 |
| :--- | :--- | :---: | :--- | :--- |
| **High-Fidelity Default**<br>（默认高保真档） | `strength=0.01`, `steps=100` | `1` 步 | `mean_abs_rgb_delta ≈ 3.7–4.8`<br>`edge_correlation ≈ 0.87–0.88` | Preserves fine micro-textures (trabecular bone, cell membranes, cristae) and passes `--min-edge-corr 0.85`. Recommended default for publication figures. |
| **Stronger Texture Re-synthesis**<br>（可选纹理重绘档） | `strength=0.1`, `steps=20` | `2` 步 | `mean_abs_rgb_delta ≈ 6.9`<br>`edge_correlation ≈ 0.79` | Applies stronger neural texture smoothing/re-synthesis (`--strength 0.1` stays within the `<= 0.20` conservative cap). Trade-off: softens fine high-frequency detail and drops below `0.85` edge correlation (pass `--min-edge-corr 0.75` if explicitly selecting this preset). |

---

## Repository Structure / 目录结构

```text
Image-Reconstruction/
├── SKILL.md                                   # Dual-track agent skill instructions (PureVector-2D & CineHybrid-3D)
├── README.md                                  # Documentation (EN / ZH)
├── LICENSE                                    # MIT License
├── requirements.txt                           # Python dependencies
├── references/
│   ├── svg-illustrator-best-practices.md      # Illustrator-ready SVG 1.1 authoring & zero-popup guardrails
│   └── neural-regeneration-protocol.md        # CineHybrid-3D (sd-turbo 0.01) & local-first neural regeneration protocol
├── scripts/
│   ├── inspect_image.py                       # Canvas size, hex color sampling, Windows OCR boxes
│   ├── trace_local_roi.py                     # Local free vtracer ROI vectorization & SVG ROI extractor (PureVector-2D)
│   ├── seamless_inpaint_clean.py              # Surgical stroke-masked Laplace harmonic diffusion text/arrow removal
│   ├── neural_regeneration.py                 # Local sd-turbo / VAE runner, QA, manifest & compose-hybrid-svg CLI (CineHybrid-3D)
│   └── render_svg_preview.py                  # Headless Edge/Chrome SVG -> 1:1 PNG preview renderer
└── tests/
    └── test_neural_regeneration.py            # Automated tests for pad/crop, auto-steps, QA, CineHybrid-3D SVG & redaction
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

> Requires Python 3.10+ and Microsoft Edge or Google Chrome installed for headless PNG visual QA rendering. For GPU-accelerated `CineHybrid-3D` (`stabilityai/sd-turbo`), install CUDA PyTorch (`torch`) and `diffusers`.

---

## Usage / 使用方式

- **2D 科研插图纯矢量重建 (`PureVector-2D`)**:
  - `用 Image-Reconstruction (PureVector-2D) 把这张科研机制图重建为纯原生矢量 SVG`
- **3D 期刊封面/体积光影混合分层重建 (`CineHybrid-3D`)**:
  - `用 Image-Reconstruction 的 CineHybrid-3D 方案重建这张 3D 封面，保留 sd-turbo 0.01 无损 3D 底图 + 原生纤细文字与柔和渐变矢量箭头`

Open the delivered `.svg` directly in **Adobe Illustrator** (or Inkscape / Figma) to edit any layer, text, curve, or arrow and export as `.ai`, `.pdf`, `.eps`, or high-DPI `.tiff`.

---

## License

MIT License — see [LICENSE](LICENSE) for details.
