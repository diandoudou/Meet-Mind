"""Offline speaker diarization models (WhisperX + pyannote)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DiarizedSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: str = "SPEAKER_00"
    words: List[Dict[str, Any]] = Field(default_factory=list)


class DiarizationResult(BaseModel):
    audio_path: str = ""
    language: str = ""
    engine: str = "whisperx+pyannote"
    segments: List[DiarizedSegment] = Field(default_factory=list)
    transcript_entries: List[Dict[str, Any]] = Field(default_factory=list)
    formatted_transcript: str = ""
    error: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)

    def to_transcript_entries(self) -> List[Dict[str, Any]]:
        if self.transcript_entries:
            return self.transcript_entries
        entries: List[Dict[str, Any]] = []
        for seg in self.segments:
            if not (seg.text or "").strip():
                continue
            entries.append(
                {
                    "speaker": seg.speaker,
                    "text": seg.text.strip(),
                    "timestamp": seg.start,
                    "end": seg.end,
                    "language": self.language or "mixed",
                }
            )
        return entries

    def to_formatted_text(self) -> str:
        if self.formatted_transcript:
            return self.formatted_transcript
        lines = []
        for entry in self.to_transcript_entries():
            lines.append(f"{entry['speaker']}: {entry['text']}")
        return "\n".join(lines)
