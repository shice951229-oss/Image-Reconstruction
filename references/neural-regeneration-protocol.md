# Local-First Neural Regeneration Protocol (`CineHybrid-3D` & Tier 2 ROI Branch)

This protocol defines the **auditable, local-first neural texture regeneration stage** inside `Image-Reconstruction`. It powers two scenarios while keeping the original figure as the immutable geometric and scientific reference:

1. **`CineHybrid-3D`（3D 光影无损混合分层模式 — Primary 3D Cover Mode）**:
   - Used for 3D rendered journal covers, volumetric lighting illustrations, and microscopy artwork where whole-image polygon vectorization (`vtracer`) would cause posterized "oil-painting" color bands.
   - Runs surgical stroke-masked Laplace harmonic inpainting (`240` iterations) followed by ultra-low-strength local `stabilityai/sd-turbo` (`mode="diffusion_img2img"`, `strength=0.01`, `steps=100`, `guidance_scale=0.0`, empty prompt `""`), then assembles the verified `reconstructed.png` into an Illustrator SVG 1.1 layered document (`xlink:href` Base64 3D layer + filter-free dual-stroke gradient vector arrows + single-font native editable `<text>`).
2. **`PureVector-2D` Optional Tier 2 Organic ROI Preprocessing**:
   - Used only when explicitly requested for complex organic/anatomical Tier 2 sub-illustration ROIs before local `vtracer` vectorization.

```text
original image inspection
  -> surgical text/arrow stroke cleanup + binary mask & OCR baseline capture (prepare)
  -> local sd-turbo (strength=0.01, steps=100) or VAE roundtrip regeneration (run)
  -> automated + manual geometric/color/edge QA (qa -> accept|reject)
  -> CineHybrid-3D SVG 1.1 layered assembly (compose-hybrid-svg) OR PureVector-2D Tier 2 ROI tracing
  -> headless 1:1 PNG preview & visual verification
```

Whenever local reconstruction fails, times out, lacks dependencies/models, or fails QA, the job is marked `unverified` or `rejected` in `manifest.json` and **automatically falls back** to `cleaned.png` / the untouched standard SVG pipeline.

---

## 1. Unified Backend Contract & CLI Subcommands

All backends implement the same lifecycle interface in `scripts/neural_regeneration.py`:

| Subcommand / Operation | Purpose |
| :--- | :--- |
| `prepare` | Copy original image, compute SHA-256, run `seamless_inpaint_clean.py` with `--mask-output`, record OCR/text boxes, and initialize `manifest.json`. |
| `run` (`create_job`) | Execute local (`local_diffusers`, `comfyui`, `mock`) regeneration on `cleaned.png` with automatic step scaling (`compute_effective_steps`) and reversible edge padding. |
| `status` (`get_job`) | Query current job status (`prepared`, `queued`, `running`, `succeeded`, `failed`, `timed_out`, `cancelled`). |
| `qa` | Run automated dimension, orientation, color-mode/alpha, structural/edge drift, color shift, and optional OCR baseline checks. |
| `accept` / `reject` | Record final verification decision and reviewer notes in `manifest.json`. |
| `cancel` | Cancel an in-flight job and record the cancellation timestamp. |
| `compose-hybrid-svg` | Package a verified 3D background PNG + JSON specification of gradient vector arrows, labels, and masthead into an Illustrator-compliant `CineHybrid-3D` SVG 1.1 file. |

### Supported Local Modes & Presets
1. **`CineHybrid-3D` Ultra-Low-Side-Effect Diffusion Preset (`diffusion_img2img`, Default High-Fidelity for 3D Covers)**:
   - Model: `stabilityai/sd-turbo` on local CUDA GPU (`torch.float16`) or CPU (`torch.float32`).
   - Parameters: `strength = 0.01`, `steps = 100` (auto-scaled via `compute_effective_steps` so `int(steps * strength) >= 1`), `guidance_scale = 0.0`, `prompt = ""`.
   - Typical verified QA metrics on 3D covers & complex biomedical art: `mean_abs_rgb_delta ≈ 3.7–4.8` (threshold `<= 14.0`), `max_mean_channel_shift ≈ 0.27–0.95`, `edge_correlation ≈ 0.868–0.875` (`>= 0.85`).
   - Hard conservative cap: `strength <= 0.20` (higher values require explicit `--allow-high-strength`).
2. **Optional Stronger Texture Re-synthesis Preset (`strength = 0.1`, `steps = 20`)**:
   - Runs `2` denoising steps within the `<= 0.20` conservative cap when stronger neural texture smoothing/re-synthesis is explicitly desired.
   - Observed trade-off on dense biomedical illustrations: `mean_abs_rgb_delta ≈ 6.90`, `max_mean_channel_shift ≈ 1.45`, `edge_correlation ≈ 0.788` (softens fine high-frequency detail and drops below the default `0.85` edge-correlation gate; pass `--min-edge-corr 0.75` if explicitly using `0.1`).
3. **`vae_roundtrip`**:
   - Runs a single deterministic `encode -> decode` pass through a local `diffusers.AutoencoderKL`.

### Reversible Padding Rule
- If a model requires dimensions divisible by `8` or `16`, apply **reversible edge padding** on the right and bottom edges before encoding, then **crop back to the exact original `(width, height)`** immediately after decoding.
- Never stretch, resize, or alter the canvas aspect ratio.

---

## 2. Text, Structure, and Scientific Integrity Boundaries

1. **Before reconstruction**:
   - Run `seamless_inpaint_clean.py --mask-output <mask.png>` (via `prepare`) using tight surgical bounding boxes around text and overlay arrows so neighboring 3D anatomy/receptors remain 100% untouched.
   - For multi-line labels adjacent to curved anatomical rims, medallions, or pointer lines, split into **single-line tight boxes** with ~2–3 px vertical margin (preventing anti-aliased edge pixels from bleeding across the Laplace boundary) and raise `"threshold"` to `55–65` with `"dilate": 1` over shaded contours so pale anatomical edges are never smudged.
   - Persist the original OCR boxes, text boxes JSON, and binary text mask inside the job directory, and visually verify `cleaned.png` before running `sd-turbo`.
2. **Immutable geometric reference**:
   - All text labels, journal mastheads, and overlay arrows are restored as live editable SVG `<text>` and `<line>`/`<polygon>` vector elements aligned to the **original image**.
3. **Strict scope**:
   - Reconstructed output **must never** overwrite the original image.
   - In `PureVector-2D`, reconstructed output **must never** be used for Tier 1 structure (frames, axes, mathematical curves, connectors, text).

---

## 3. Auditable Work Directory & Manifest Schema

Each job uses an isolated directory containing:
- `original.<ext>` (immutable copy of source image)
- `cleaned.png` (text/arrow-free input submitted to backend)
- `text_mask.png` (binary mask of cleaned strokes)
- `boxes.json` / `ocr_baseline.json` (recorded text/arrow regions)
- `reconstructed.png` (backend artifact, if succeeded)
- `manifest.json` (full audit record with SHA-256 hashes, parameters, state history, QA metrics, decision, and fallback path)

**Secret Hygiene**: Never write API keys, Bearer tokens, Authorization headers, or local credentials into `manifest.json`, CLI output, or SVG metadata.
