#!/usr/bin/env bash
# ==============================================================================
#  36_sync_output_down.sh : Download Generated Videos from Vast.ai to Local
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
print(f\"{info.get('ssh_host')} {info.get('ssh_port')}\")
")

SSH_HOST=$(echo "$SSH_INFO" | awk '{print $1}')
SSH_PORT=$(echo "$SSH_INFO" | awk '{print $2}')
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p $SSH_PORT"

mkdir -p outputs

echo "========================================================================"
echo "  SYNCING OUTPUTS FROM VAST.AI INSTANCE #$INST_ID"
echo "  Remote: /workspace/vajan/outputs/ -> Local: ./outputs/"
echo "========================================================================"

rsync -avz --progress -e "ssh $SSH_OPTS" "root@$SSH_HOST:/workspace/vajan/outputs/" "./outputs/"

echo "[+] Sync completed! Videos downloaded into ./outputs/:"
ls -lh outputs/*.mp4 2>/dev/null || true
