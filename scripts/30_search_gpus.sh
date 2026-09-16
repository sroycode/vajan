#!/usr/bin/env bash
# ==============================================================================
#  30_search_gpus.sh : Find Available GPUs on Vast.ai for Video Generation
# ==============================================================================
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
source scripts/00_script_config.sh

GPU="${1:-RTX 4090}"
MAX_PRICE="${2:-0.60}"

echo "========================================================================"
echo "  VAST.AI GPU SEARCH FOR VIDEO GENERATION"
echo "  Target Architecture : $GPU"
echo "  Max Price / Hour    : \$$MAX_PRICE"
echo "========================================================================"

python3 -c "
from src.cloud.vast_client import VastClient
import json, sys

gpu_target = '$GPU'.strip()
max_price = float('$MAX_PRICE')

client = VastClient()
query = {'rentable': {'eq': True}}
res = client.request('bundles', params={'q': json.dumps(query)})
offers = res.get('offers', [])

matching = []
for o in offers:
    name = o.get('gpu_name', '')
    dph = float(o.get('dph_total', 999.0))
    if gpu_target.lower().replace('_', ' ') in name.lower() and dph <= max_price:
        matching.append(o)

matching = sorted(matching, key=lambda x: x.get('dph_total', 999.0))

if not matching:
    print(f'[-] No matching offers found for \"{gpu_target}\" under \${max_price:.2f}/hr.')
    print('    Try raising max price or searching: RTX 4090, RTX 5090, A100, RTX 3090, H100.')
    sys.exit(0)

print(f'Found {len(matching)} available offer(s):\\n')
print(f'{\"OFFER_ID\":<11} {\"GPU MODEL\":<18} {\"VRAM\":<8} {\"PRICE\":<10} {\"DL/UL\":<14} {\"DRIVER/CUDA\":<18} {\"LOCATION\"}')
print('-' * 95)
for m in matching[:15]:
    oid = m.get('id')
    g = f\"{m.get('num_gpus')}x {m.get('gpu_name')}\"
    vram = f\"{int(m.get('gpu_ram', 0) / 1024)}GB\"
    price = f\"\${m.get('dph_total', 0):.3f}/hr\"
    net = f\"{int(m.get('inet_down', 0))}/{int(m.get('inet_up', 0))}M\"
    drv = f\"{m.get('driver_version', 'N/A')[:6]} (cu{m.get('cuda_max_good', 'N/A')})\"
    loc = m.get('geolocation', 'Cloud')[:18]
    print(f\"{oid:<11} {g:<18} {vram:<8} {price:<10} {net:<14} {drv:<18} {loc}\")

print('-' * 95)
top_offer = matching[0].get('id')
print(f'\\n[+] To launch the lowest-priced offer (#{top_offer}), run:')
print(f'    ./scripts/31_launch_instance.sh {top_offer}')
"
