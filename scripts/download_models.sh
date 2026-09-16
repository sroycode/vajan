#!/usr/bin/env bash
set -e

echo "=== [Vajan] Pre-caching Open-Weight AI Models ==="

MODEL_DIR="${MODEL_CACHE_DIR:-$HOME/.cache/huggingface/hub}"
echo "Caching models to: $MODEL_DIR"

# Ensure huggingface_hub is installed
pip install -q huggingface_hub

# 1. Download Local VLM (Qwen2.5-VL-7B-Instruct) for Video Analysis
echo "Downloading Qwen2.5-VL-7B-Instruct..."
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='Qwen/Qwen2.5-VL-7B-Instruct',
    ignore_patterns=['*.bin', '*.pth', '*.pt'],  # Download safetensors only
    resume_download=True
)
print('Qwen2.5-VL-7B cached successfully.')
"

# 2. Download Video Diffusion Model (CogVideoX-5B or Wan2.1)
DEFAULT_VIDEO_MODEL="${1:-THUDM/CogVideoX-5B}"
echo "Downloading Video DiT Model: $DEFAULT_VIDEO_MODEL..."
python3 -c "
import sys
from huggingface_hub import snapshot_download
repo = '$DEFAULT_VIDEO_MODEL'
snapshot_download(
    repo_id=repo,
    ignore_patterns=['*.bin', '*.pth', '*.pt'],
    resume_download=True
)
print(f'{repo} cached successfully.')
"

echo "=== [Vajan] All model weights cached locally! ==="
