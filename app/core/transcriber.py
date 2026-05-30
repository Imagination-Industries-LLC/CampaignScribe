"""WhisperX transcription + pyannote speaker diarization.

Adapted from the reference transcribe.py in CampaignScribe reference docs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def _detect_nvidia_gpu_via_smi() -> str | None:
    """Use nvidia-smi to detect a physical NVIDIA GPU even when CUDA torch isn't loaded."""
    import shutil
    import subprocess

    from app.core.proc import CREATE_NO_WINDOW

    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        out = subprocess.check_output(
            [smi, "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
        first = out.decode("utf-8", errors="replace").splitlines()
        if first and first[0].strip():
            return first[0].strip()
    except Exception:
        pass
    return None


def check_gpu() -> dict[str, Any]:
    """Probe for CUDA availability and return a status dict.

    Recommendation values:
      - "cuda"            : torch sees CUDA — GPU mode ready
      - "cpu_no_cuda"     : NVIDIA GPU detected by nvidia-smi but bundled torch is CPU-only
                            (user should install/upgrade CUDA driver or rebuild with CUDA torch)
      - "cpu_slow"        : no NVIDIA GPU at all — CPU mode is the only option
      - "cpu_unavailable" : torch failed to import — bundle is broken
    """
    smi_name = _detect_nvidia_gpu_via_smi()
    try:
        import torch

        torch_version = torch.__version__
        cuda_built = bool(getattr(torch.version, "cuda", None))
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            return {
                "cuda_available": True,
                "device_name": name,
                "vram_gb": round(vram, 1),
                "recommendation": "cuda",
                "torch_version": torch_version,
                "torch_cuda_version": torch.version.cuda,
                "smi_gpu_name": smi_name,
            }
        if smi_name:
            return {
                "cuda_available": False,
                "device_name": None,
                "vram_gb": None,
                "recommendation": "cpu_no_cuda",
                "torch_version": torch_version,
                "torch_cuda_version": torch.version.cuda if cuda_built else None,
                "smi_gpu_name": smi_name,
                "hint": (
                    "An NVIDIA GPU is present but PyTorch cannot use it. "
                    "Either the bundled torch is CPU-only (rebuild from source with the "
                    "CUDA wheel) OR your NVIDIA driver does not support the CUDA version "
                    "torch was built against ({}). "
                    "Update the NVIDIA driver from https://www.nvidia.com/Download/index.aspx "
                    "or install the CUDA toolkit from "
                    "https://developer.nvidia.com/cuda-downloads"
                ).format(torch.version.cuda or "unknown"),
            }
        return {
            "cuda_available": False,
            "device_name": None,
            "vram_gb": None,
            "recommendation": "cpu_slow",
            "torch_version": torch_version,
            "torch_cuda_version": torch.version.cuda if cuda_built else None,
            "smi_gpu_name": None,
            "hint": "No NVIDIA GPU detected. Transcription will run on CPU (very slow for "
            "long files). For GPU acceleration, install an NVIDIA GPU and the "
            "CUDA driver from https://www.nvidia.com/Download/index.aspx.",
        }
    except Exception as e:
        return {
            "cuda_available": False,
            "device_name": None,
            "vram_gb": None,
            "recommendation": "cpu_unavailable",
            "torch_version": None,
            "smi_gpu_name": smi_name,
            "error": str(e),
        }


class TranscriptionPipeline:
    """Holds long-lived WhisperX models so they are loaded once per run."""

    def __init__(self, model_size: str = "large-v3", hf_token: str = "", force_cpu: bool = False):
        self.model_size = model_size
        self.hf_token = hf_token or ""
        self.force_cpu = force_cpu
        self._model = None
        self._diarize = None
        self._align_cache: dict[str, Any] = {}

        gpu = check_gpu()
        if force_cpu or not gpu.get("cuda_available", False):
            self.device = "cpu"
            self.compute_type = "int8"
        else:
            self.device = "cuda"
            self.compute_type = "float16"

    def _load_models(self) -> None:
        if self._model is None:
            import whisperx

            # whisperx defaults vad_method='pyannote' which needs an HF token.
            # If no token is set, fall back to silero VAD which is bundled.
            load_kwargs: dict[str, Any] = {
                "compute_type": self.compute_type,
            }
            if self.hf_token:
                load_kwargs["use_auth_token"] = self.hf_token
            else:
                load_kwargs["vad_method"] = "silero"
            self._model = whisperx.load_model(self.model_size, self.device, **load_kwargs)
        if self._diarize is None:
            from whisperx.diarize import DiarizationPipeline

            # whisperx 3.8+ uses `token=`, not `use_auth_token=`. Default model is
            # `pyannote/speaker-diarization-community-1`, which needs a HuggingFace
            # token AND license acceptance on huggingface.co.
            kwargs: dict[str, Any] = {"device": self.device}
            if self.hf_token:
                kwargs["token"] = self.hf_token
            self._diarize = DiarizationPipeline(**kwargs)

    def transcribe_file(
        self,
        wav_path: str,
        num_speakers: int | None = None,
        progress: Callable[[str, float], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Run the full transcribe + align + diarize pipeline. Returns segment list."""
        import whisperx

        if progress:
            progress("Loading models", 0.05)
        self._load_models()

        if progress:
            progress("Transcribing", 0.20)
        result = self._model.transcribe(wav_path, batch_size=16)
        language = result.get("language", "en")

        if progress:
            progress("Aligning timestamps", 0.55)
        if language not in self._align_cache:
            model_a, metadata = whisperx.load_align_model(
                language_code=language, device=self.device
            )
            self._align_cache[language] = (model_a, metadata)
        model_a, metadata = self._align_cache[language]
        result = whisperx.align(result["segments"], model_a, metadata, wav_path, self.device)

        if progress:
            progress("Diarizing speakers", 0.75)
        kwargs: dict[str, Any] = {}
        if num_speakers and num_speakers > 0:
            kwargs["min_speakers"] = num_speakers
            kwargs["max_speakers"] = num_speakers
        diarize_segments = self._diarize(wav_path, **kwargs)
        result = whisperx.assign_word_speakers(diarize_segments, result)

        if progress:
            progress("Done", 1.0)
        segments = result.get("segments", [])
        normalized: list[dict[str, Any]] = []
        for seg in segments:
            normalized.append(
                {
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                    "text": (seg.get("text") or "").strip(),
                    "speaker": seg.get("speaker") or "UNKNOWN",
                }
            )
        return normalized

    def close(self) -> None:
        """Release models and free GPU memory between jobs. Idempotent."""
        self._model = None
        self._diarize = None
        self._align_cache.clear()
        import gc

        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


def save_segments_json(segments: list[dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)


def collect_speaker_samples(
    segments: list[dict[str, Any]], max_lines: int = 15
) -> dict[str, list[str]]:
    """Group sample lines per speaker id."""
    samples: dict[str, list[str]] = {}
    for seg in segments:
        sid = seg.get("speaker") or "UNKNOWN"
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        bucket = samples.setdefault(sid, [])
        if len(bucket) < max_lines:
            bucket.append(text)
    return samples
