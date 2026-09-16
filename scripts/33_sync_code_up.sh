#!/usr/bin/env bash
# ==============================================================================
#  33_sync_code_up.sh : Fast Sync of Code & Setup to Remote Vast.ai Instance
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
source scripts/00_script_config.sh

INST_ID="${1:-}"

if [ -z "$INST_ID" ] && [ -f ".vast_instance" ]; then
    INST_ID=$(grep '^INSTANCE_ID=' .vast_instance | cut -d'=' -f2)
fi

if [ -z "$INST_ID" ]; then
    echo "Usage: $0 [INSTANCE_ID]"
    echo "No active instance specified and .vast_instance not found."
    exit 1
fi

SSH_INFO=$(python3 -c "
from src.cloud.vast_client import VastClient
import sys

client = VastClient()
info = client.get_instance(int('$INST_ID'))
if not info:
    print('ERROR: Instance not found', file=sys.stderr)
    sys.exit(1)

host = info.get('ssh_host')
port = info.get('ssh_port')
if not host or not port:
    print('ERROR: SSH credentials not yet available', file=sys.stderr)
    sys.exit(1)

print(f'{host} {port}')
")

SSH_HOST=$(echo "$SSH_INFO" | awk '{print $1}')
SSH_PORT=$(echo "$SSH_INFO" | awk '{print $2}')
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p $SSH_PORT"

echo "========================================================================"
echo "  SYNCING VAJAN CODE TO VAST.AI INSTANCE #$INST_ID"
echo "  Target Host : $SSH_HOST:$SSH_PORT"
echo "========================================================================"

# Prepare remote directory
echo "[*] Preparing remote directory /workspace/vajan..."
ssh $SSH_OPTS "root@$SSH_HOST" "mkdir -p /workspace/vajan /workspace/vajan/outputs /workspace/vajan/inputs"

# Fast code transfer via tar stream excluding local caches/large outputs
echo "[*] Streaming codebase to remote instance..."
tar -czf - \
    --exclude='*.mp4' \
    --exclude='*.avi' \
    --exclude='*.mov' \
    --exclude='*.safetensors' \
    --exclude='*.bin' \
    --exclude='venv' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='outputs' \
    --exclude='.git' \
    src/ \
    scripts/ \
    config.yaml \
    requirements.txt \
    run.py \
    README.md 2>/dev/null | ssh $SSH_OPTS "root@$SSH_HOST" "tar -xzf - -C /workspace/vajan"

echo "[+] Code transfer complete."

# Prompt to execute remote setup
read -p "Do you want to run bootstrap setup (pip install & model caching) on remote instance now? (y/N): " RUN_SETUP
if [[ "$RUN_SETUP" == "y" || "$RUN_SETUP" == "Y" ]]; then
    echo "[*] Running ./scripts/vast_setup.sh on remote instance..."
    ssh $SSH_OPTS "root@$SSH_HOST" "cd /workspace/vajan && bash scripts/vast_setup.sh"
    
    echo "[*] Pre-caching model weights..."
    ssh $SSH_OPTS "root@$SSH_HOST" "cd /workspace/vajan && bash scripts/download_models.sh"
fi

echo "========================================================================"
echo "[+] Remote instance is ready for video generation!"
echo "========================================================================"
echo "To run generation on remote instance:"
echo "  ./scripts/34_run_remote_video.sh <local_or_remote_video.mp4>"
