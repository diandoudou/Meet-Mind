"""Offline diarization package (WhisperX + pyannote)."""

from diarization.models import DiarizationResult, DiarizedSegment
from diarization.whisperx_pipeline import (
    is_offline_diarization_enabled,
    merge_diarization_into_live_transcript,
    run_whisperx_pyannote,
    whisperx_available,
)

__all__ = [
    "DiarizationResult",
    "DiarizedSegment",
    "is_offline_diarization_enabled",
    "merge_diarization_into_live_transcript",
    "run_whisperx_pyannote",
    "whisperx_available",
]
