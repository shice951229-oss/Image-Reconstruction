# Local-First Neural Regeneration Protocol (Optional Preprocessing Branch)

This protocol defines an **optional, local-first preprocessing stage** inside `Image-Reconstruction`. It **never replaces** the primary native SVG reconstruction pipeline; it is strictly limited to preparing complex organic/textured Tier 2 ROIs while preserving the original figure as the immutable geometric and scientific reference.

```text
original image inspection
  -> text/label cleanup + mask & OCR baseline capture
  -> optional local VAE or low-strength Diffusion reconstruction
  -> automated + manual geometric/color QA
  -> restore live editable SVG <text> from original baseline
  -> native SVG reconstruction (Tier 1 native geometry + Tier 2 ROI)
```

Whenever local reconstruction fails, times out, lacks dependencies/models, or fails QA, the job is marked `unverified` or `rejected` in its manifest and **automatically falls back** to the standard local SVG pipeline using the untouched original / cleaned image.

---

## 1. Unified Backend Contract

All backends implement the same lifecycle interface in `scripts/neural_regeneration.py`:

| Operation | Purpose |
| :--- | :--- |
| `prepare` | Copy original image, compute SHA-256, run `seamless_inpaint_clean.py` with `--mask-output`, record OCR/text boxes and initialize `manifest.json`. |
| `create_job` | Submit a local (`local_diffusers`, `comfyui`, `mock`) or optional workstation job using the cleaned image. |
| `get_job` | Query current job status (`queued`, `running`, `succeeded`, `failed`, `timed_out`, `cancelled`). |
| `fetch_artifact` | Retrieve and store the reconstructed image without overwriting the original or cleaned input. |
| `qa` | Run automated dimension, orientation, color-mode/alpha, structural/edge drift, color shift, and OCR baseline checks. |
| `cancel` | Cancel an in-flight job and record the cancellation timestamp. |

### Supported Local Modes
1. **`vae_roundtrip` (Preferred low-side-effect default)**:
   - Runs a single deterministic `encode -> decode` pass through a local `diffusers.AutoencoderKL`.
   - Never iterates multiple times by default.
2. **`diffusion_img2img`**:
   - Runs a low-strength image-to-image pass through a local non-homologous Diffusion pipeline (`diffusers.AutoPipelineForImage2Image`).
   - **Conservative scientific figure defaults**:
     - Default `strength = 0.10`.
     - Hard default cap `strength <= 0.20` (higher values require explicit `--allow-high-strength` opt-in).
     - Empty prompt (`""`) by default; ControlNet, LoRA, and semantic-altering guidance are disabled by default.

### Reversible Padding Rule
- If a model requires dimensions divisible by `8` or `16`, apply **reversible edge/reflect padding** on the right and bottom edges before encoding, then **crop back to the exact original `(width, height)`** immediately after decoding.
- Never stretch, resize, or alter the canvas aspect ratio.

---

## 2. Text, Structure, and Scientific Integrity Boundaries

1. **Before reconstruction**:
   - Run `seamless_inpaint_clean.py --mask-output <mask.png>` to remove lettering, labels, and annotations.
   - Persist the original OCR boxes, text boxes JSON, and binary text mask inside the job directory.
2. **Immutable geometric reference**:
   - Borders, axes, arrows, thin lines, mathematical symbols, and text coordinates come strictly from the **original image**.
   - All text is always restored as live editable SVG `<text>` / `<tspan>` elements.
3. **Strict Tier 2 scope**:
   - Reconstructed output **must never** overwrite the original image.
   - Reconstructed output **must never** be used to draw Tier 1 structural elements (frames, axes, mathematical curves, connectors, text).
   - Reconstructed output is **never treated as scientific evidence**; it may only serve as an intermediate visual reference or Tier 2 complex organic texture ROI.

---

## 3. Auditable Work Directory & Manifest Schema

Each job uses an isolated directory containing:
- `original.<ext>` (immutable copy of source image)
- `cleaned.png` (text-free input submitted to backend)
- `text_mask.png` (binary mask of cleaned text strokes)
- `boxes.json` / `ocr_baseline.json` (recorded text regions)
- `reconstructed.png` (backend artifact, if succeeded)
- `manifest.json` (full audit record)

Required `manifest.json` fields:
- `schema_version`: `"1.0"`
- `job_id`, `created_at`, `updated_at`
- `original`: `{path, sha256, width, height, mode}`
- `cleaned`: `{path, sha256, mask_path, boxes_path, ocr_baseline_path}`
- `backend`: `{type, mode, model_id, model_revision, steps, strength, seed, pad_multiple, input_resolution, color_mode}`
- `job`: `{status, remote_job_id, started_at, finished_at, error}`
- `artifact`: `{path, sha256, width, height, mode}`
- `qa`: `{passed, checks, metrics, checked_at}`
- `decision`: `"pending" | "accepted" | "rejected" | "unverified"`
- `review_notes`: human reviewer notes
- `fallback_path`: original/cleaned path used if rejected or unverified

**Secret Hygiene**: Never write API keys, Bearer tokens, Authorization headers, or local credentials into `manifest.json`, CLI output, or SVG metadata.

---

## 4. QA Criteria & Failure Fallback Policy

### Automated QA (`scripts/neural_regeneration.py qa`)
A reconstructed artifact is automatically **rejected** if any of the following fail:
1. Exact canvas `(width, height)` and orientation match.
2. Color mode and alpha presence match.
3. Mean color shift and structural/edge drift remain within conservative thresholds (detects cropping, zoom, unremoved padding, severe banding, or shifted borders/axes).
4. Optional OCR drift check confirms no unexpected text hallucination or baseline shift when OCR boxes are compared.

### Manual QA
Before calling `accept`, compare the original, cleaned, and reconstructed images 1:1, focusing on text regions, thin lines, arrowheads, panel borders, and complex ROIs. Reject immediately on any topological, geometric, or scientific-symbol alteration.

### Fallback Policy
If dependencies (`torch`, `diffusers`) are missing, the local model is unavailable, the job times out/fails, or QA fails:
- Preserve `manifest.json` with `decision = "unverified"` (on runtime/dependency failure) or `"rejected"` (on QA failure).
- Automatically continue with the standard `Image-Reconstruction` local SVG workflow using `original` / `cleaned.png`.
