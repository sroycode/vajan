#!/usr/bin/env python3
"""
run_engine.py
-------------
Remote execution engine running on the Vast.ai GPU instance.
Invoked in background by vajan CLI:
  nohup python3 -u run_engine.py --input <path> --style <style> > run.log 2>&1 &
"""

import sys
import argparse
from pathlib import Path
from src.pipeline import VajanPipeline


def main():
    parser = argparse.ArgumentParser(description="Vajan Server-Side Video Generation Engine")
    parser.add_argument("--input", "-i", type=str, required=True, help="Path to input MP4 video")
    parser.add_argument("--style", "-s", type=str, default="cinematic", help="Artistic style preset")
    parser.add_argument("--prompt", "-p", type=str, default=None, help="Optional creative prompt")
    parser.add_argument("--denoise", "-d", type=float, default=0.74, help="Denoising strength (0.68-0.80)")
    parser.add_argument("--steps", type=int, default=32, help="Diffusion inference steps")
    parser.add_argument("--output", "-o", type=str, default="outputs", help="Output directory")
    parser.add_argument("--config", "-c", type=str, default="config.yaml", help="Path to config.yaml")

    args = parser.parse_args()

    input_p = Path(args.input)
    if not input_p.exists():
        print(f"[Fatal] Input video not found at: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"=== [Vajan Engine] Starting Processing Job ===")
    print(f"Input Video : {args.input}")
    print(f"Style       : {args.style}")
    print(f"Denoise     : {args.denoise}")
    print(f"Output Dir  : {args.output}")

    pipeline = VajanPipeline(config_path=args.config)
    result = pipeline.run(
        input_video_path=args.input,
        creative_direction=args.prompt,
        style_preset=args.style,
        output_dir=args.output,
        denoise_strength=args.denoise,
        num_inference_steps=args.steps
    )

    print(f"\n=== [Vajan Engine] Job Finished Successfully ===")
    print(f"Final Video: {result.get('output_video')}")
    print(f"Elapsed: {result.get('elapsed_seconds')}s")


if __name__ == "__main__":
    main()
