import os
import gc
import torch
from pathlib import Path
from typing import Dict, List, Any, Optional
from PIL import Image
from diffusers import (
    CogVideoXPipeline,
    CogVideoXVideoToVideoPipeline,
    AutoencoderKLCogVideoX
)
from diffusers.utils import export_to_video


class VideoGenerationEngine:
    """Local Video Diffusion Engine running on Vast.ai GPU.
    
    Supports structural motion transfer with creative reimagining using
    CogVideoX and Wan2.1 diffusion transformers.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("generator", {})
        self.model_id = self.config.get("default_model", "THUDM/CogVideoX-5B")
        self.precision_str = self.config.get("precision", "bfloat16")
        self.dtype = torch.bfloat16 if self.precision_str == "bfloat16" else torch.float16
        self.enable_cpu_offload = self.config.get("enable_model_cpu_offload", True)
        self.enable_vae_slicing = self.config.get("enable_vae_slicing", True)
        self.enable_vae_tiling = self.config.get("enable_vae_tiling", True)
        self.num_inference_steps = self.config.get("num_inference_steps", 35)
        self.guidance_scale = self.config.get("guidance_scale", 6.5)
        self.denoise_strength = self.config.get("denoise_strength", 0.75)

        self.pipe = None

    def load_pipeline(self, mode: str = "video_to_video"):
        """Loads the local video diffusion pipeline with memory optimizations."""
        if self.pipe is not None:
            return

        print(f"[VideoEngine] Loading local diffusion pipeline '{self.model_id}' (mode: {mode})...")

        if "CogVideoX" in self.model_id:
            if mode == "video_to_video":
                self.pipe = CogVideoXVideoToVideoPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=self.dtype
                )
            else:
                self.pipe = CogVideoXPipeline.from_pretrained(
                    self.model_id,
                    torch_dtype=self.dtype
                )
        else:
            # Generic auto-pipeline for other DiT architectures (e.g. Wan2.1 / LTX-Video)
            from diffusers import AutoPipelineForImage2Video
            self.pipe = AutoPipelineForImage2Video.from_pretrained(
                self.model_id,
                torch_dtype=self.dtype
            )

        # Apply memory optimizations
        if self.enable_vae_slicing and hasattr(self.pipe, "vae") and hasattr(self.pipe.vae, "enable_slicing"):
            self.pipe.vae.enable_slicing()
        if self.enable_vae_tiling and hasattr(self.pipe, "vae") and hasattr(self.pipe.vae, "enable_tiling"):
            self.pipe.vae.enable_tiling()

        if self.enable_cpu_offload and torch.cuda.is_available():
            print("[VideoEngine] Enabling model CPU offload (preserves VRAM for generation)...")
            self.pipe.enable_model_cpu_offload()
        elif torch.cuda.is_available():
            self.pipe.to("cuda")

        print("[VideoEngine] Diffusion pipeline ready.")

    def generate_reimagined_video(
        self,
        prompt: str,
        input_frames: List[Image.Image],
        output_path: str,
        denoise_strength: Optional[float] = None,
        num_inference_steps: Optional[int] = None,
        fps: int = 16,
        first_frame_anchor: Optional[Image.Image] = None
    ) -> Tuple[str, Image.Image]:
        """Executes structural video-to-video generation with frame continuity.
        
        Args:
            prompt: The reimagined prompt from VLM/user.
            input_frames: The preprocessed PIL frames from the source video.
            output_path: Target .mp4 file location.
            denoise_strength: Strength of reimagination (0.65 - 0.85).
            num_inference_steps: Diffusion denoising steps.
            fps: Output framerate.
            first_frame_anchor: Last generated frame of the preceding chunk.
        """
        self.load_pipeline(mode="video_to_video")

        strength = denoise_strength if denoise_strength is not None else self.denoise_strength
        steps = num_inference_steps if num_inference_steps is not None else self.num_inference_steps

        # CogVideoX requires frame count to be (k * 8 + 1) e.g. 49
        num_frames = len(input_frames)
        valid_frames = ((num_frames - 1) // 8) * 8 + 1
        trimmed_frames = list(input_frames[:valid_frames])

        # Auto-regressive continuity: bind first frame to last frame of previous chunk
        if first_frame_anchor is not None and len(trimmed_frames) > 0:
            target_size = trimmed_frames[0].size
            anchor_resized = first_frame_anchor.resize(target_size, Image.Resampling.LANCZOS)
            trimmed_frames[0] = anchor_resized
            print("[VideoEngine] Anchored first frame to previous chunk's final frame for seamless continuity.")

        print(f"[VideoEngine] Starting generation:")
        print(f"  - Prompt: '{prompt[:100]}...'")
        print(f"  - Input Frames: {len(trimmed_frames)} at {trimmed_frames[0].size}")
        print(f"  - Denoise Strength: {strength} (higher = more imaginative divergence)")
        print(f"  - Steps: {steps}")

        generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(42)

        # Run diffusion
        with torch.inference_mode():
            if isinstance(self.pipe, CogVideoXVideoToVideoPipeline):
                output = self.pipe(
                    video=trimmed_frames,
                    prompt=prompt,
                    num_inference_steps=steps,
                    guidance_scale=self.guidance_scale,
                    strength=strength,
                    generator=generator
                )
            else:
                # Text-to-Video / I2V fallback
                output = self.pipe(
                    prompt=prompt,
                    num_inference_steps=steps,
                    guidance_scale=self.guidance_scale,
                    generator=generator
                )

        output_frames = list(output.frames[0])

        # Ensure exact frame-level stitch match if anchored
        if first_frame_anchor is not None and len(output_frames) > 0:
            output_frames[0] = first_frame_anchor.resize(output_frames[0].size, Image.Resampling.LANCZOS)

        last_frame = output_frames[-1]

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        print(f"[VideoEngine] Exporting video to {output_path}...")
        export_to_video(output_frames, output_path, fps=fps)

        return output_path, last_frame

    def unload(self):
        """Unload pipeline to free memory."""
        if self.pipe is not None:
            del self.pipe
            self.pipe = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
