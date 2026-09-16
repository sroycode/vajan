import os
import subprocess
import json
from pathlib import Path
from typing import Optional


class AudioManager:
    """Extracts, verifies, and remuxes audio streams for frame-accurate sync."""

    @staticmethod
    def has_audio(video_path: str) -> bool:
        """Checks whether the input video contains an audio stream."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "json",
            str(video_path)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            return len(data.get("streams", [])) > 0
        except Exception:
            return False

    @staticmethod
    def extract_audio(video_path: str, output_audio_path: str) -> Optional[str]:
        """Extracts audio from video file without re-encoding if possible."""
        if not AudioManager.has_audio(video_path):
            print(f"[AudioManager] No audio stream found in {video_path}")
            return None

        Path(output_audio_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_audio_path)
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"[AudioManager] Extracted audio to: {output_audio_path}")
            return output_audio_path
        except Exception as e:
            print(f"[AudioManager] Audio extraction failed: {e}")
            return None

    @staticmethod
    def mux_audio_video(video_path: str, audio_path: Optional[str], output_path: str) -> str:
        """Combines reimagined video stream with source audio, preserving timing."""
        if not audio_path or not os.path.exists(audio_path):
            print("[AudioManager] No audio provided or found; copying video as-is.")
            if video_path != output_path:
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_path)
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            print(f"[AudioManager] Successfully remuxed synchronized audio into: {output_path}")
            return output_path
        except Exception as e:
            print(f"[AudioManager] Failed to remux audio ({e}); falling back to mute video.")
            if video_path != output_path:
                import shutil
                shutil.copy2(video_path, output_path)
            return output_path
