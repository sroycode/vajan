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


class VastClient:
    API_BASE = "https://console.vast.ai/api/v0"
    DEFAULT_IMAGE = "pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("VASTAI_KEY") or os.environ.get("VAST_API_KEY")
        if not self.api_key:
            # Check local .env files
            for env_file in [Path(".env.local"), Path(".env"), Path("../.env.local")]:
                if env_file.exists():
                    try:
                        with open(env_file, "r") as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith("export VASTAI_KEY=") or line.startswith("VASTAI_KEY="):
                                    self.api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                                    break
                                if line.startswith("export VAST_API_KEY=") or line.startswith("VAST_API_KEY="):
                                    self.api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                                    break
                    except Exception:
                        pass
                if self.api_key:
                    break

        if not self.api_key:
            config_file = Path.home() / ".vast_api_key"
            if config_file.exists():
                with open(config_file, "r") as f:
                    self.api_key = f.read().strip()

    def set_key(self, key: str):
        self.api_key = key.strip()
        config_file = Path.home() / ".vast_api_key"
        with open(config_file, "w") as f:
            f.write(self.api_key + "\n")
        os.chmod(config_file, 0o600)
        return str(config_file)

    def request(self, endpoint: str, method: str = "GET", params: dict = None, data: dict = None):
        if not self.api_key:
            raise ValueError(
                "Vast.ai API key not configured. Set VAST_API_KEY in .env.local, ~/.vast_api_key, or via CLI."
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

    def search(self, gpu_name: str = "RTX_4090", num_gpus: int = 1, max_price: float = 0.60, limit: int = 15):
        query = {
            "verified": {"eq": True},
            "rentable": {"eq": True},
            "num_gpus": {"eq": num_gpus},
            "dph": {"lte": max_price},
        }
        if gpu_name:
            query["gpu_name"] = {"eq": gpu_name.replace("_", " ")}

        res = self.request("bundles", params={"q": json.dumps(query)})
        offers = res.get("offers", [])
        offers = sorted(offers, key=lambda x: x.get("dph_total", 999.0))[:limit]
        return offers

    def _find_ssh_pubkey(self):
        candidates = [
            Path.home() / ".ssh" / "id_ed25519.pub",
            Path.home() / ".ssh" / "id_rsa.pub",
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    return candidate.read_text().strip()
                except Exception:
                    pass
        return None

    def launch(self, offer_id: int, disk_gb: int = 60, image: str = None):
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

    def list_instances(self):
        res = self.request("instances")
        return res.get("instances", [])

    def get_instance(self, instance_id: int):
        for inst in self.list_instances():
            if str(inst.get("id")) == str(instance_id):
                return inst
        return {}

    def destroy(self, instance_id: int):
        return self.request(f"instances/{instance_id}", method="DELETE")
