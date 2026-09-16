#!/usr/bin/env bash
set -e

echo "=== [Vajan] Bootstrapping Environment for Vast.ai GPU Instance ==="

# 1. Update system & install essential tools
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    git \
    git-lfs \
    curl \
    wget \
    build-essential \
    python3-dev \
    libgl1-mesa-glx

git lfs install

# 2. Upgrade pip
python3 -m pip install --upgrade pip setuptools wheel

# 3. Install PyTorch with CUDA support if not already present
if ! python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    echo "Installing PyTorch with CUDA 12.4 support..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
fi

# 4. Install project requirements
echo "Installing project dependencies from requirements.txt..."
pip install -r requirements.txt

# 5. Verify GPU status and CUDA availability
python3 -c "
import torch
print('CUDA Available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('Device Name:', torch.cuda.get_device_name(0))
    print('VRAM (GB):', round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2))
"

echo "=== [Vajan] Setup Complete! ==="
