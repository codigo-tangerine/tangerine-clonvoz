"""Download the model snapshots explicitly before starting the offline studio."""
import os

if __name__ == "__main__":
    os.environ.pop("HF_HUB_OFFLINE", None)
    from huggingface_hub import snapshot_download

    snapshot_download("openai/whisper-base", allow_patterns=["*.json", "*.txt", "model.safetensors"])
    snapshot_download("Qwen/Qwen3-TTS-12Hz-1.7B-Base")
