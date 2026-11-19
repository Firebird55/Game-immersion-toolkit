"""Subtitle matching helpers shared by games with English and Mandarin text."""
from __future__ import annotations

import re
import unicodedata
from typing import Callable, Iterable

from rapidfuzz import fuzz, process
from opencc import OpenCC

from .textmaps import display_text, normalize_english

HAN_RE = re.compile(r"[\u3400-\u9fff\U00020000-\U0003134f]")
# Lookup receives both simplified official text and traditional OCR. tw2s
# reverses Taiwan-specific variants first, interpreting the already simplified
# particle 么 as the traditional variant of 幺. That makes 什么 and 什麼
# different keys. t2s accepts both scripts without rewriting genuine 幺.
_SIMPLIFIED = OpenCC("t2s")


def _single_character_conversion(converter):
    # The bundled t2s conversion has one stage with a phrase dictionary and
    # a character dictionary. Keep OpenCC's phrase precedence and separators.
    # An unfamiliar dictionary layout uses the normal converter for all text.
    stages = getattr(converter, "_dict_chain_data", ())
    if len(stages) != 1 or not isinstance(stages[0], list) or len(stages[0]) != 2:
        return None, None
    characters, phrases = {}, set()
    for _, _, dictionary in stages[0]:
        for key, value in dictionary.items():
            if len(key) != 1:
                phrases.add(key)
            elif not converter.split_chars_re.fullmatch(key):
                characters.setdefault(key, value.split(" ", 1)[0])
    pattern = re.compile("|".join(map(re.escape, sorted(phrases)))) if phrases else None
    return str.maketrans(characters), pattern


_T2S_CHARACTERS, _T2S_PHRASES = _single_character_conversion(_SIMPLIFIED)


def contains_han(value: str) -> bool:
    return bool(HAN_RE.search(value))


def simplify_chinese(value: str) -> str:
    if _T2S_CHARACTERS is not None and (_T2S_PHRASES is None or not _T2S_PHRASES.search(value)):
        return value.translate(_T2S_CHARACTERS)
    return _SIMPLIFIED.convert(value)


def normalize_chinese(value: str) -> str:
    # OCR spaces between ideographs and full-width punctuation are display
    # artifacts. Preserve Latin words/numbers that belong to Chinese dialogue.
    # Convert lookup keys only; retain the official transcript and raw OCR.
    value = simplify_chinese(unicodedata.normalize("NFKC", display_text(value)))
    return "".join(char for char in value.casefold()
                   if char.isalnum())


def normalize_subtitle(value: str) -> str:
    return normalize_chinese(value) if contains_han(value) else ''.join(
        char for char in unicodedata.normalize('NFKC', display_text(value)).casefold() if char.isalnum())


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
    # At some font sizes OCR isolates an ellipsis as its own row. It has no
    # language or lookup content; leaving it between two Hanzi rows prevents
    # those wrapped parts from being joined into the original subtitle.
    cleaned = [line for line in cleaned if normalize_subtitle(line)]
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
