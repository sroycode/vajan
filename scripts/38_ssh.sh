#!/usr/bin/env bash
# ==============================================================================
#  38_ssh.sh : Open Interactive Terminal on Vast.ai Instance
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

echo "[*] Connecting to Vast.ai instance #$INST_ID (root@$SSH_HOST:$SSH_PORT)..."
exec ssh -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "root@$SSH_HOST"
