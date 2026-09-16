#!/usr/bin/env bash
# ==============================================================================
#  34_run_remote_video.sh : Run Video Reimagination Remotely on Vast.ai
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
source scripts/00_script_config.sh

LOCAL_VIDEO="${1:-}"
PROMPT="${2:-}"
STYLE="${3:-cinematic_film}"
DENOISE="${4:-0.75}"

if [ -z "$LOCAL_VIDEO" ]; then
    echo "Usage: $0 <VIDEO_PATH> [PROMPT] [STYLE] [DENOISE]"
    echo "Example: $0 family.mp4 'Renaissance royal banquet' cinematic_film 0.75"
    exit 1
fi

INST_ID="${INST_ID:-}"
if [ -z "$INST_ID" ] && [ -f ".vast_instance" ]; then
    INST_ID=$(grep '^INSTANCE_ID=' .vast_instance | cut -d'=' -f2)
fi

if [ -z "$INST_ID" ]; then
    echo "[-] No active instance found. Rent one first using ./scripts/31_launch_instance.sh"
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
print(f'{host} {port}')
")

SSH_HOST=$(echo "$SSH_INFO" | awk '{print $1}')
SSH_PORT=$(echo "$SSH_INFO" | awk '{print $2}')
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p $SSH_PORT"

REMOTE_INPUT_PATH="/workspace/vajan/inputs/$(basename "$LOCAL_VIDEO")"

# Upload video if local file exists
if [ -f "$LOCAL_VIDEO" ]; then
    echo "[*] Uploading local video '$LOCAL_VIDEO' to remote GPU instance..."
    scp -P "$SSH_PORT" -o StrictHostKeyChecking=no "$LOCAL_VIDEO" "root@$SSH_HOST:$REMOTE_INPUT_PATH"
    echo "[+] Video uploaded."
fi

# Build remote command
CMD="cd /workspace/vajan && nohup python3 run.py --input '$REMOTE_INPUT_PATH' --style '$STYLE' --denoise '$DENOISE'"
if [ -n "$PROMPT" ]; then
    CMD="$CMD --prompt '$PROMPT'"
fi
CMD="$CMD > /workspace/vajan/run.log 2>&1 & echo \$! > /workspace/vajan/run.pid"

echo "[*] Launching generation job in background on remote GPU..."
ssh $SSH_OPTS "root@$SSH_HOST" "$CMD"

PID=$(ssh $SSH_OPTS "root@$SSH_HOST" "cat /workspace/vajan/run.pid")
echo "[+] Job launched with Remote PID: $PID"
echo ""
echo "Next steps:"
echo "  - Stream live logs: ./scripts/35_tail_logs.sh"
echo "  - Sync video down:  ./scripts/36_sync_output_down.sh"
echo "  - Check status:     ./scripts/32_instance_status.sh"
