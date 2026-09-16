import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import cv2
import numpy as np
from PIL import Image


class VideoPreprocessor:
    """Preprocesses older mobile phone MP4 videos for generative AI pipelines.
    
    Handles:
    1. EXIF rotation / orientation correction (crucial for vertical phone videos).
    2. Variable Frame Rate (VFR) to Constant Frame Rate (CFR) normalization.
    3. Aspect ratio detection and optimal resolution bucket selection.
    4. Sensor noise filtering & lighting normalization for low-light indoor family clips.
    5. Frame extraction for VLM and DiT latent initialization.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("preprocessing", {})
        self.target_fps = self.config.get("target_fps", 16)
        self.max_frames = self.config.get("max_frames", 49)
        self.auto_orient = self.config.get("auto_orient", True)
        self.normalize_lighting = self.config.get("normalize_lighting", True)
        self.resolutions = self.config.get("resolutions", {
            "landscape": [720, 480],
            "portrait": [480, 720],
            "square": [512, 512]
        })

    def probe_video(self, video_path: str) -> Dict[str, Any]:
        """Extracts technical metadata using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(video_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            meta = json.loads(result.stdout)
        except Exception as e:
            # Fallback to OpenCV if ffprobe fails
            cap = cv2.VideoCapture(str(video_path))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS)) or 24.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            return {
                "width": w,
                "height": h,
                "fps": fps,
                "total_frames": total_frames,
                "rotation": 0,
                "duration": total_frames / fps if fps > 0 else 0
            }

        video_stream = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        # Check for rotation tags common in mobile MP4s
        rotation = 0
        side_data_list = video_stream.get("side_data_list", [])
        for side_data in side_data_list:
            if "rotation" in side_data:
                rotation = int(side_data["rotation"])
                break
        
        tags = video_stream.get("tags", {})
        if "rotate" in tags:
            rotation = int(tags["rotate"])

        # Calculate FPS
        r_frame_rate = video_stream.get("r_frame_rate", "24/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 24.0
        else:
            fps = float(r_frame_rate)

        duration = float(meta.get("format", {}).get("duration", 0))

        return {
            "width": width,
            "height": height,
            "fps": fps,
            "rotation": rotation,
            "duration": duration,
            "nb_frames": int(video_stream.get("nb_frames", 0))
        }

    def normalize_video(self, input_path: str, output_dir: str) -> str:
        """Converts input video into a clean CFR MP4 with corrected rotation."""
        output_dir_p = Path(output_dir)
        output_dir_p.mkdir(parents=True, exist_ok=True)
        
        clean_mp4 = output_dir_p / "normalized_input.mp4"
        meta = self.probe_video(input_path)

        # Build ffmpeg filters
        filters = [f"fps={self.target_fps}"]

        # Auto-rotate based on rotation metadata if needed
        # FFmpeg modern versions handle autorotate by default, but we enforce explicit orientation
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_path),
            "-vf", ",".join(filters),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",  # Strip audio for visual generation
            str(clean_mp4)
        ]

        subprocess.run(cmd, capture_output=True, check=True)
        return str(clean_mp4)

    def determine_resolution_bucket(self, width: int, height: int) -> Tuple[int, int]:
        """Determines best target resolution (landscape, portrait, or square)."""
        aspect_ratio = width / height
        if aspect_ratio >= 1.25:
            # Horizontal / Landscape
            target_w, target_h = self.resolutions["landscape"]
        elif aspect_ratio <= 0.8:
            # Vertical / Portrait (typical modern/older smartphone orientation)
            target_w, target_h = self.resolutions["portrait"]
        else:
            # Square-ish or 4:3
            target_w, target_h = self.resolutions["square"]

        # Ensure dimensions are divisible by 16 for DiT VAE encoders
        target_w = (target_w // 16) * 16
        target_h = (target_h // 16) * 16
        return target_w, target_h

    def load_and_preprocess_frames(
        self,
        normalized_video_path: str
    ) -> Tuple[List[Image.Image], Tuple[int, int]]:
        """Reads frames, applies adaptive sensor noise cleanup, and resizes to bucket."""
        cap = cv2.VideoCapture(normalized_video_path)
        frames_bgr = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames_bgr.append(frame)
            if len(frames_bgr) >= self.max_frames:
                break
        cap.release()

        if not frames_bgr:
            raise ValueError(f"Could not read any frames from {normalized_video_path}")

        orig_h, orig_w = frames_bgr[0].shape[:2]
        target_w, target_h = self.determine_resolution_bucket(orig_w, orig_h)

        processed_pil_frames = []
        
        # Optional CLAHE for underexposed or dim home video footage
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)) if self.normalize_lighting else None

        for frame in frames_bgr:
            # Mild bilateral filter to smooth high-ISO sensor noise while keeping action edges sharp
            smoothed = cv2.bilateralFilter(frame, d=5, sigmaColor=35, sigmaSpace=35)

            if self.normalize_lighting:
                lab = cv2.cvtColor(smoothed, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                l2 = clahe.apply(l)
                lab_merged = cv2.merge((l2, a, b))
                smoothed = cv2.cvtColor(lab_merged, cv2.COLOR_LAB2BGR)

            # Resize to DiT target dimensions
            resized = cv2.resize(smoothed, (target_w, target_h), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            processed_pil_frames.append(Image.fromarray(rgb))

        return processed_pil_frames, (target_w, target_h)

    def sample_keyframes_for_vlm(
        self,
        frames: List[Image.Image],
        num_samples: int = 12
    ) -> List[Image.Image]:
        """Selects evenly distributed keyframes across the clip for VLM scene analysis."""
        total = len(frames)
        if total <= num_samples:
            return frames
        indices = np.linspace(0, total - 1, num_samples, dtype=int)
        return [frames[i] for i in indices]
