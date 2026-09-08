from __future__ import annotations

import html
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rapidfuzz import fuzz, process

from .models import TextMatch
from .textmaps import display_text, normalize_english


REF_RE = re.compile(r"<REF\s+([^>]+)>", re.IGNORECASE)
SPEAKER_CODE_RE = re.compile(r"_(Ch\d{5})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PragmataRecord:
    text_id: str
    english: str
    chinese: str
    source: str
    speaker_code: str | None = None


class PragmataTextIndex:
    """Official bilingual PRAGMATA dialogue extracted from RE Engine MSG files."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "textmap.json"
        self._lock = threading.RLock()
        self._records: dict[str, list[PragmataRecord]] = {}
        self._choices: list[str] = []
        self._speaker_names: dict[str, tuple[str, str]] = {}
        self.ready = False
        self.state = "not_ready"
        self.message = "PRAGMATA dialogue has not been indexed"
        self.entry_count = 0

    def load(self) -> bool:
        if not self.path.is_file():
            return False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records: dict[str, list[PragmataRecord]] = {}
            for item in payload.get("records", []):
                record = PragmataRecord(**item)
                normalized = normalize_english(record.english)
                if len(normalized) >= 2:
                    records.setdefault(normalized, []).append(record)
            names = {
                normalize_english(key): (str(value[0]), str(value[1]))
                for key, value in payload.get("speakers", {}).items()
                if key and isinstance(value, list) and len(value) >= 2
            }
            with self._lock:
                self._records = records
                self._choices = list(records)
                self._speaker_names = names
                self.entry_count = sum(len(items) for items in records.values())
                self.ready = True
                self.state = "ready"
                self.message = f"{self.entry_count:,} official PRAGMATA dialogue pairs indexed"
            return True
        except Exception as error:
            with self._lock:
                self.ready = False
                self.state = "error"
                self.message = str(error)
            return False

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "ready": self.ready,
                "state": self.state,
                "message": self.message,
                "entry_count": self.entry_count,
            }

    @staticmethod
    def _looks_like_speaker(value: str) -> bool:
        value = display_text(value).strip(" .·•")
        return bool(value) and len(value) <= 32 and len(value.split()) <= 4

    def resolve_speaker(self, value: str | None) -> tuple[str | None, str | None]:
        if not value:
            return None, None
        cleaned = display_text(value).strip(" .·•")
        result = self._speaker_names.get(normalize_english(cleaned))
        return result if result else (cleaned, None)

    def match_lines(self, lines: Iterable[str], threshold: float = 82) -> TextMatch | None:
        cleaned = [display_text(line) for line in lines if display_text(line)]
        if not cleaned:
            return None
        candidates: list[tuple[str, str | None]] = []
        speaker = cleaned[0] if len(cleaned) >= 2 and self._looks_like_speaker(cleaned[0]) else None
        body = cleaned[1:] if speaker else cleaned
        candidates.append((" ".join(body), speaker))
        candidates.append((" ".join(cleaned), None))
        # OneOCR occasionally splits the speaker label or subtitle oddly.
        if len(body) > 1:
            for start in range(len(body)):
                candidates.append((" ".join(body[start:]), speaker))
        matches = [self.match_text(text, threshold, speaker) for text, speaker in candidates]
        return max(
            (item for item in matches if item is not None),
            key=lambda item: (item.score, len(normalize_english(item.source_ocr))),
            default=None,
        )

    def match_text(
        self, value: str, threshold: float = 82, speaker: str | None = None
    ) -> TextMatch | None:
        source = display_text(value)
        normalized = normalize_english(source)
        if len(normalized) < 2:
            return None
        with self._lock:
            records = self._records.get(normalized)
            score = 100.0
            kind = "exact"
            if not records:
                result = process.extractOne(normalized, self._choices, scorer=fuzz.ratio, score_cutoff=threshold)
                if result is None:
                    return None
                choice, score, _ = result
                records = self._records.get(choice)
                kind = "fuzzy"
            if not records:
                return None
            record = records[0]
            speaker_english, speaker_chinese = self.resolve_speaker(speaker)
            return TextMatch(
                game="pragmata",
                text_id=f"pragmata:{record.text_id}",
                english=record.english,
                chinese=record.chinese,
                source_ocr=source,
                score=float(score),
                kind=kind,
                ambiguous=len(records) > 1,
                speaker_english=speaker_english,
                speaker_chinese=speaker_chinese,
            )

    @staticmethod
    def is_capture_text(_text_id: str, english: str, _channel: str) -> bool:
        return bool(display_text(english))
