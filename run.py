#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
from src.pipeline import VajanPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Vajan: Generate reimagined high-quality videos from low-res mobile footage (100% Local on Vast.ai)."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Path to the input mobile MP4 video."
    )
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default=None,
        help="Creative direction for reimagining (e.g. 'cyberpunk street', '1920s vintage ballroom', 'royal fantasy banquet')."
    )
    parser.add_argument(
        "--style", "-s",
        type=str,
        default="cinematic_film",
        choices=["cinematic_film", "cyberpunk_scifi", "vintage_victorian", "studio_fashion", "watercolor_anime"],
        help="Predefined artistic style preset from config.yaml."
    )
    parser.add_argument(
        "--denoise", "-d",
        type=float,
        default=None,
        help="Denoising strength (0.60 to 0.85). Default is 0.75. Higher = more imaginative divergence from original faces/clothing."
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=None,
        help="Number of diffusion inference steps (e.g. 30-50). Default is 35."
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="outputs",
        help="Directory to save generated outputs and metadata."
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config.yaml",
        help="Path to configuration YAML file."
    )

    args = parser.parse_args()

    input_p = Path(args.input)
    if not input_p.exists():
        print(f"Error: Input video not found at '{args.input}'")
        sys.exit(1)

    pipeline = VajanPipeline(config_path=args.config)
    
    result = pipeline.run(
        input_video_path=args.input,
        creative_direction=args.prompt,
        style_preset=args.style,
        output_dir=args.output,
        denoise_strength=args.denoise,
        num_inference_steps=args.steps
    )

    print(f"\nFinished! Watch the result at: {result['output_video']}")


if __name__ == "__main__":
    main()
