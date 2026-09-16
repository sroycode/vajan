import gc
import torch
from typing import Dict, List, Any, Optional
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration


class LocalVLMCaptioner:
    """Local Vision-Language Model analyzer using Qwen2.5-VL-7B.
    
    Extracts action choreography, human dynamics, and camera movement from
    sampled video frames, then constructs an imaginative generation prompt.
    Includes explicit memory management to free VRAM before video diffusion.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("vlm", {})
        self.model_id = self.config.get("model_id", "Qwen/Qwen2.5-VL-7B-Instruct")
        self.quantization = self.config.get("quantization", "4bit")
        self.temperature = self.config.get("temperature", 0.7)
        self.max_new_tokens = self.config.get("max_new_tokens", 384)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.model = None
        self.processor = None

    def load(self):
        """Loads VLM into GPU memory on-demand."""
        if self.model is not None:
            return

        print(f"[VLM] Loading local vision model '{self.model_id}' (quantization: {self.quantization})...")
        self.processor = AutoProcessor.from_pretrained(self.model_id)

        model_kwargs = {
            "device_map": "auto",
            "torch_dtype": torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        }

        if self.quantization == "4bit" and torch.cuda.is_available():
            from transformers import BitsAndBytesConfig
            model_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
        elif self.quantization == "8bit" and torch.cuda.is_available():
            from transformers import BitsAndBytesConfig
            model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)

        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_id,
            **model_kwargs
        )
        print("[VLM] Model loaded successfully.")

    def unload(self):
        """Completely purges VLM from GPU memory to make room for Video DiT."""
        print("[VLM] Offloading VLM and purging VRAM cache...")
        if self.model is not None:
            del self.model
            self.model = None
        if self.processor is not None:
            del self.processor
            self.processor = None

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
        print("[VLM] VRAM cache cleared.")

    def analyze_actions_and_reimagine(
        self,
        frames: List[Image.Image],
        user_creative_prompt: Optional[str] = None,
        style_prefix: str = "",
        style_suffix: str = ""
    ) -> Dict[str, str]:
        """Analyzes video frames for physical actions and outputs a reimagined diffusion prompt."""
        self.load()

        # Construct prompt enforcing attire fidelity, authentic family action, and cinematic elevation
        analysis_instruction = (
            "You are an expert cinematographer, visual storyteller, and AI video prompt engineer. "
            "Analyze these sequential frames from a candid video clip carefully: "
            "1. Identify the subjects, their exact actions, gestures, emotional expressions, and camera motion. "
            "2. CRITICAL ATTIRE FIDELITY RULE: Maintain the authentic garment category and cultural attire of each subject. "
            "   If someone is wearing a saree, describe them as wearing an elegant, high-quality silk or cotton saree with authentic "
            "   pallu drape and rich woven texture—NEVER substitute a saree with a Western gown, dress, or costume. "
            "   If someone is wearing a kurta or traditional tunic, keep it as a refined kurta. "
            "   If wearing casual wear, describe clean, well-tailored modern apparel. Elevate the fabric quality, weave, and lighting. "
            "3. Formulate a final reimagined cinematic video prompt preserving these exact human actions and garment types, "
            "   while elevating the visuals with rich 35mm film cinematography, natural atmospheric lighting, shallow depth of field, "
            "   and authentic photorealistic textures."
        )

        if user_creative_prompt:
            analysis_instruction += f"\nAdditional creative direction: '{user_creative_prompt}'."

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": frames},
                    {"type": "text", "text": (
                        f"{analysis_instruction}\n"
                        "Return your output strictly formatted as:\n"
                        "ACTION_CHOREOGRAPHY: <concise summary of exact physical movements, postures, and camera track>\n"
                        "REIMAGINED_PROMPT: <rich, visually stunning prompt describing characters, their authentic garments (e.g. elegant silk saree), lighting, and environment executing those exact movements>"
                    )}
                ]
            }
        ]

        text_input = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = None, None
        
        # Process inputs using Qwen VL utils
        from qwen_vl_utils import process_vision_info
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self.processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                do_sample=True if self.temperature > 0 else False
            )

        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

        # Parse the structured response
        action_summary = ""
        reimagined_prompt = ""

        for line in output_text.splitlines():
            line = line.strip()
            if line.startswith("ACTION_CHOREOGRAPHY:"):
                action_summary = line.replace("ACTION_CHOREOGRAPHY:", "").strip()
            elif line.startswith("REIMAGINED_PROMPT:"):
                reimagined_prompt = line.replace("REIMAGINED_PROMPT:", "").strip()

        # Fallback if VLM didn't adhere strictly to format
        if not reimagined_prompt:
            reimagined_prompt = output_text.strip()
        if not action_summary:
            action_summary = "Natural human movement and candid interaction."

        # Add optional style wrappers
        full_final_prompt = reimagined_prompt
        if style_prefix:
            full_final_prompt = f"{style_prefix} {full_final_prompt}"
        if style_suffix:
            full_final_prompt = f"{full_final_prompt}, {style_suffix}"

        return {
            "action_summary": action_summary,
            "reimagined_prompt": full_final_prompt,
            "raw_output": output_text
        }
