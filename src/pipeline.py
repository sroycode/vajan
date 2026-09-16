import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
import yaml

from src.analyzer.video_preprocessor import VideoPreprocessor
from src.analyzer.vlm_captioner import LocalVLMCaptioner
from src.generator.video_engine import VideoGenerationEngine


class VajanPipeline:
    """End-to-end memory-safe orchestrator for local video generation."""

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.preprocessor = VideoPreprocessor(self.config)
        self.vlm = LocalVLMCaptioner(self.config)
        self.generator = VideoGenerationEngine(self.config)

    def run(
        self,
        input_video_path: str,
        creative_direction: Optional[str] = None,
        style_preset: Optional[str] = None,
        output_dir: str = "outputs",
        denoise_strength: Optional[float] = None,
        num_inference_steps: Optional[int] = None
    ) -> Dict[str, Any]:
        """Executes the full local generation pipeline.
        
        Args:
            input_video_path: Path to raw input mobile video (.mp4)
            creative_direction: Specific instructions (e.g. 'Victorian ballroom, elegant gowns')
            style_preset: One of the presets from config.yaml ('cinematic_film', 'cyberpunk_scifi', etc.)
            output_dir: Destination folder for output and intermediate files
            denoise_strength: Override denoise strength (0.65 - 0.85)
            num_inference_steps: Override diffusion steps
        """
        start_time = time.time()
        out_p = Path(output_dir)
        out_p.mkdir(parents=True, exist_ok=True)

        print("=" * 60)
        print("  VAJAN: LOCAL VIDEO RE-IMAGINER & STRUCTURAL GENERATOR")
        print("=" * 60)
        print(f"Input: {input_video_path}")
        print(f"Output Directory: {output_dir}")

        # Resolve style presets
        style_prefix = ""
        style_suffix = ""
        if style_preset:
            styles = self.config.get("styles", {})
            if style_preset in styles:
                style_prefix = styles[style_preset].get("prefix", "")
                style_suffix = styles[style_preset].get("suffix", "")
                print(f"Applying Style Preset: [{style_preset}]")
            else:
                print(f"Warning: Style preset '{style_preset}' not found. Available: {list(styles.keys())}")

        # --- STAGE 1: VIDEO PREPROCESSING ---
        print("\n--- [Stage 1/3] Preprocessing Mobile Video ---")
        meta = self.preprocessor.probe_video(input_video_path)
        print(f"Detected format: {meta.get('width')}x{meta.get('height')}, {round(meta.get('fps', 0), 2)} FPS, rotation: {meta.get('rotation')} deg")

        normalized_mp4 = self.preprocessor.normalize_video(input_video_path, str(out_p / "temp"))
        frames, (target_w, target_h) = self.preprocessor.load_and_preprocess_frames(normalized_mp4)
        print(f"Extracted {len(frames)} frames scaled to target bucket: {target_w}x{target_h}")

        # --- STAGE 2: VLM ACTION UNDERSTANDING & RE-IMAGINING ---
        print("\n--- [Stage 2/3] Local VLM Scene & Action Analysis ---")
        sample_count = self.config.get("vlm", {}).get("sample_frames", 12)
        vlm_keyframes = self.preprocessor.sample_keyframes_for_vlm(frames, num_samples=sample_count)

        vlm_result = self.vlm.analyze_actions_and_reimagine(
            frames=vlm_keyframes,
            user_creative_prompt=creative_direction,
            style_prefix=style_prefix,
            style_suffix=style_suffix
        )

        print(f"\n[Detected Action Choreography]:\n  {vlm_result['action_summary']}")
        print(f"\n[Generated Reimagined Prompt]:\n  {vlm_result['reimagined_prompt']}")

        # Free VRAM immediately before loading the diffusion generator
        self.vlm.unload()

        # Save metadata JSON
        meta_record = {
            "input_video": str(input_video_path),
            "original_metadata": meta,
            "target_resolution": [target_w, target_h],
            "action_summary": vlm_result["action_summary"],
            "reimagined_prompt": vlm_result["reimagined_prompt"],
            "denoise_strength": denoise_strength or self.generator.denoise_strength,
            "style_preset": style_preset,
            "creative_direction": creative_direction
        }
        with open(out_p / "run_metadata.json", "w") as f:
            json.dump(meta_record, f, indent=2)

        # --- STAGE 3: VIDEO DIFFUSION SYNTHESIS ---
        print("\n--- [Stage 3/3] Local Video DiT Synthesis ---")
        final_video_path = str(out_p / "reimagined_output.mp4")

        self.generator.generate_reimagined_video(
            prompt=vlm_result["reimagined_prompt"],
            input_frames=frames,
            output_path=final_video_path,
            denoise_strength=denoise_strength,
            num_inference_steps=num_inference_steps,
            fps=self.preprocessor.target_fps
        )

        elapsed = round(time.time() - start_time, 2)
        print("=" * 60)
        print(f"SUCCESS: Video generated in {elapsed}s")
        print(f"Result saved to: {final_video_path}")
        print("=" * 60)

        return {
            "output_video": final_video_path,
            "metadata_path": str(out_p / "run_metadata.json"),
            "action_summary": vlm_result["action_summary"],
            "prompt": vlm_result["reimagined_prompt"],
            "elapsed_seconds": elapsed
        }
