from __future__ import annotations

import html
import json
import re
import threading
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from rapidfuzz import fuzz, process

from .models import TextMatch


TEXTMAP_URLS = {
    "en_base": "https://git.mero.moe/dimbreath/ZenlessData/raw/branch/master/TextMap/TextMap_ENTemplateTb.json",
    "zh_base": "https://git.mero.moe/dimbreath/ZenlessData/raw/branch/master/TextMap/TextMapTemplateTb.json",
    "en_overwrite": "https://git.mero.moe/dimbreath/ZenlessData/raw/branch/master/TextMap/TextMap_ENOverwriteTemplateTb.json",
    "zh_overwrite": "https://git.mero.moe/dimbreath/ZenlessData/raw/branch/master/TextMap/TextMapOverwriteTemplateTb.json",
}

TAG_RE = re.compile(r"<[^>]+>")
FORMAT_RE = re.compile(r"\{[^{}]*\}|\[[^\[\]]*\]")
NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
DIALOGUE_ID_MARKERS = ("chat", "galgame", "dialog", "talk", "voice")
TIP_ID_MARKERS = ("tips", "autoevent", "guide", "unlockdes", "toast")
CINEMATIC_ID_MARKERS = (
    "comic",
    "video",
    "voice",
    "subtitle",
    "caption",
)
GENDER_VARIANT_RE = re.compile(r"\{[MF]#(.*?)\}", re.DOTALL)
TERMINAL_PUNCTUATION_RE = re.compile(r"[.!?…][\"')\]}]*$")


def display_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\n", " ").replace("\r", " ").replace("\n", " ")
    text = TAG_RE.sub("", text)
    return " ".join(text.split()).strip()


def normalize_english(value: str) -> str:
    text = display_text(value).casefold()
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = FORMAT_RE.sub(" ", text)
    return NON_ALNUM_RE.sub("", text)


def localized_variants(value: str) -> list[str]:
    variants = [display_text(item) for item in GENDER_VARIANT_RE.findall(str(value or ""))]
    variants = [item for item in variants if item]
    return list(dict.fromkeys(variants)) or [display_text(value)]


@dataclass(frozen=True, slots=True)
class _Record:
    text_id: str
    english: str
    chinese: str


