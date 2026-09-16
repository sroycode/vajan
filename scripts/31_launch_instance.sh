#!/usr/bin/env bash
# ==============================================================================
#  31_launch_instance.sh : Launch/Rent Selected Instance on Vast.ai
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
source scripts/00_script_config.sh

OFFER_ID="${1:-}"
DISK_GB="${2:-70}"

if [ -z "$OFFER_ID" ]; then
    echo "Usage: $0 <OFFER_ID> [DISK_GB]"
    echo "Example: $0 48265692 70"
    echo ""
    echo "Run ./scripts/30_search_gpus.sh to find available OFFER_IDs."
    exit 1
fi

echo "========================================================================"
echo "  VAST.AI INSTANCE LAUNCH"
echo "  Offer ID : $OFFER_ID"
echo "  Disk     : ${DISK_GB} GB"
echo "========================================================================"

python3 -c "
from src.cloud.vast_client import VastClient
import sys, time, os
from pathlib import Path

offer_id = int('$OFFER_ID')
disk_gb = int('$DISK_GB')

client = VastClient()
print(f'[*] Renting instance for offer #{offer_id} ({disk_gb}GB disk)...')
inst_id = client.launch(offer_id=offer_id, disk_gb=disk_gb)
if not inst_id:
    print('[-] Failed to launch instance. Check balance or offer availability.')
    sys.exit(1)

print(f'[+] Instance rental initiated! Instance ID: {inst_id}')

# Save instance ID locally
meta_file = Path('.vast_instance')
with open(meta_file, 'w') as f:
    f.write(f'INSTANCE_ID={inst_id}\\n')

print('[*] Waiting for instance to spin up and report SSH coordinates...')
for attempt in range(45):
    time.sleep(4)
    info = client.get_instance(inst_id)
    status = info.get('actual_status', 'starting')
    ssh_host = info.get('ssh_host')
    ssh_port = info.get('ssh_port')
    print(f'    [{attempt*4}s] Status: {status} | SSH: {ssh_host}:{ssh_port}')
    if status == 'running' and ssh_host and ssh_port:
        with open(meta_file, 'w') as f:
            f.write(f'INSTANCE_ID={inst_id}\\n')
            f.write(f'SSH_HOST={ssh_host}\\n')
            f.write(f'SSH_PORT={ssh_port}\\n')
            f.write(f'SSH_CMD=\"ssh -p {ssh_port} root@{ssh_host}\"\\n')
            f.write(f'GPU_NAME=\"{info.get(\"gpu_name\")}\"\\n')
            f.write(f'DPH={info.get(\"dph_total\", 0)}\\n')

        print('\\n========================================================================')
        print(f'[+] INSTANCE #{inst_id} IS READY!')
        print(f'    GPU      : {info.get(\"num_gpus\")}x {info.get(\"gpu_name\")}')
        print(f'    SSH      : ssh -p {ssh_port} root@{ssh_host}')
        print(f'    Rate     : \${info.get(\"dph_total\", 0):.3f}/hr')
        print('    Config   : Saved to .vast_instance')
        print('========================================================================')
        print('\\nNext steps:')
        print('  1. Upload code to instance    : ./scripts/33_sync_code_up.sh')
        print('  2. Open interactive shell     : ./scripts/38_ssh.sh')
        print('  3. Run video generation       : ./scripts/34_run_remote_video.sh <video.mp4>')
        print('  4. Sync generated video back  : ./scripts/36_sync_output_down.sh')
        sys.exit(0)

print(f'[!] Instance #{inst_id} is still initializing. Check status anytime with:')
print('    ./scripts/32_instance_status.sh')
"
