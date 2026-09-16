#!/usr/bin/env bash
# ==============================================================================
#  37_destroy_instance.sh : Safely Destroy Vast.ai Instance to Stop Billing
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

echo "========================================================================"
echo "  DESTROY VAST.AI INSTANCE #$INST_ID"
echo "========================================================================"

read -p "Are you sure you want to DESTROY instance #$INST_ID and terminate billing? (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "[-] Destruction cancelled."
    exit 0
fi

python3 -c "
from src.cloud.vast_client import VastClient
import os

client = VastClient()
res = client.destroy(int('$INST_ID'))
print(f'[+] Instance #$INST_ID destroyed successfully: {res}')

if os.path.exists('.vast_instance'):
    os.remove('.vast_instance')
    print('[+] Cleared local .vast_instance metadata.')
"

echo "========================================================================"
echo "[+] Instance terminated. No further billing will occur."
echo "========================================================================"