class TextMapIndex:
    def __init__(self, data_dir: Path, urls: dict[str, str] | None = None):
        self.data_dir = data_dir
        self.urls = urls or TEXTMAP_URLS
        self._lock = threading.RLock()
        self._records_by_normalized: dict[str, list[_Record]] = {}
        self._choices: list[str] = []
        self._blocked_labels: set[str] = set()
        self._cache: dict[tuple[str, int, bool, str], TextMatch | None] = {}
        self.ready = False
        self.state = "not_ready"
        self.message = "TextMaps have not been loaded"
        self.entry_count = 0

    def file_path(self, name: str) -> Path:
        return self.data_dir / f"{name}.json"

    def prepare(
        self,
        *,
        force_download: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        with self._lock:
            self.state = "downloading"
            self.message = "Checking bilingual TextMaps"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for name, url in self.urls.items():
            path = self.file_path(name)
            if force_download or not path.exists() or path.stat().st_size < 100:
                if progress:
                    progress(f"Downloading {name.replace('_', ' ')}")
                self._download(url, path)
        if progress:
            progress("Building English lookup index")
        self.load()

    @staticmethod
    def _download(url: str, destination: Path) -> None:
        partial = destination.with_suffix(".part")
        request = urllib.request.Request(url, headers={"User-Agent": "ProxyTranscript/0.1"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            partial.replace(destination)
        finally:
            if partial.exists():
                partial.unlink(missing_ok=True)

    def _read_map(self, name: str) -> dict[str, str]:
        with self.file_path(name).open("r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"{name} is not a JSON object")
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    def load(self) -> None:
        try:
            english = self._read_map("en_base")
            english.update(self._read_map("en_overwrite"))
            chinese = self._read_map("zh_base")
            chinese.update(self._read_map("zh_overwrite"))
            index: dict[str, list[_Record]] = {}
            blocked_labels: set[str] = set()
            for text_id, english_value in english.items():
                chinese_value = chinese.get(text_id)
                if not chinese_value:
                    continue
                english_variants = localized_variants(english_value)
                chinese_variants = localized_variants(chinese_value)
                # ZZZ repeats character names across thousands of TextMap keys.
                # Harvest those official label records up front so a name cannot
                # leak through via a second, less-obvious key with the same text.
                lowered_id = text_id.casefold()
                for variant_index, english_text in enumerate(english_variants):
                    chinese_text = chinese_variants[min(variant_index, len(chinese_variants) - 1)]
                    normalized = normalize_english(english_text)
                    if len(normalized) < 2 or not chinese_text:
                        continue
                    if "name" in lowered_id or "speaker" in lowered_id:
                        blocked_labels.add(normalized)
                    index.setdefault(normalized, []).append(
                        _Record(text_id=text_id, english=english_text, chinese=chinese_text)
                    )
            with self._lock:
                self._records_by_normalized = index
                self._choices = list(index)
                self._blocked_labels = blocked_labels
                self._cache.clear()
                self.entry_count = sum(len(records) for records in index.values())
                self.ready = True
                self.state = "ready"
                self.message = f"{self.entry_count:,} bilingual entries indexed"
        except Exception as error:
            with self._lock:
                self.ready = False
                self.state = "error"
                self.message = str(error)
            raise

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "ready": self.ready,
                "state": self.state,
                "message": self.message,
                "entry_count": self.entry_count,
            }

    def set_message(self, message: str) -> None:
        with self._lock:
            self.message = message

    @staticmethod
    def _looks_like_label(value: str) -> bool:
        words = value.split()
        return bool(words) and len(words) <= 4 and len(value) <= 48 and not TERMINAL_PUNCTUATION_RE.search(value)

    @classmethod
    def _candidate_strings(cls, lines: Iterable[str]) -> list[tuple[str, bool]]:
        cleaned = [display_text(line) for line in lines if display_text(line)]
        candidates: list[tuple[str, bool]] = []
        has_speaker_context = 2 <= len(cleaned) <= 3 and cls._looks_like_label(cleaned[0])

        def add(value: str, allow_short: bool = False) -> None:
            value = " ".join(value.split()).strip()
            candidate = (value, allow_short)
            if value and candidate not in candidates:
                candidates.append(candidate)

        add(" ".join(cleaned))
        if len(cleaned) > 1:
            add(" ".join(cleaned[1:]), has_speaker_context)
            add(" ".join(cleaned[:-1]))
        for index, line in enumerate(cleaned):
            add(line, has_speaker_context and index > 0)
        for start in range(len(cleaned)):
            for end in range(start + 2, min(len(cleaned), start + 3) + 1):
                add(" ".join(cleaned[start:end]), has_speaker_context and start > 0)
        return candidates

    def match_lines(
        self,
        lines: Iterable[str],
        threshold: float = 82,
        *,
        channel: str = "dialogue",
    ) -> TextMatch | None:
        source_lines = list(lines)
        crowded = len([line for line in source_lines if display_text(line)]) > 4
        matches: list[TextMatch] = []
        for candidate, allow_short in self._candidate_strings(source_lines):
            if crowded and len(display_text(candidate).split()) < 4:
                continue
            result = self.match_text(
                candidate,
                threshold=threshold,
                allow_short=allow_short,
                channel=channel,
            )
            if result is None:
                continue
            matches.append(result)
        if not matches:
            return None

        best = max(
            matches,
            key=lambda item: (item.score, len(normalize_english(item.source_ocr))),
        )
        best_text = normalize_english(best.english)
        # OCR often exposes the final subtitle row as a perfect short match while
        # the joined rows form the correct full sentence at a slightly lower fuzzy
        # score. Prefer that fuller official line when it contains the short match
        # and is still within a conservative score margin.
        fuller_matches = [
            item
            for item in matches
            if len(normalize_english(item.english)) >= len(best_text) + 8
            and best_text in normalize_english(item.english)
            and item.score >= best.score - 15
        ]
        if fuller_matches:
            best = max(
                fuller_matches,
                key=lambda item: (len(normalize_english(item.english)), item.score),
            )
        return best

    def match_line_groups(
        self,
        lines: Iterable[str],
        threshold: float = 88,
        *,
        channel: str = "cinematic",
    ) -> list[TextMatch]:
        """Return every distinct official line represented in cumulative screen text."""
        source_lines = list(lines)
        joined = normalize_english(" ".join(source_lines))
        by_id: dict[str, TextMatch] = {}
        for candidate, allow_short in self._candidate_strings(source_lines):
            result = self.match_text(
                candidate,
                threshold=threshold,
                allow_short=allow_short,
                channel=channel,
            )
            if result is None:
                continue
            previous = by_id.get(result.text_id)
            if previous is None or (result.score, len(normalize_english(result.source_ocr))) > (
                previous.score,
                len(normalize_english(previous.source_ocr)),
            ):
                by_id[result.text_id] = result

        def screen_position(item: TextMatch) -> tuple[int, int]:
            source = normalize_english(item.source_ocr)
            position = joined.find(source)
            return (position if position >= 0 else -1, len(source))

        return sorted(by_id.values(), key=screen_position)

    def match_text(
        self,
        source_ocr: str,
        threshold: float = 82,
        *,
        allow_short: bool = False,
        channel: str = "dialogue",
    ) -> TextMatch | None:
        if not self.ready:
            return None
        normalized = normalize_english(source_ocr)
        # One-to-three character matches are overwhelmingly speaker labels,
        # percentages, button hints, and other HUD fragments in ZZZ. Keeping
        # the live log quiet matters more than collecting isolated "Yes" lines.
        if len(normalized) < 4:
            return None
        with self._lock:
            if normalized in self._blocked_labels:
                return None
        words = display_text(source_ocr).split()
        if channel == "tip" and (len(words) < 4 or len(normalized) < 15):
            return None
        if (
            not allow_short
            and len(words) <= 2
            and len(normalized) < 20
            and not TERMINAL_PUNCTUATION_RE.search(display_text(source_ocr))
        ):
            return None
        cache_key = (normalized, round(threshold), allow_short, channel)
        with self._lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                return cached.model_copy(update={"source_ocr": source_ocr}) if cached else None
            records = self._records_by_normalized.get(normalized)
            kind = "exact"
            score = 100.0
            if records is None:
                if len(normalized) < 5:
                    self._cache[cache_key] = None
                    return None
                effective_threshold = max(threshold, 94) if len(normalized) < 10 else threshold
                fuzzy_match = process.extractOne(
                    normalized,
                    self._choices,
                    scorer=fuzz.ratio,
                    score_cutoff=effective_threshold,
                )
                if fuzzy_match is None:
                    self._cache[cache_key] = None
                    return None
                matched_normalized, score, _choice_index = fuzzy_match
                records = self._records_by_normalized[matched_normalized]
                kind = "fuzzy"

            records = [record for record in records if self._is_allowed_record(record, channel)]
            if not records:
                self._cache[cache_key] = None
                return None

            chinese_counts = Counter(record.chinese for record in records)
            selected_chinese, _ = chinese_counts.most_common(1)[0]
            selected = next(record for record in records if record.chinese == selected_chinese)
            result = TextMatch(
                text_id=selected.text_id,
                english=selected.english,
                chinese=selected.chinese,
                source_ocr=source_ocr,
                score=round(float(score), 1),
                kind=kind,
                ambiguous=len(chinese_counts) > 1,
            )
            self._cache[cache_key] = result
            if len(self._cache) > 4096:
                self._cache.pop(next(iter(self._cache)))
            return result

    @staticmethod
    def _is_dialogue_record(record: _Record) -> bool:
        text_id = record.text_id.casefold()
        if "name" in text_id or "speaker" in text_id:
            return False
        return any(marker in text_id for marker in DIALOGUE_ID_MARKERS)

    @classmethod
    def _is_allowed_record(cls, record: _Record, channel: str) -> bool:
        if channel == "tip":
            text_id = record.text_id.casefold()
            if "name" in text_id or "speaker" in text_id:
                return False
            return any(marker in text_id for marker in TIP_ID_MARKERS)
        if channel == "cinematic":
            text_id = record.text_id.casefold()
            if "name" in text_id or "speaker" in text_id:
                return False
            return any(marker in text_id for marker in CINEMATIC_ID_MARKERS)
        return cls._is_dialogue_record(record)
