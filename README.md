# Vajan (वजन)

**Vajan** is a 100% local, self-contained AI video generation and reimagination pipeline designed for **Vast.ai** GPU instances. It takes low-resolution, candid mobile/family videos (MP4) and reimagines them into high-production cinematic videos while preserving the core human actions, gestures, and camera choreography.

---

## Key Features

* **100% Local & Self-Hosted:** No external APIs (no OpenAI, no Gemini API, no cloud SaaS). Runs entirely on your rented Vast.ai GPU.
* **Candid Mobile Video Preprocessing:**
  * **Auto-Orientation:** Automatically parses EXIF / MP4 container rotation metadata (fixes sideways vertical phone videos).
  * **VFR to CFR Normalization:** Converts mobile Variable Frame Rates into steady 16 FPS required by diffusion models.
  * **Sensor Noise Smoothing & CLAHE Contrast:** Reduces high-ISO sensor grain from low-light indoor family clips while keeping motion silhouettes intact.
  * **Smart Aspect Ratio Bucketing:** Automatically adapts to 9:16 portrait (480x720), 16:9 landscape (720x480), or 1:1 square.
* **Local Vision-Language Understanding (`Qwen2.5-VL-7B`):**
  * Reads the video clip locally in 4-bit / 8-bit precision (~5GB VRAM).
  * Extracts human choreography: gestures, facial emotional dynamics, physical interactions, and camera movement.
  * Synthesizes an imaginative cinematic prompt that replaces casual clothing and domestic clutter with high-end aesthetic designs.
* **Memory-Safe Sequential VRAM Offloading:**
  * VLM loads, extracts prompts, and unloads completely (`torch.cuda.empty_cache()`), freeing the GPU for video generation.
  * Enables running both a 7B VLM and a 5B+ Video DiT on a single **RTX 4090 (24GB)**.
* **Structural Video DiT (`CogVideoX-5B` / `Wan2.1`):**
  * Utilizes latent video-to-video with calibrated denoising strength (0.70 - 0.80).
  * Preserves macro motion dynamics while completely reimagining faces, skin, lighting, and wardrobe.

---

## Vast.ai Setup & Quickstart

### Vast.ai Lifecycle Scripts (Same Pattern as `bahiranan`)

You can launch, manage, sync, and generate remotely from your local terminal with zero manual setup:

```bash
# 1. Search for available GPUs (e.g. RTX 4090 under $0.60/hr)
./scripts/30_search_gpus.sh "RTX 4090" 0.60

# 2. Launch instance with 70GB disk for models (saves coordinates to .vast_instance)
./scripts/31_launch_instance.sh <OFFER_ID> 70

# 3. Check instance status, uptime, and spend
./scripts/32_instance_status.sh

# 4. Stream code to remote GPU and run setup
./scripts/33_sync_code_up.sh

# 5. Open an interactive SSH shell anytime
./scripts/38_ssh.sh

# 6. Run video generation remotely in background
./scripts/34_run_remote_video.sh my_video.mp4 "royal Renaissance banquet" cinematic_film 0.75

# 7. Tail live generation progress
./scripts/35_tail_logs.sh

# 8. Sync generated MP4s and metadata back to your local ./outputs/
./scripts/36_sync_output_down.sh

# 9. Terminate instance and stop billing when finished
./scripts/37_destroy_instance.sh
```

---

## Usage

### Basic Command

```bash
python run.py \
  --input path/to/family_clip.mp4 \
  --prompt "a royal Renaissance banquet with velvet robes, candlelight and gold goblets" \
  --style cinematic_film
```

### Command-Line Arguments

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-i`, `--input` | Path to the source mobile video (`.mp4`) | *Required* |
| `-p`, `--prompt` | Creative direction for reimagining | `None` (VLM will auto-elevate) |
| `-s`, `--style` | Style preset (`cinematic_film`, `cyberpunk_scifi`, `vintage_victorian`, `studio_fashion`, `watercolor_anime`) | `cinematic_film` |
| `-d`, `--denoise`| Denoising strength (0.60 to 0.85) | `0.75` |
| `--steps` | Diffusion inference steps | `35` |
| `-o`, `--output` | Output folder for videos and run metadata | `outputs` |
| `-c`, `--config` | Path to custom YAML configuration | `config.yaml` |

---

## How to Tune Structural Transfer

The `--denoise` flag controls the balance between source loyalty and creative imagination:

* **0.55 – 0.65 (High Loyalty):** Preserves original colors, shirt patterns, and room features. Retains too much of the low-res mobile artifacts.
* **0.70 – 0.80 (Sweet Spot):** **Recommended.** The faces, hair, and clothing are completely regenerated with high-fidelity detail and new identity. The physical movements, walking paths, head turns, and camera pans match the source video.
* **0.85 – 0.95 (High Imagination):** Video DiT prioritizes the prompt over the source video. Actions may diverge from the original footage.

---

## Project Structure

```text
vajan/
├── config.yaml                    # System configuration & style presets
├── requirements.txt               # Deep learning & video dependencies
├── scripts/
│   ├── vast_setup.sh              # One-click environment bootstrap for Vast.ai
│   └── download_models.sh         # Local model weights downloader
├── src/
│   ├── analyzer/
│   │   ├── video_preprocessor.py  # Orientation fix, VFR->CFR, noise filtering
│   │   └── vlm_captioner.py       # Local Qwen2.5-VL video action analyzer
│   ├── generator/
│   │   └── video_engine.py        # Local Diffusers DiT inference
│   └── pipeline.py                # End-to-end memory-safe orchestrator
└── run.py                         # CLI entrypoint
```
