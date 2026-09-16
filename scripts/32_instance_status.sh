#!/usr/bin/env bash
# ==============================================================================
#  32_instance_status.sh : Check Vast.ai Instance Status & SSH Endpoint
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
source scripts/00_script_config.sh

INST_ID="${1:-}"

if [ -z "$INST_ID" ] && [ -f ".vast_instance" ]; then
    INST_ID=$(grep '^INSTANCE_ID=' .vast_instance | cut -d'=' -f2)
fi

python3 -c "
from src.cloud.vast_client import VastClient
import sys

inst_id = '$INST_ID'.strip()
client = VastClient()

if not inst_id:
    # List all instances
    instances = client.list_instances()
    if not instances:
        print('[+] No active instances currently running on Vast.ai.')
        sys.exit(0)
    print('Active instances:')
    print(f'{\"ID\":<10} {\"Status\":<12} {\"GPU\":<20} {\"SSH Host:Port\":<30} {\"$/hr\"}')
    print('-' * 75)
    for inst in instances:
        ssh = f\"{inst.get('ssh_host', 'N/A')}:{inst.get('ssh_port', '')}\"
        print(f\"{inst.get('id'):<10} {inst.get('actual_status', 'unknown'):<12} {inst.get('gpu_name', 'GPU'):<20} {ssh:<30} \${inst.get('dph_total', 0):.3f}\")
    sys.exit(0)

info = client.get_instance(int(inst_id))
if not info:
    print(f'[-] Instance #{inst_id} not found or has been destroyed.')
    sys.exit(1)

ssh_host = info.get('ssh_host')
ssh_port = info.get('ssh_port')
status = info.get('actual_status')
dph = info.get('dph_total', 0)
uptime_hrs = info.get('duration', 0) / 3600.0

print('========================================================================')
print(f'  VAST.AI INSTANCE #{inst_id}')
print(f'  Status       : {status}')
print(f'  GPU          : {info.get(\"num_gpus\")}x {info.get(\"gpu_name\")} ({int(info.get(\"gpu_ram\", 0)/1024)}GB VRAM)')
print(f'  SSH Endpoint : root@{ssh_host}:{ssh_port}')
print(f'  SSH Command  : ssh -p {ssh_port} root@{ssh_host}')
print(f'  Rate / Hour  : \${dph:.3f}/hr')
print(f'  Uptime       : {uptime_hrs:.2f} hrs (Est. spend: \${uptime_hrs * dph:.3f})')
print('========================================================================')
"
