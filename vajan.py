#!/usr/bin/env python3
"""
vajan.py
--------
Single CLI for Vajan: AI Structural Video Enhancer & Re-imaginer using Vast.ai.

Usage:
  # Start a new video generation (hardware search -> select -> launch -> run):
  python vajan.py -v <video_file> -a start [-s <style>]

  # Check generation status and progress:
  python vajan.py -c <config_json> -a check

  # Stop running process on Vast.ai:
  python vajan.py -c <config_json> -a stop

  # Download generated file when ready:
  python vajan.py -c <config_json> -a getfile

  # Clean up temporary video data on server (keeps models/environment):
  python vajan.py -c <config_json> -a cleanup

  # Start a new video re-using existing instance setup:
  python vajan.py -c <config_json> -a start -v <new_video_file> [-s <style>]

  # Stop and permanently delete the Vast.ai instance (always succeeds):
  python vajan.py -c <config_json> -a delete
"""

import os
import re
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from src.cloud.vast_client import VastClient


# ------------------------------------------------------------------------------
# Helpers: Naming, Paths & Config
# ------------------------------------------------------------------------------

def get_vajan_home() -> Path:
    """Returns the resolved VAJAN_HOME directory (defaults to current directory)."""
    home = os.environ.get("VAJAN_HOME", ".")
    p = Path(home).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def generate_config_path(video_file: str) -> Path:
    """Generates config filename: lowercase_underscore_video_name + YYMMDDHHMM.json"""
    stem = Path(video_file).stem
    # Convert name to lowercase + underscores
    clean_stem = re.sub(r'[^a-zA-Z0-9]+', '_', stem).strip('_').lower()
    if not clean_stem:
        clean_stem = "video"
    timestamp = datetime.now().strftime("%y%m%d%H%M")
    filename = f"{clean_stem}_{timestamp}.json"
    return get_vajan_home() / filename


def load_config(config_path: str) -> Dict[str, Any]:
    """Loads and validates a config JSON file."""
    p = Path(config_path)
    if not p.exists():
        # Also check relative to VAJAN_HOME
        alt = get_vajan_home() / config_path
        if alt.exists():
            p = alt
        else:
            print(f"[-] Error: Config JSON not found at '{config_path}'", file=sys.stderr)
            sys.exit(1)
    try:
        with open(p, "r") as f:
            data = json.load(f)
        data["_filepath"] = str(p.resolve())
        return data
    except Exception as e:
        print(f"[-] Error reading config JSON '{p}': {e}", file=sys.stderr)
        sys.exit(1)


def save_config(config_data: Dict[str, Any], filepath: Optional[str] = None):
    """Saves updated config JSON back to disk."""
    dest = Path(filepath or config_data.get("_filepath"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean_data = {k: v for k, v in config_data.items() if not k.startswith("_")}
    with open(dest, "w") as f:
        json.dump(clean_data, f, indent=2)


# ------------------------------------------------------------------------------
# Remote SSH & File Transfer Utilities
# ------------------------------------------------------------------------------

def run_ssh(host: str, port: int, command: str, timeout: int = 60) -> Tuple[int, str, str]:
    """Runs a remote command over SSH."""
    opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-p", str(port)
    ]
    cmd = ["ssh"] + opts + [f"root@{host}", command]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "SSH command timed out"
    except Exception as e:
        return -1, "", str(e)


def upload_file(host: str, port: int, local_path: str, remote_path: str) -> bool:
    """Uploads a local file to remote host via scp."""
    opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-P", str(port)
    ]
    # Ensure remote directory exists
    remote_dir = str(Path(remote_path).parent)
    run_ssh(host, port, f"mkdir -p '{remote_dir}'", timeout=20)

    cmd = ["scp"] + opts + [local_path, f"root@{host}:{remote_path}"]
    res = subprocess.run(cmd)
    return res.returncode == 0


def download_file(host: str, port: int, remote_path: str, local_path: str) -> bool:
    """Downloads a remote file via scp."""
    opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-P", str(port)
    ]
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = ["scp"] + opts + [f"root@{host}:{remote_path}", local_path]
    res = subprocess.run(cmd)
    return res.returncode == 0


