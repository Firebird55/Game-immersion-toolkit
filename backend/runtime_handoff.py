"""Bounded local capture state transferred to a prepared app replacement."""
from pydantic import BaseModel, Field


class CaptureHandoff(BaseModel):
    running: bool = False
    session_id: str = Field(default='', max_length=80)
    last_emitted_at: dict[str, float] = Field(default_factory=dict, max_length=2048)
    last_emitted_key_by_channel: dict[str, str] = Field(default_factory=dict, max_length=16)
    cinematic_seen_ids: list[str] = Field(default_factory=list, max_length=2048)
    cinematic_panel_text: str = Field(default='', max_length=20000)
