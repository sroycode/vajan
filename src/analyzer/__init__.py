from .video_preprocessor import VideoPreprocessor

def get_vlm_captioner(*args, **kwargs):
    from .vlm_captioner import LocalVLMCaptioner
    return LocalVLMCaptioner(*args, **kwargs)

__all__ = ["VideoPreprocessor", "get_vlm_captioner"]