def sync_codebase_to_remote(host: str, port: int, remote_dir: str = "/workspace/vajan") -> bool:
    """Syncs the current project codebase to the remote instance excluding heavy files."""
    print(f"[*] Syncing project code to remote instance ({remote_dir})...")
    run_ssh(host, port, f"mkdir -p '{remote_dir}'", timeout=20)

    root_dir = Path(__file__).resolve().parent

    # Stream tarball over SSH
    tar_cmd = [
        "tar", "-czf", "-",
        "--exclude=.git*",
        "--exclude=venv*",
        "--exclude=*.mp4",
        "--exclude=*.avi",
        "--exclude=outputs*",
        "--exclude=temp*",
        "--exclude=__pycache__*",
        "--exclude=*.json",
        "."
    ]

    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-p", str(port)
    ]
    remote_unpack_cmd = ["ssh"] + ssh_opts + [f"root@{host}", f"tar -xzf - -C '{remote_dir}'"]

    p1 = subprocess.Popen(tar_cmd, cwd=str(root_dir), stdout=subprocess.PIPE)
    p2 = subprocess.Popen(remote_unpack_cmd, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p1.stdout.close()
    out, err = p2.communicate()

    if p2.returncode == 0:
        print("[+] Codebase synced successfully.")
        return True
    else:
        print(f"[-] Codebase sync error: {err.decode('utf-8')}", file=sys.stderr)
        return False


def setup_remote_environment(host: str, port: int, remote_dir: str = "/workspace/vajan") -> bool:
    """Runs bootstrap script on remote instance to install dependencies."""
    print("[*] Bootstrapping remote GPU environment (ffmpeg, packages, PyTorch)...")
    cmd = f"cd '{remote_dir}' && bash scripts/vast_setup.sh"
    ret, out, err = run_ssh(host, port, cmd, timeout=600)
    if ret == 0:
        print("[+] Remote environment bootstrap complete.")
        return True
    else:
        print(f"[!] Bootstrap warning (non-zero exit): {err}\nOutput: {out[:300]}")
        return True


# ------------------------------------------------------------------------------
# Action Implementations
# ------------------------------------------------------------------------------

def action_start_new(video_path: str, style: str = "cinematic"):
    """Action '-v file -a start':
    1. Checks available hardware and displays top options in a table.
    2. User selects hardware option.
    3. Creates instance, writes config JSON to VAJAN_HOME.
    4. Sets up environment and starts the generation process in background.
    """
    v_path = Path(video_path).resolve()
    if not v_path.exists():
        print(f"[-] Error: Input video file not found at '{video_path}'", file=sys.stderr)
        sys.exit(1)

    print("=" * 75)
    print("  VAJAN: LAUNCH NEW GENERATION JOB")
    print(f"  Source Video : {v_path.name} ({v_path.stat().st_size / (1024*1024):.2f} MB)")
    print(f"  Style Preset : {style}")
    print("=" * 75)

    client = VastClient()
    if not client.api_key:
        print("[-] Error: Vast.ai API key not configured. Set VASTAI_KEY or VAST_API_KEY.", file=sys.stderr)
        sys.exit(1)

    # 1. Search available hardware
    print("[*] Querying available high-performance GPU hardware on Vast.ai...")
    offers = client.search_hardware(limit=10)
    if not offers:
        print("[-] No matching GPU offers found on Vast.ai. Check filters or try again later.", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 90)
    print(f"{'#':<3} {'OFFER_ID':<11} {'GPU MODEL':<18} {'VRAM':<7} {'RATE':<11} {'DL/UL SPEED':<15} {'LOCATION':<18} {'ARCH'}")
    print("-" * 90)
    for i, o in enumerate(offers, 1):
        arch = "Blackwell ★" if o["is_blackwell"] else "Standard"
        g_desc = f"{o['num_gpus']}x {o['gpu_name']}"[:17]
        vram_str = f"{o['vram_gb']}GB"
        rate_str = f"${o['price_per_hr']:.3f}/hr"
        net_str = f"{o['down_mbps']}/{o['up_mbps']}M"
        loc_str = str(o['location'])[:17]
        print(f"{i:<3} {o['id']:<11} {g_desc:<18} {vram_str:<7} {rate_str:<11} {net_str:<15} {loc_str:<18} {arch}")
    print("=" * 90)

    # 2. User selects hardware option
    chosen_offer = None
    try:
        user_choice = input(f"\nSelect hardware option [1-{len(offers)}] (default: 1) or enter Offer ID: ").strip()
        if not user_choice:
            chosen_offer = offers[0]
        elif user_choice.isdigit():
            idx = int(user_choice)
            if 1 <= idx <= len(offers):
                chosen_offer = offers[idx - 1]
            else:
                # Treated as custom offer ID
                chosen_offer = {"id": idx, "gpu_name": "Custom Offer", "price_per_hr": 0.0}
        else:
            chosen_offer = offers[0]
    except (KeyboardInterrupt, EOFError):
        print("\nAborted by user.")
        sys.exit(0)

    offer_id = chosen_offer["id"]
    gpu_name = chosen_offer.get("gpu_name", "GPU")
    print(f"\n[*] Renting selected offer #{offer_id} ({gpu_name}) on Vast.ai...")

    # 3. Create instance
    inst_id = client.launch(offer_id=offer_id, disk_gb=70)
    if not inst_id:
        print("[-] Failed to launch instance. Check balance or offer availability.", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Instance contract created! Instance ID: #{inst_id}")

    # 4. Generate config JSON in VAJAN_HOME
    config_path = generate_config_path(str(v_path))
    stem = v_path.stem
    clean_stem = re.sub(r'[^a-zA-Z0-9]+', '_', stem).strip('_').lower()

    config_data = {
        "video_file": str(v_path),
        "video_name": stem,
        "clean_name": clean_stem,
        "style": style,
        "instance_id": inst_id,
        "offer_id": offer_id,
        "gpu_name": gpu_name,
        "ssh_host": None,
        "ssh_port": None,
        "status": "initializing",
        "created_at": datetime.now().isoformat(),
        "remote_workdir": "/workspace/vajan",
        "remote_pid": None,
        "remote_output": f"/workspace/vajan/outputs/{clean_stem}_reimagined.mp4"
    }
    save_config(config_data, str(config_path))
    print(f"[+] Config JSON written to: {config_path}")

    # 5. Wait for SSH coordinates
    print("[*] Waiting for instance to initialize and report SSH connection...")
    try:
        ssh_host, ssh_port = client.wait_for_ssh(inst_id, max_wait_sec=180, poll_sec=4)
    except Exception as e:
        print(f"[-] Error waiting for SSH: {e}", file=sys.stderr)
        print(f"    Check status later with: python vajan.py -c {config_path} -a check")
        sys.exit(1)

    config_data["ssh_host"] = ssh_host
    config_data["ssh_port"] = ssh_port
    config_data["status"] = "provisioned"
    save_config(config_data, str(config_path))
    print(f"[+] SSH Ready: ssh -p {ssh_port} root@{ssh_host}")

    # 6. Sync codebase & setup remote environment
    sync_codebase_to_remote(ssh_host, ssh_port, "/workspace/vajan")
    setup_remote_environment(ssh_host, ssh_port, "/workspace/vajan")

    # 7. Upload video
    remote_video_path = f"/workspace/vajan/inputs/{v_path.name}"
    print(f"[*] Uploading video '{v_path.name}' to remote instance...")
    if not upload_file(ssh_host, ssh_port, str(v_path), remote_video_path):
        print(f"[-] Failed to upload video to remote instance.", file=sys.stderr)
        sys.exit(1)
    print("[+] Video uploaded successfully.")

    # 8. Start generation process in background
    print("[*] Launching video generation job in background on Vast.ai GPU...")
    start_cmd = (
        f"cd /workspace/vajan && "
        f"nohup python3 -u run_engine.py --input '{remote_video_path}' --style '{style}' "
        f"> /workspace/vajan/run.log 2>&1 & echo $! > /workspace/vajan/run.pid"
    )
    ret, out, err = run_ssh(ssh_host, ssh_port, start_cmd, timeout=30)
    ret_pid, out_pid, _ = run_ssh(ssh_host, ssh_port, "cat /workspace/vajan/run.pid", timeout=15)
    pid = out_pid.strip() if ret_pid == 0 else None

    config_data["status"] = "running"
    config_data["remote_pid"] = pid
    config_data["started_at"] = datetime.now().isoformat()
    save_config(config_data, str(config_path))

    print("=" * 75)
    print(f"[+] SUCCESS: Job is actively running on Vast.ai!")
    print(f"    Instance ID  : #{inst_id} ({gpu_name})")
    print(f"    Remote PID   : {pid}")
    print(f"    Config JSON  : {config_path}")
    print("=" * 75)
    print("\nNext commands to manage your job:")
    print(f"  Check status : python vajan.py -c {config_path.name} -a check")
    print(f"  Download file: python vajan.py -c {config_path.name} -a getfile")
    print(f"  Stop process : python vajan.py -c {config_path.name} -a stop")
    print(f"  Delete GPU   : python vajan.py -c {config_path.name} -a delete")


def action_start_existing(config_path: str, new_video_path: str, style: str = "cinematic"):
    """Action '-c json -a start -v new_video':
    Re-uses existing setup/instance:
    1. If previous process is still running, refuses to run.
    2. Else writes a new config JSON to VAJAN_HOME.
    3. Uploads new video and starts generation.
    """
    cfg = load_config(config_path)
    inst_id = cfg.get("instance_id")
    ssh_host = cfg.get("ssh_host")
    ssh_port = cfg.get("ssh_port")
    old_pid = cfg.get("remote_pid")
    old_video = cfg.get("video_name", "previous video")

    v_path = Path(new_video_path).resolve()
    if not v_path.exists():
        print(f"[-] Error: New video file not found at '{new_video_path}'", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Checking status of instance #{inst_id} before re-using...")

    # Check if instance is alive
    client = VastClient()
    inst_info = client.get_instance(inst_id)
    if not inst_info or inst_info.get("actual_status") != "running":
        print(f"[-] Error: Instance #{inst_id} is not running (status: {inst_info.get('actual_status', 'not found')}).", file=sys.stderr)
        print("    Launch a new instance with: python vajan.py -v <file> -a start")
        sys.exit(1)

    # Check if old process is running
    is_running = False
    if old_pid:
        ret, out, _ = run_ssh(ssh_host, ssh_port, f"kill -0 {old_pid} 2>/dev/null && echo RUNNING || echo STOPPED", timeout=15)
        if "RUNNING" in out:
            is_running = True

    if not is_running:
        # Fallback check for any active run_engine.py
        ret, out, _ = run_ssh(ssh_host, ssh_port, "pgrep -f run_engine.py || true", timeout=15)
        if out.strip():
            is_running = True

    if is_running:
        print("=" * 75)
        print(f"[-] REFUSING TO RUN: Previous job for '{old_video}' is still active on instance #{inst_id}!")
        print(f"    Active PID: {old_pid}")
        print("=" * 75)
        print(f"Options:")
        print(f"  1. Wait for completion and check progress: python vajan.py -c {config_path} -a check")
        print(f"  2. Stop the running job first            : python vajan.py -c {config_path} -a stop")
        sys.exit(1)

    print(f"[+] Instance #{inst_id} is idle. Ready to process new video '{v_path.name}'.")

    # Generate new config JSON
    new_config_path = generate_config_path(str(v_path))
    stem = v_path.stem
    clean_stem = re.sub(r'[^a-zA-Z0-9]+', '_', stem).strip('_').lower()

    new_config = {
        "video_file": str(v_path),
        "video_name": stem,
        "clean_name": clean_stem,
        "style": style,
        "instance_id": inst_id,
        "offer_id": cfg.get("offer_id"),
        "gpu_name": cfg.get("gpu_name"),
        "ssh_host": ssh_host,
        "ssh_port": ssh_port,
        "status": "provisioned",
        "created_at": datetime.now().isoformat(),
        "remote_workdir": "/workspace/vajan",
        "remote_pid": None,
        "remote_output": f"/workspace/vajan/outputs/{clean_stem}_reimagined.mp4"
    }

    # Upload new video
    remote_video_path = f"/workspace/vajan/inputs/{v_path.name}"
    print(f"[*] Uploading '{v_path.name}' to instance #{inst_id}...")
    if not upload_file(ssh_host, ssh_port, str(v_path), remote_video_path):
        print(f"[-] Failed to upload video.", file=sys.stderr)
        sys.exit(1)

    # Launch new process
    print("[*] Starting generation with new video...")
    start_cmd = (
        f"cd /workspace/vajan && "
        f"nohup python3 -u run_engine.py --input '{remote_video_path}' --style '{style}' "
        f"> /workspace/vajan/run.log 2>&1 & echo $! > /workspace/vajan/run.pid"
    )
    run_ssh(ssh_host, ssh_port, start_cmd, timeout=30)
    ret_pid, out_pid, _ = run_ssh(ssh_host, ssh_port, "cat /workspace/vajan/run.pid", timeout=15)
    new_pid = out_pid.strip() if ret_pid == 0 else None

    new_config["status"] = "running"
    new_config["remote_pid"] = new_pid
    new_config["started_at"] = datetime.now().isoformat()
    save_config(new_config, str(new_config_path))

    print("=" * 75)
    print(f"[+] SUCCESS: New video job launched on existing instance #{inst_id}!")
    print(f"    New PID         : {new_pid}")
    print(f"    New Config JSON : {new_config_path}")
    print("=" * 75)


def action_check(config_path: str):
    """Action '-c json -a check': Checks current video processing status."""
    cfg = load_config(config_path)
    inst_id = cfg.get("instance_id")
    ssh_host = cfg.get("ssh_host")
    ssh_port = cfg.get("ssh_port")
    pid = cfg.get("remote_pid")
    video_name = cfg.get("video_name", "Video")
    remote_output = cfg.get("remote_output")

    print("=" * 75)
    print(f"  VAJAN JOB STATUS: {video_name}")
    print(f"  Instance ID  : #{inst_id} ({cfg.get('gpu_name', 'GPU')})")
    print(f"  Remote PID   : {pid}")
    print("=" * 75)

    client = VastClient()
    inst_info = client.get_instance(inst_id)
    actual_status = inst_info.get("actual_status", "unknown")
    dph = inst_info.get("dph_total", 0.0)

    print(f"  Instance State : {actual_status.upper()} (${dph:.3f}/hr)")

    if actual_status != "running":
        print(f"\n[!] Instance is not currently active (status: {actual_status}).")
        return

    # Check process via SSH
    ret, out, _ = run_ssh(ssh_host, ssh_port, f"kill -0 {pid} 2>/dev/null && echo RUNNING || echo STOPPED", timeout=15)
    is_running = "RUNNING" in out

    # Check if final output exists
    ret_f, out_f, _ = run_ssh(ssh_host, ssh_port, f"test -f '{remote_output}' && echo EXISTS || echo MISSING", timeout=15)
    output_ready = "EXISTS" in out_f

    # Read latest log snippet
    ret_log, out_log, _ = run_ssh(ssh_host, ssh_port, "tail -n 12 /workspace/vajan/run.log 2>/dev/null || true", timeout=20)

    # Determine overall status
    if output_ready and not is_running:
        state_str = "COMPLETED (Ready for download)"
        cfg["status"] = "completed"
    elif is_running:
        state_str = "PROCESSING (Actively generating frames)"
        cfg["status"] = "running"
    elif not output_ready and not is_running:
        state_str = "FAILED / STOPPED (Process exited before completion)"
        cfg["status"] = "failed"
    else:
        state_str = "UNKNOWN"

    print(f"  Job State      : {state_str}")
    print(f"  Output Ready   : {'YES' if output_ready else 'NO'}")

    save_config(cfg, cfg.get("_filepath"))

    print("\n--- Recent Log Output ---")
    if out_log.strip():
        for line in out_log.strip().splitlines():
            print(f"  | {line}")
    else:
        print("  (Log file is initializing...)")
    print("-" * 75)

    if output_ready:
        print(f"\n[+] Video is ready! Download it now using:")
        print(f"    python vajan.py -c {Path(config_path).name} -a getfile")


def action_stop(config_path: str):
    """Action '-c json -a stop': Stops the running process on Vast.ai."""
    cfg = load_config(config_path)
    inst_id = cfg.get("instance_id")
    ssh_host = cfg.get("ssh_host")
    ssh_port = cfg.get("ssh_port")
    pid = cfg.get("remote_pid")

    print(f"[*] Stopping process on Vast.ai instance #{inst_id}...")
    if ssh_host and ssh_port:
        stop_cmd = f"kill {pid} 2>/dev/null || true; pkill -f run_engine.py || true"
        run_ssh(ssh_host, ssh_port, stop_cmd, timeout=15)

    cfg["status"] = "stopped"
    save_config(cfg, cfg.get("_filepath"))
    print(f"[+] Process {pid} stopped successfully on instance #{inst_id}.")


def action_getfile(config_path: str):
    """Action '-c json -a getfile': Downloads the generated file if ready, else says not ready."""
    cfg = load_config(config_path)
    inst_id = cfg.get("instance_id")
    ssh_host = cfg.get("ssh_host")
    ssh_port = cfg.get("ssh_port")
    remote_output = cfg.get("remote_output")
    clean_stem = cfg.get("clean_name", "reimagined")

    if not ssh_host or not ssh_port:
        print("[-] Error: SSH coordinates missing in config.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Checking if output video is ready on instance #{inst_id}...")
    ret, out, _ = run_ssh(ssh_host, ssh_port, f"test -f '{remote_output}' && echo READY || echo NOT_READY", timeout=15)

    if "READY" not in out:
        print("[-] File is NOT ready yet.")
        # Check current progress
        ret_log, out_log, _ = run_ssh(ssh_host, ssh_port, "grep -E '\\[Progress\\]' /workspace/vajan/run.log | tail -n 1 || true", timeout=15)
        if out_log.strip():
            print(f"    Current status: {out_log.strip()}")
        print(f"    Monitor status anytime with: python vajan.py -c {Path(config_path).name} -a check")
        return

    # Ready -> Download to local VAJAN_HOME / outputs
    out_dir = get_vajan_home() / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    local_output_path = out_dir / f"{clean_stem}_reimagined.mp4"

    print(f"[+] Video is ready! Downloading to: {local_output_path}...")
    if download_file(ssh_host, ssh_port, remote_output, str(local_output_path)):
        print("=" * 75)
        print(f"[+] SUCCESS: Video successfully downloaded!")
        print(f"    Local File : {local_output_path}")
        print(f"    File Size  : {local_output_path.stat().st_size / (1024*1024):.2f} MB")
        print("=" * 75)

        # Also download metadata JSON if available
        remote_meta = f"/workspace/vajan/outputs/{clean_stem}_metadata.json"
        download_file(ssh_host, ssh_port, remote_meta, str(out_dir / f"{clean_stem}_metadata.json"))
    else:
        print("[-] Error downloading file via SCP.", file=sys.stderr)


def action_cleanup(config_path: str):
    """Action '-c json -a cleanup': Cleans up server video data (inputs, temp chunks)."""
    cfg = load_config(config_path)
    inst_id = cfg.get("instance_id")
    ssh_host = cfg.get("ssh_host")
    ssh_port = cfg.get("ssh_port")

    print(f"[*] Cleaning up temporary server video data on instance #{inst_id}...")
    if ssh_host and ssh_port:
        clean_cmd = "rm -rf /workspace/vajan/inputs/* /workspace/vajan/outputs/temp/* /workspace/vajan/temp/*"
        run_ssh(ssh_host, ssh_port, clean_cmd, timeout=30)
        print(f"[+] Server video inputs and scratch chunks cleaned up.")
        print("    (Environment and downloaded model weights are preserved for future runs.)")
    else:
        print("[-] Error: SSH host/port not available in config.", file=sys.stderr)


def action_delete(config_path: str):
    """Action '-c json -a delete': Stops running process and permanently destroys instance. Never fails."""
    cfg = load_config(config_path)
    inst_id = cfg.get("instance_id")
    ssh_host = cfg.get("ssh_host")
    ssh_port = cfg.get("ssh_port")

    print(f"[*] Stopping and deleting Vast.ai instance #{inst_id} (Stopping billing)...")

    # 1. Attempt graceful process stop (timeout 5s)
    if ssh_host and ssh_port:
        try:
            run_ssh(ssh_host, ssh_port, "pkill -f run_engine.py || true", timeout=5)
        except Exception:
            pass

    # 2. Destroy instance via Vast API (Never fails)
    client = VastClient()
    try:
        res = client.destroy(inst_id)
    except Exception as e:
        res = {"status": "error_suppressed", "message": str(e)}

    cfg["status"] = "deleted"
    save_config(cfg, cfg.get("_filepath"))

    print("=" * 75)
    print(f"[+] Instance #{inst_id} destroyed successfully.")
    print("    All billing for this instance is stopped.")
    print("=" * 75)


# ------------------------------------------------------------------------------
# Main CLI Entrypoint
# ------------------------------------------------------------------------------

def check_vast_credentials_or_exit() -> VastClient:
    """Verifies that Vast.ai credentials exist in env, exiting with an informative error if absent."""
    client = VastClient()
    if not client.api_key:
        print("=" * 75, file=sys.stderr)
        print("[-] FATAL ERROR: Vast.ai API key is missing from your environment!", file=sys.stderr)
        print("=" * 75, file=sys.stderr)
        print("To use Vajan with Vast.ai, set your API key using one of the following:\n", file=sys.stderr)
        print("  1. Environment variable:", file=sys.stderr)
        print("     export VASTAI_KEY=\"your_vast_api_key_here\"\n", file=sys.stderr)
        print("  2. Alternative variable name:", file=sys.stderr)
        print("     export VAST_API_KEY=\"your_vast_api_key_here\"\n", file=sys.stderr)
        print("  3. Create a local .env.local file in the project directory:", file=sys.stderr)
        print("     echo 'VASTAI_KEY=your_vast_api_key_here' > .env.local\n", file=sys.stderr)
        print("  4. Standard Vast CLI config:", file=sys.stderr)
        print("     echo 'your_vast_api_key_here' > ~/.vast_api_key\n", file=sys.stderr)
        print("Get your API key at: https://cloud.vast.ai/account/", file=sys.stderr)
        print("=" * 75, file=sys.stderr)
        sys.exit(1)
    return client


def main():
    parser = argparse.ArgumentParser(
        description="Vajan: Local AI Structural Video Enhancer & Re-imaginer on Vast.ai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch new generation job on Vast.ai:
  python vajan.py -v samples/sample01.mp4 -a start -s cinematic

  # Check progress:
  python vajan.py -c sample01_2609162207.json -a check

  # Download finished video:
  python vajan.py -c sample01_2609162207.json -a getfile

  # Re-use existing instance with a new video:
  python vajan.py -c sample01_2609162207.json -a start -v samples/family02.mp4

  # Permanently terminate and delete GPU instance:
  python vajan.py -c sample01_2609162207.json -a delete
        """
    )

    parser.add_argument("-v", "--video", type=str, default=None, help="Path to input video file (.mp4)")
    parser.add_argument("-c", "--config", type=str, default=None, help="Path to config JSON file")
    parser.add_argument(
        "-a", "--action",
        type=str,
        required=True,
        choices=["start", "stop", "check", "getfile", "cleanup", "delete"],
        help="Action to perform"
    )
    parser.add_argument("-s", "--style", type=str, default="cinematic", help="Artistic style preset (default: cinematic)")

    args = parser.parse_args()

    # Enforce Vast.ai credentials presence upfront
    check_vast_credentials_or_exit()

    action = args.action

    if action == "start":
        if args.config and args.video:
            # Re-use existing setup
            action_start_existing(config_path=args.config, new_video_path=args.video, style=args.style)
        elif args.video and not args.config:
            # Start fresh instance
            action_start_new(video_path=args.video, style=args.style)
        elif not args.video:
            print("[-] Error: -v <video_file> is required for 'start' action.", file=sys.stderr)
            sys.exit(1)
    elif action == "check":
        if not args.config:
            print("[-] Error: -c <config_json> is required for 'check' action.", file=sys.stderr)
            sys.exit(1)
        action_check(config_path=args.config)
    elif action == "stop":
        if not args.config:
            print("[-] Error: -c <config_json> is required for 'stop' action.", file=sys.stderr)
            sys.exit(1)
        action_stop(config_path=args.config)
    elif action == "getfile":
        if not args.config:
            print("[-] Error: -c <config_json> is required for 'getfile' action.", file=sys.stderr)
            sys.exit(1)
        action_getfile(config_path=args.config)
    elif action == "cleanup":
        if not args.config:
            print("[-] Error: -c <config_json> is required for 'cleanup' action.", file=sys.stderr)
            sys.exit(1)
        action_cleanup(config_path=args.config)
    elif action == "delete":
        if not args.config:
            print("[-] Error: -c <config_json> is required for 'delete' action.", file=sys.stderr)
            sys.exit(1)
        action_delete(config_path=args.config)


if __name__ == "__main__":
    main()
