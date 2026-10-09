"""Subtitle matching helpers shared by games with English and Mandarin text."""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Iterable

from rapidfuzz import fuzz, process

from .textmaps import display_text, normalize_english

HAN_RE = re.compile(r"[\u3400-\u9fff\U00020000-\U0003134f]")


def contains_han(value: str) -> bool:
    return bool(HAN_RE.search(value))


def normalize_chinese(value: str) -> str:
    # OCR spaces between ideographs and full-width punctuation are display
    # artifacts. Preserve Latin words/numbers that belong to Chinese dialogue.
    return "".join(char for char in unicodedata.normalize("NFKC", display_text(value)).casefold()
                   if char.isalnum())


def normalize_subtitle(value: str) -> str:
    return normalize_chinese(value) if contains_han(value) else normalize_english(value)


def subtitle_candidates(lines: Iterable[str]) -> list[str]:
    """Keep wrapped language blocks separate, including bilingual speaker labels."""
    cleaned = [display_text(line).lstrip("~～ ") for line in lines if display_text(line)]
    separated = []
    for line in cleaned:
        parts = [part.strip() for part in re.split(r"\s*[~～]\s*", line) if part.strip()]
        # Witcher Dual Subtitles uses '~' for same-row or wrapped pairs. Keep
        # ordinary tildes within a single language as part of the utterance.
        separated.extend(parts if len({contains_han(part) for part in parts}) > 1 else [line])
    cleaned = separated
    # Some layouts/OCR versions flatten the mod's newline. Split at a sentence
    # boundary, retaining Latin names embedded within ordinary Chinese text.
    cleaned = [part.strip() for line in cleaned for part in re.split(
        r"(?<=[。！？])\s*(?=[A-Za-z])|(?<=[.!?])\s*(?=[\u3400-\u9fff])", line) if part.strip()]
    candidates: list[str] = []
    for start in range(len(cleaned)):
        for end in range(start + 1, min(len(cleaned), start + 8) + 1):
            block = cleaned[start:end]
            if len({contains_han(line) for line in block}) > 1:
                continue
            value = " ".join(block)
            candidates.append(value)
            # Names may precede dialogue on the same OCR row.
            if re.search(r"[:：]", value):
                candidates.append(re.split(r"[:：]", value, maxsplit=1)[1].strip())
    return list(dict.fromkeys(value for value in candidates if value))


class ChineseLookup:
    def __init__(self, records: Iterable[object]):
        self.records: dict[str, list] = {}
        for record in records:
            key = normalize_chinese(record.chinese)
            if contains_han(record.chinese) and len(key) >= 2:
                self.records.setdefault(key, []).append(record)
        self._choices: dict[str, list[str]] = {}

    def match(self, value: str, threshold: float, allowed: Callable = lambda _record: True,
              channel: str = "dialogue") -> tuple[list, float] | None:
        key = normalize_chinese(value)
        if not contains_han(value) or len(key) < 2:
            return None
        exact = [record for record in self.records.get(key, []) if allowed(record)]
        if exact:
            return exact, 100.0
        if key in self.records:
            return None  # An exact record belongs to an excluded channel.
        # Short Hanzi fragments must be exact: fuzzy matching two or three
        # characters can otherwise select a completely different utterance.
        if len(key) < 6:
            return None
        choices = self._choices.get(channel)
        if choices is None:
            choices = [text for text, records in self.records.items() if any(allowed(r) for r in records)]
            self._choices[channel] = choices
        hits = process.extract(key, choices, scorer=fuzz.ratio,
                               score_cutoff=max(88, threshold), limit=2)
        if not hits or (len(hits) > 1 and hits[1][1] >= hits[0][1] - 2):
            return None
        matched, score, _ = hits[0]
        return [record for record in self.records[matched] if allowed(record)], float(score)
