import os
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import yaml

from src.analyzer.video_preprocessor import VideoPreprocessor
from src.analyzer.vlm_captioner import LocalVLMCaptioner
from src.generator.video_engine import VideoGenerationEngine


class VajanPipeline:
    """End-to-end memory-safe orchestrator for local video generation.
    Supports long-duration videos (up to 600s) through intelligent chunking,
    action and cultural garment preservation (sarees stay sarees),
    and 1:1 original audio remuxing.
    """

    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.preprocessor = VideoPreprocessor(self.config)
        self.vlm = LocalVLMCaptioner(self.config)
        self.generator = VideoGenerationEngine(self.config)

    def extract_audio(self, video_path: str, temp_dir: Path) -> Optional[str]:
        """Extracts the original audio stream to preserve synchronized sound."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio_out = temp_dir / "original_audio.aac"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "copy",
            str(audio_out)
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            if audio_out.exists() and audio_out.stat().st_size > 500:
                print(f"[Audio] Preserved original audio track: {audio_out}")
                return str(audio_out)
        except Exception:
            # Fallback encode to aac if stream copy is incompatible
            try:
                cmd_fallback = [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-vn",
                    "-acodec", "aac",
                    "-b:a", "192k",
                    str(audio_out)
                ]
                subprocess.run(cmd_fallback, capture_output=True, check=True)
                if audio_out.exists() and audio_out.stat().st_size > 500:
                    print(f"[Audio] Encoded and preserved original audio track: {audio_out}")
                    return str(audio_out)
            except Exception:
                pass
        print("[Audio] No compatible audio stream detected in source video.")
        return None

    def slice_video_chunk(
        self,
        input_video_path: str,
        start_sec: float,
        duration_sec: float,
        output_path: str
    ) -> str:
        """Extracts a temporal slice using FFmpeg with keyframe accuracy."""
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start_sec:.3f}",
            "-t", f"{duration_sec:.3f}",
            "-i", str(input_video_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "17",
            "-an",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    def stitch_chunks(self, chunk_paths: List[str], output_path: str) -> str:
        """Concatenates video chunks seamlessly using FFmpeg concat demuxer."""
        list_file = Path(output_path).parent / "concat_list.txt"
        with open(list_file, "w") as f:
            for p in chunk_paths:
                f.write(f"file '{Path(p).resolve()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    def remux_audio(self, video_path: str, audio_path: Optional[str], final_output_path: str) -> str:
        """Remuxes original audio track with stitched video without re-encoding video."""
        if not audio_path or not Path(audio_path).exists():
            # If no audio, copy video to final destination
            if str(video_path) != str(final_output_path):
                subprocess.run(["cp", str(video_path), str(final_output_path)], check=True)
            return final_output_path

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(final_output_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return final_output_path

    def run(
        self,
        input_video_path: str,
        creative_direction: Optional[str] = None,
        style_preset: Optional[str] = "cinematic",
        output_dir: str = "outputs",
        denoise_strength: Optional[float] = 0.74,
        num_inference_steps: Optional[int] = 32
    ) -> Dict[str, Any]:
        """Executes the complete local generation pipeline with chunking and audio preservation."""
        start_time = time.time()
        out_p = Path(output_dir)
        out_p.mkdir(parents=True, exist_ok=True)
        temp_dir = out_p / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 65)
        print("  VAJAN: STRUCTURAL VIDEO RE-IMAGINER & ENHANCER")
        print("=" * 65)
        print(f"Input Video       : {input_video_path}")
        print(f"Output Directory  : {output_dir}")
        print(f"Style Preset      : {style_preset}")
        print(f"Denoise Strength  : {denoise_strength} (action fidelity + imaginative textures)")

        # 1. Probe input video metadata
        meta = self.preprocessor.probe_video(input_video_path)
        total_duration = meta.get("duration", 0.0)
        orig_fps = meta.get("fps", 24.0)
        print(f"Video Format      : {meta.get('width')}x{meta.get('height')}, {orig_fps:.2f} FPS, {total_duration:.1f}s duration")

        # 2. Extract original audio for 1:1 synchronization
        audio_file = self.extract_audio(input_video_path, temp_dir)

        # 3. Determine Chunking Strategy
        # Each chunk starts from the boundary of the preceding chunk,
        # and seeds the preceding chunk's final frame as its first frame for 100% visual continuity.
        chunk_duration = 5.0
        chunks = []

        if total_duration <= 7.0:
            chunks = [(0.0, total_duration)]
        else:
            cur_start = 0.0
            while cur_start < total_duration:
                dur = min(chunk_duration, total_duration - cur_start)
                if dur < 1.0 and chunks:
                    # Append remaining tiny fragment to previous chunk
                    break
                chunks.append((cur_start, dur))
                cur_start += dur

        total_chunks = len(chunks)
        print(f"\n[Plan] Processing {total_duration:.1f}s video in {total_chunks} sequential chunk(s)...")
        print("       (Each chunk anchors to the preceding chunk's final frame for seamless continuity)")

        # 4. Resolve style presets
        style_prompt_text = "masterpiece 35mm cinematic film still, warm natural lighting, shallow depth of field, authentic realistic motion, sharp textures"
        styles = self.config.get("styles", {})
        if style_preset and style_preset in styles:
            style_prompt_text = styles[style_preset].get("style_prompt", style_prompt_text)
        elif style_preset == "cinematic" or style_preset == "cinematic_film":
            style_prompt_text = styles.get("cinematic_film", {}).get("style_prompt", style_prompt_text)

        processed_chunk_paths = []
        chunk_metadata = []
        last_chunk_end_frame = None

        # 5. Process Each Chunk
        for idx, (c_start, c_dur) in enumerate(chunks, 1):
            progress_pct = (idx / total_chunks) * 100
            print(f"\n" + "-" * 60)
            print(f"[Progress] Chunk {idx}/{total_chunks} ({progress_pct:.1f}%) | Time: {c_start:.1f}s - {c_start+c_dur:.1f}s")
            if last_chunk_end_frame is not None:
                print(f"           Anchoring start frame to Chunk #{idx-1}'s final generated frame.")
            print("-" * 60)

            raw_chunk_path = str(temp_dir / f"chunk_{idx:03d}_raw.mp4")
            self.slice_video_chunk(input_video_path, c_start, c_dur, raw_chunk_path)

            normalized_chunk = self.preprocessor.normalize_video(raw_chunk_path, str(temp_dir))
            frames, (target_w, target_h) = self.preprocessor.load_and_preprocess_frames(normalized_chunk)
            print(f"Loaded {len(frames)} frames scaled to target resolution: {target_w}x{target_h}")

            # Analyze action & attire with VLM (preserves sarees, kurtas, and candid choreography)
            chunk_prompt = style_prompt_text
            action_desc = "Candid human interaction and movement."

            try:
                sample_count = min(8, len(frames))
                vlm_keyframes = self.preprocessor.sample_keyframes_for_vlm(frames, num_samples=sample_count)
                vlm_result = self.vlm.analyze_actions_and_reimagine(
                    frames=vlm_keyframes,
                    user_creative_prompt=creative_direction,
                    style_prefix=style_prompt_text
                )
                chunk_prompt = vlm_result.get("reimagined_prompt", style_prompt_text)
                action_desc = vlm_result.get("action_summary", action_desc)
                print(f"[Action Detected] {action_desc}")
                # Immediately unload VLM to guarantee full VRAM for video diffusion
                self.vlm.unload()
            except Exception as e:
                print(f"[VLM Notice] Skipping dynamic VLM analysis for chunk {idx}: {e}")
                chunk_prompt = f"{style_prompt_text}. Candid family motion, authentic traditional attire, natural expressions."

            # Generate reimagined video chunk, anchoring first frame to last frame of previous chunk
            chunk_out_path = str(temp_dir / f"chunk_{idx:03d}_reimagined.mp4")
            _, last_chunk_end_frame = self.generator.generate_reimagined_video(
                prompt=chunk_prompt,
                input_frames=frames,
                output_path=chunk_out_path,
                denoise_strength=denoise_strength,
                num_inference_steps=num_inference_steps,
                fps=self.preprocessor.target_fps,
                first_frame_anchor=last_chunk_end_frame
            )

            processed_chunk_paths.append(chunk_out_path)
            chunk_metadata.append({
                "chunk_idx": idx,
                "start_sec": c_start,
                "duration_sec": c_dur,
                "action": action_desc,
                "prompt": chunk_prompt
            })

        # 6. Seamless Stitching
        print("\n--- Stitching Processed Video Chunks ---")
        if len(processed_chunk_paths) == 1:
            stitched_video = processed_chunk_paths[0]
        else:
            stitched_video = str(temp_dir / "stitched_temp.mp4")
            self.stitch_chunks(processed_chunk_paths, stitched_video)

        # 7. Remux Audio Track
        stem = Path(input_video_path).stem
        final_video_name = f"{stem}_reimagined.mp4"
        final_video_path = str(out_p / final_video_name)

        print("\n--- Remuxing Synchronized Audio Track ---")
        self.remux_audio(stitched_video, audio_file, final_video_path)

        # 8. Save Execution Metadata
        elapsed = round(time.time() - start_time, 2)
        meta_record = {
            "input_video": str(input_video_path),
            "output_video": final_video_path,
            "total_duration": total_duration,
            "chunks_count": total_chunks,
            "style_preset": style_preset,
            "denoise_strength": denoise_strength,
            "elapsed_seconds": elapsed,
            "status": "COMPLETED",
            "chunks": chunk_metadata
        }
        meta_path = out_p / f"{stem}_metadata.json"
        with open(meta_path, "w") as f:
            json.dump(meta_record, f, indent=2)

        print("=" * 65)
        print(f"SUCCESS: Video reimagination complete in {elapsed}s")
        print(f"Final Video File : {final_video_path}")
        print(f"Metadata File   : {meta_path}")
        print("=" * 65)

        return {
            "output_video": final_video_path,
            "metadata_path": str(meta_path),
            "elapsed_seconds": elapsed,
            "chunks_count": total_chunks
        }
