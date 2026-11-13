"""WhisperX + pyannote offline ASR alignment and speaker diarization."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from diarization.models import DiarizationResult, DiarizedSegment


def _device() -> str:
    forced = os.getenv("DIARIZATION_DEVICE", "").strip()
    if forced:
        return forced
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _compute_type(device: str) -> str:
    env = os.getenv("WHISPERX_COMPUTE_TYPE", "").strip()
    if env:
        return env
    # CPU float16 is often unsupported; prefer int8/float32
    return "float16" if device.startswith("cuda") else "int8"


def _whisper_model_name() -> str:
    return os.getenv("WHISPERX_MODEL", "base")


def _hf_token() -> Optional[str]:
    return (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_TOKEN")
        or os.getenv("PYANNOTE_TOKEN")
        or None
    )


def _min_speakers() -> Optional[int]:
    raw = os.getenv("DIARIZATION_MIN_SPEAKERS", "").strip()
    return int(raw) if raw.isdigit() else None


def _max_speakers() -> Optional[int]:
    raw = os.getenv("DIARIZATION_MAX_SPEAKERS", "").strip()
    return int(raw) if raw.isdigit() else None


def is_offline_diarization_enabled() -> bool:
    return os.getenv("DIARIZATION_OFFLINE_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def whisperx_available() -> bool:
    try:
        import whisperx  # noqa: F401

        return True
    except Exception:
        return False


def _segments_from_whisperx_result(result: Dict[str, Any]) -> List[DiarizedSegment]:
    segments: List[DiarizedSegment] = []
    for seg in result.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        speaker = seg.get("speaker") or "SPEAKER_00"
        words = seg.get("words") or []
        segments.append(
            DiarizedSegment(
                start=float(seg.get("start") or 0.0),
                end=float(seg.get("end") or 0.0),
                text=text,
                speaker=str(speaker),
                words=words if isinstance(words, list) else [],
            )
        )
    return segments


def run_whisperx_pyannote(
    audio_path: str,
    *,
    language: Optional[str] = None,
) -> DiarizationResult:
    """
    Offline pipeline:
      audio → WhisperX ASR → forced alignment → pyannote diarization → assign speakers

    Requires optional deps: whisperx, pyannote.audio, torch, and HF_TOKEN for pyannote.
    """
    path = Path(audio_path)
    if not path.exists():
        return DiarizationResult(audio_path=audio_path, error=f"audio not found: {audio_path}")

    if not is_offline_diarization_enabled():
        return DiarizationResult(
            audio_path=str(path),
            error="offline diarization disabled (DIARIZATION_OFFLINE_ENABLED=false)",
            engine="disabled",
        )

    started = time.time()
    try:
        import whisperx
    except Exception as exc:
        return DiarizationResult(
            audio_path=str(path),
            error=f"whisperx not installed: {exc}",
            engine="unavailable",
        )

    device = _device()
    compute_type = _compute_type(device)
    model_name = _whisper_model_name()
    batch_size = int(os.getenv("WHISPERX_BATCH_SIZE", "8"))
    meta: Dict[str, Any] = {
        "device": device,
        "compute_type": compute_type,
        "whisper_model": model_name,
        "batch_size": batch_size,
    }

    try:
        audio = whisperx.load_audio(str(path))
        asr_model = whisperx.load_model(model_name, device, compute_type=compute_type)
        asr_result = asr_model.transcribe(audio, batch_size=batch_size, language=language)
        detected_lang = language or asr_result.get("language") or "en"
        meta["language"] = detected_lang

        # Free ASR model VRAM before alignment/diarization when possible
        del asr_model

        align_model, align_metadata = whisperx.load_align_model(
            language_code=detected_lang,
            device=device,
        )
        aligned = whisperx.align(
            asr_result["segments"],
            align_model,
            align_metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        del align_model

        token = _hf_token()
        if not token:
            # Still return aligned transcript without speaker labels
            segments = _segments_from_whisperx_result(aligned)
            result = DiarizationResult(
                audio_path=str(path),
                language=detected_lang,
                engine="whisperx-align-only",
                segments=segments,
                error="HF_TOKEN missing; skipped pyannote speaker assignment",
                meta={**meta, "latency_ms": int((time.time() - started) * 1000)},
            )
            result.transcript_entries = result.to_transcript_entries()
            result.formatted_transcript = result.to_formatted_text()
            return result

        # Prefer new whisperx.diarize API, fall back to older import paths
        DiarizationPipeline = None
        try:
            from whisperx.diarize import DiarizationPipeline as _DP

            DiarizationPipeline = _DP
        except Exception:
            try:
                DiarizationPipeline = whisperx.DiarizationPipeline
            except Exception as exc:
                return DiarizationResult(
                    audio_path=str(path),
                    language=detected_lang,
                    engine="whisperx",
                    error=f"DiarizationPipeline unavailable: {exc}",
                    meta=meta,
                )

        diarize_kwargs: Dict[str, Any] = {"device": device}
        # auth token arg name differs across versions
        try:
            diarize_model = DiarizationPipeline(use_auth_token=token, **diarize_kwargs)
        except TypeError:
            diarize_model = DiarizationPipeline(token=token, **diarize_kwargs)

        diarize_call_kwargs: Dict[str, Any] = {}
        min_spk = _min_speakers()
        max_spk = _max_speakers()
        if min_spk is not None:
            diarize_call_kwargs["min_speakers"] = min_spk
        if max_spk is not None:
            diarize_call_kwargs["max_speakers"] = max_spk

        try:
            diarize_segments = diarize_model(str(path), **diarize_call_kwargs)
        except TypeError:
            diarize_segments = diarize_model(audio, **diarize_call_kwargs)

        assigned = whisperx.assign_word_speakers(diarize_segments, aligned)
        segments = _segments_from_whisperx_result(assigned)
        result = DiarizationResult(
            audio_path=str(path),
            language=detected_lang,
            engine="whisperx+pyannote",
            segments=segments,
            meta={
                **meta,
                "num_speakers": len({s.speaker for s in segments}),
                "latency_ms": int((time.time() - started) * 1000),
            },
        )
        result.transcript_entries = result.to_transcript_entries()
        result.formatted_transcript = result.to_formatted_text()
        print(
            f"[Diarization] done engine={result.engine} segs={len(segments)} "
            f"speakers={result.meta.get('num_speakers')} "
            f"latency_ms={result.meta.get('latency_ms')}"
        )
        return result
    except Exception as exc:
        print(f"[Diarization] failed: {exc}")
        return DiarizationResult(
            audio_path=str(path),
            error=str(exc),
            engine="whisperx+pyannote",
            meta={**meta, "latency_ms": int((time.time() - started) * 1000)},
        )


def merge_diarization_into_live_transcript(
    live_entries: List[Dict[str, Any]],
    diarized: DiarizationResult,
) -> List[Dict[str, Any]]:
    """
    Prefer diarized WhisperX transcript when available; otherwise keep live DashScope entries.
    """
    diarized_entries = diarized.to_transcript_entries()
    if diarized_entries and not diarized.error:
        return diarized_entries
    if diarized_entries and diarized.engine.endswith("align-only"):
        return diarized_entries
    return live_entries
