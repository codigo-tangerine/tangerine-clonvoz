from functools import lru_cache

MODEL = "openai/whisper-base"


@lru_cache(maxsize=1)
def recognizer():
    from huggingface_hub import snapshot_download
    from transformers import pipeline

    root = snapshot_download(MODEL, local_files_only=True)
    return pipeline("automatic-speech-recognition", model=root, tokenizer=root,
                    feature_extractor=root, device=-1, chunk_length_s=25)


def transcribe(wav, language):
    import subprocess

    import numpy as np

    options = {"task": "transcribe"}
    if language != "Auto":
        options["language"] = language.lower()
    audio = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(wav), "-ac", "1", "-ar", "16000",
         "-f", "f32le", "pipe:1"], capture_output=True, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    result = recognizer()(np.frombuffer(audio, dtype=np.float32), generate_kwargs=options)
    return result["text"].strip()
