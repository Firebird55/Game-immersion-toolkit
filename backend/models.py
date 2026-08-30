from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CaptureRegion(BaseModel):
    left: float = Field(default=0.08, ge=0, le=1)
    top: float = Field(default=0.67, ge=0, le=1)
    width: float = Field(default=0.84, gt=0, le=1)
    height: float = Field(default=0.25, gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "CaptureRegion":
        if self.left + self.width > 1.0001:
            raise ValueError("Capture region extends beyond the right edge")
        if self.top + self.height > 1.0001:
            raise ValueError("Capture region extends beyond the bottom edge")
        return self


class AppSettings(BaseModel):
    process_names: list[str] = Field(default_factory=lambda: ["ZenlessZoneZero.exe"])
    window_title_contains: list[str] = Field(
        default_factory=lambda: ["Zenless Zone Zero", "ZenlessZoneZero"]
    )
    region: CaptureRegion = Field(default_factory=CaptureRegion)
    tip_region: CaptureRegion = Field(
        default_factory=lambda: CaptureRegion(left=0.62, top=0.015, width=0.37, height=0.19)
    )
    cinematic_region: CaptureRegion = Field(
        default_factory=lambda: CaptureRegion(left=0.04, top=0.06, width=0.92, height=0.88)
    )
    scan_interval_ms: int = Field(default=250, ge=100, le=5000)
    stable_frames: int = Field(default=2, ge=1, le=8)
    fuzzy_threshold: float = Field(default=82.0, ge=50, le=100)
    auto_start: bool = True
    save_unmatched: bool = False

    @field_validator("process_names", "window_title_contains")
    @classmethod
    def strip_string_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class TextMatch(BaseModel):
    text_id: str
    english: str
    chinese: str
    source_ocr: str
    score: float
    kind: Literal["exact", "fuzzy"]
    ambiguous: bool = False


class TranscriptLine(BaseModel):
    id: int
    created_at: datetime
    session_id: str
    source_ocr: str
    english: str
    chinese: str
    text_id: str
    score: float
    match_kind: str
    ambiguous: bool = False
    channel: Literal["dialogue", "tip", "cinematic"] = "dialogue"
    voiced: bool = False
    has_audio: bool = False


class CaptureSnapshot(BaseModel):
    running: bool = False
    phase: str = "stopped"
    message: str = "Capture is stopped"
    window_title: str | None = None
    window_bounds: tuple[int, int, int, int] | None = None
    crop_bounds: tuple[int, int, int, int] | None = None
    tip_crop_bounds: tuple[int, int, int, int] | None = None
    cinematic_crop_bounds: tuple[int, int, int, int] | None = None
    last_ocr: str = ""
    last_ocr_confidence: float | None = None
    last_tip_ocr: str = ""
    last_tip_ocr_confidence: float | None = None
    last_tip_match_score: float | None = None
    last_cinematic_ocr: str = ""
    last_cinematic_ocr_confidence: float | None = None
    last_cinematic_match_score: float | None = None
    last_match_score: float | None = None
    last_scan_at: datetime | None = None
    last_error: str | None = None
