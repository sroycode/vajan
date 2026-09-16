"""
vast_client.py
--------------
Sovereign Vast.ai REST API client for on-demand GPU instance management.
Zero external pip dependencies (uses Python standard library).
"""

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class VastClient:
    API_BASE = "https://console.vast.ai/api/v0"
    DEFAULT_IMAGE = "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("VASTAI_KEY") or os.environ.get("VAST_API_KEY")
        if not self.api_key:
            # Check candidate .env files
            candidate_files = [
                Path(".env.local"),
                Path(".env"),
                Path("../.env.local"),
                Path("../bahiranan/.env.local"),
            ]
            for env_file in candidate_files:
                if env_file.exists():
                    try:
                        with open(env_file, "r") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("#"):
                                    continue
                                if "VASTAI_KEY=" in line:
                                    self.api_key = line.split("VASTAI_KEY=", 1)[1].strip().strip('"').strip("'")
                                    break
                                if "VAST_API_KEY=" in line:
                                    self.api_key = line.split("VAST_API_KEY=", 1)[1].strip().strip('"').strip("'")
                                    break
                    except Exception:
                        pass
                if self.api_key:
                    break

        if not self.api_key:
            config_file = Path.home() / ".vast_api_key"
            if config_file.exists():
                try:
                    with open(config_file, "r") as f:
                        self.api_key = f.read().strip()
                except Exception:
                    pass

    def request(self, endpoint: str, method: str = "GET", params: dict = None, data: dict = None) -> Any:
        if not self.api_key:
            raise ValueError(
                "Vast.ai API key not configured. Set VASTAI_KEY or VAST_API_KEY in .env.local, ~/.vast_api_key, or env."
            )
        if params is None:
            params = {}
        params["api_key"] = self.api_key

        url = f"{self.API_BASE}/{endpoint.lstrip('/')}"
        query_str = urllib.parse.urlencode(params)
        if query_str:
            url += f"?{query_str}"

        headers = {"Accept": "application/json"}
        body_bytes = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body_bytes = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        ctx = None
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            try:
                ctx = ssl.create_default_context()
            except Exception:
                ctx = ssl._create_unverified_context()

        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}
        except urllib.error.URLError:
            ctx_unverified = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=30, context=ctx_unverified) as resp:
                content = resp.read().decode("utf-8")
                return json.loads(content) if content else {}

    def search_hardware(
        self,
        targets: Optional[List[str]] = None,
        max_price: float = 2.50,
        min_vram_gb: int = 20,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Searches top GPU offers prioritizing Blackwell (5090), 4090, and A100."""
        if targets is None:
            targets = ["5090", "4090", "A100", "H100"]

        query = {"rentable": {"eq": True}}
        res = self.request("bundles", params={"q": json.dumps(query)})
        offers = res.get("offers", [])

        candidates = []
        for o in offers:
            gpu_name = o.get("gpu_name", "")
            dph = float(o.get("dph_total", 999.0))
            vram_gb = int(o.get("gpu_ram", 0) / 1024)

            if dph > max_price or vram_gb < min_vram_gb:
                continue

            matched_target = None
            for t in targets:
                if t.lower() in gpu_name.lower():
                    matched_target = t
                    break

            if matched_target:
                candidates.append({
                    "id": o.get("id"),
                    "gpu_name": gpu_name,
                    "num_gpus": o.get("num_gpus", 1),
                    "vram_gb": vram_gb,
                    "price_per_hr": dph,
                    "down_mbps": int(o.get("inet_down", 0)),
                    "up_mbps": int(o.get("inet_up", 0)),
                    "cuda_max": o.get("cuda_max_good", "N/A"),
                    "driver_version": o.get("driver_version", "N/A"),
                    "location": o.get("geolocation", "Cloud"),
                    "reliability": float(o.get("reliability2", 0.0) or 0.0) * 100,
                    "is_blackwell": "5090" in gpu_name.lower() or "b200" in gpu_name.lower()
                })

        # Sort: Blackwell first if priced reasonably, then by lowest hourly rate
        candidates.sort(key=lambda x: (not x["is_blackwell"] and x["price_per_hr"] > 0.60, x["price_per_hr"]))
        return candidates[:limit]

    def _find_ssh_pubkey(self) -> Optional[str]:
        candidates = [
            Path.home() / ".ssh" / "id_ed25519.pub",
            Path.home() / ".ssh" / "id_rsa.pub",
            Path("/Users/shreos/.ssh/id_ed25519.pub"),
            Path("/Users/shreos/.ssh/id_rsa.pub"),
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    return candidate.read_text().strip()
                except Exception:
                    pass
        return None

    def launch(self, offer_id: int, disk_gb: int = 70, image: Optional[str] = None) -> Optional[int]:
        payload = {
            "client_id": "me",
            "image": image or self.DEFAULT_IMAGE,
            "disk": disk_gb,
            "runtype": "ssh",
        }
        res = self.request(f"asks/{offer_id}", method="PUT", data=payload)
        inst_id = res.get("new_contract") or res.get("instance_id")
        if inst_id:
            pubkey = self._find_ssh_pubkey()
            if pubkey:
                try:
                    self.request(f"instances/{inst_id}/ssh", method="POST", data={"ssh_key": pubkey})
                except Exception:
                    pass
        return inst_id

    def list_instances(self) -> List[Dict[str, Any]]:
        res = self.request("instances")
        return res.get("instances", [])

    def get_instance(self, instance_id: int) -> Dict[str, Any]:
        for inst in self.list_instances():
            if str(inst.get("id")) == str(instance_id):
                return inst
        return {}

    def wait_for_ssh(self, instance_id: int, max_wait_sec: int = 180, poll_sec: int = 4) -> Tuple[str, int]:
        """Polls until instance is running and reports SSH host and port."""
        start = time.time()
        while time.time() - start < max_wait_sec:
            info = self.get_instance(instance_id)
            status = info.get("actual_status", "starting")
            ssh_host = info.get("ssh_host")
            ssh_port = info.get("ssh_port")

            elapsed = int(time.time() - start)
            print(f"  [{elapsed:02d}s] Instance #{instance_id} status: {status} | SSH: {ssh_host}:{ssh_port}")

            if status == "running" and ssh_host and ssh_port:
                return str(ssh_host), int(ssh_port)

            time.sleep(poll_sec)

        raise TimeoutError(f"Instance #{instance_id} did not report SSH coordinates within {max_wait_sec}s.")

    def destroy(self, instance_id: int) -> Dict[str, Any]:
        """Terminates the instance to stop billing. Never raises exception."""
        try:
            return self.request(f"instances/{instance_id}", method="DELETE")
        except Exception as e:
            return {"success": False, "error": str(e)}
