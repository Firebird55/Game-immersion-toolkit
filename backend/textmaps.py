from __future__ import annotations

import html
import hashlib
import json
import re
import shutil
import tempfile
import threading
import urllib.request
import uuid
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
    # Centered narration inside comic scenes can use GalGame dialogue IDs.
    # CaptureService still requires a verified voice for every non-comic ID.
    "galgame",
)
GAMEPLAY_ID_MARKERS = ("ongoinglevel",)
UI_LABELS = {"talk", "outputvalue", "searchsupply", "next", "select", "confirm", "cancel"}
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
        self._prepare_lock = threading.Lock()
        self._records_by_normalized: dict[str, list[_Record]] = {}
        self._choices: list[str] = []
        self._cinematic_choices: list[str] = []
        self._gameplay_choices: list[str] = []
        self._blocked_labels: set[str] = set()
        self._chinese_lookup = None
        self._cache: dict[tuple[str, int, bool, str], TextMatch | None] = {}
        self.ready = False
        self.state = "not_ready"
        self.message = "TextMaps have not been loaded"
        self.entry_count = 0

    def file_path(self, name: str) -> Path:
        return self.active_directory() / f"{name}.json"

    def active_directory(self) -> Path:
        try:
            name = json.loads((self.data_dir / "current.json").read_text(encoding="utf-8"))["snapshot"]
            if isinstance(name, str) and re.fullmatch(r"[a-f0-9]{64}(?:-[a-f0-9]{8})?", name):
                directory = self.data_dir / "snapshots" / name
                if directory.resolve().is_relative_to(self.data_dir.resolve()) and all(
                    (directory / f"{key}.json").is_file() for key in self.urls
                ):
                    return directory
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return self.data_dir

    def prepare(
        self,
        *,
        force_download: bool = False,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        with self._prepare_lock:
            with self._lock:
                self.state = "downloading"
                self.message = "Checking bilingual TextMaps"
            self.data_dir.mkdir(parents=True, exist_ok=True)
            try:
                with tempfile.TemporaryDirectory(dir=self.data_dir, prefix="refresh-") as temporary:
                    staging = Path(temporary)
                    active = self.active_directory()
                    for name, url in self.urls.items():
                        source, target = active / f"{name}.json", staging / f"{name}.json"
                        if force_download or not source.exists() or source.stat().st_size < 100:
                            if progress:
                                progress(f"Downloading {name.replace('_', ' ')}")
                            self._download(url, target)
                        else:
                            shutil.copyfile(source, target)
                    if progress:
                        progress("Building English lookup index")
                    candidate = TextMapIndex(staging, self.urls)
                    candidate.load()
                    if not candidate.ready or not candidate.entry_count:
                        raise ValueError("Downloaded TextMaps have no valid bilingual dialogue; previous index kept")
                    digest = hashlib.sha256(b"".join((staging / f"{name}.json").read_bytes() for name in sorted(self.urls))).hexdigest()
                    destination = self.data_dir / "snapshots" / digest
                    if destination.exists() and not all((destination / f"{name}.json").is_file() and
                            (destination / f"{name}.json").read_bytes() == (staging / f"{name}.json").read_bytes() for name in self.urls):
                        destination = destination.with_name(digest + "-" + uuid.uuid4().hex[:8])
                    if not destination.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        staging.replace(destination)
                    marker = self.data_dir / "current.pending"
                    marker.write_text(json.dumps({"snapshot": destination.name}), encoding="utf-8")
                    marker.replace(self.data_dir / "current.json")
                    with self._lock:
                        for field in ("_records_by_normalized", "_choices", "_cinematic_choices", "_gameplay_choices",
                                      "_blocked_labels", "_chinese_lookup", "_cache", "entry_count", "ready", "state", "message"):
                            setattr(self, field, getattr(candidate, field))
            except Exception:
                with self._lock:
                    self.state = "ready" if self.ready else "error"
                    self.message = "Refresh failed; keeping the previous complete TextMaps" if self.ready else "TextMap setup needs attention"
                raise

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

    def _read_map(self, name: str, directory: Path | None = None) -> dict[str, str]:
        with ((directory or self.active_directory()) / f"{name}.json").open("r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError(f"{name} is not a JSON object")
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    def load(self, *, prepare_matching: bool = True) -> None:
        """Load the same bilingual snapshot; exports can omit unused OCR indexes."""
        try:
            directory = self.active_directory()
            english = self._read_map("en_base", directory)
            english.update(self._read_map("en_overwrite", directory))
            chinese = self._read_map("zh_base", directory)
            chinese.update(self._read_map("zh_overwrite", directory))
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
            chinese_lookup = None
            cinematic_choices, gameplay_choices = [], []
            # Prepare channel choices before publishing the snapshot. Large
            # indexes must neither consume the first subtitle's stability
            # window nor block status requests while the background loader runs.
            if prepare_matching:
                from .bilingual import ChineseLookup
                chinese_lookup = ChineseLookup(record for records in index.values() for record in records)
                for channel in ("dialogue", "tip", "cinematic", "gameplay"):
                    chinese_lookup._choices[channel] = [key for key, records in chinese_lookup.records.items()
                        if any(self._is_allowed_record(record, channel) for record in records)]
                cinematic_choices = [
                    normalized for normalized, records in index.items()
                    if len(normalized) >= 20
                    if any(self._is_allowed_record(record, "cinematic") for record in records)
                ]
                gameplay_choices = [
                    normalized for normalized, records in index.items()
                    if any(self._is_allowed_record(record, "gameplay") for record in records)
                ]
            with self._lock:
                self._chinese_lookup = chinese_lookup
                self._records_by_normalized = index
                self._choices = list(index)
                self._cinematic_choices = cinematic_choices
                self._gameplay_choices = gameplay_choices
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

    def resolve_display_name(self, candidates: Iterable[str]) -> tuple[str, str] | None:
        """Resolve a technical/OCR speaker label to an official bilingual name."""
        with self._lock:
            ranked: list[tuple[tuple[int, int, int, int], str, str]] = []
            for candidate_index, candidate in enumerate(candidates):
                normalized = normalize_english(candidate)
                if not normalized:
                    continue
                for record in self._records_by_normalized.get(normalized, []):
                    english = display_text(record.english).strip(" \"'.,!?…:;()[]{}")
                    chinese = display_text(record.chinese).strip(" \"'.,!?…:;()[]{}「」『』（）")
                    if not english or not chinese or len(english) > 48 or len(chinese) > 24:
                        continue
                    text_id = record.text_id.casefold()
                    name_hint = int("name" in text_id or "avatar" in text_id or "speaker" in text_id)
                    punctuation_free = int(english == record.english.strip() and chinese == record.chinese.strip())
                    exact_spelling = int(english.casefold() == candidate.casefold())
                    ranked.append(
                        ((-candidate_index, name_hint, exact_spelling, punctuation_free), english, chinese)
                    )
            if not ranked:
                return None
            _, english, chinese = max(ranked, key=lambda item: item[0])
            return english, chinese

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
        from .bilingual import contains_han, normalize_subtitle
        source_lines = list(lines)
        crowded = len([line for line in source_lines if display_text(line)]) > 4
        matches: list[TextMatch] = []
        for candidate, allow_short in self._candidate_strings(source_lines):
            if crowded and not contains_han(candidate) and len(display_text(candidate).split()) < 4:
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
            key=lambda item: (item.score, len(normalize_subtitle(item.source_ocr))),
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
        from .bilingual import normalize_subtitle
        source_lines = list(lines)
        joined = normalize_subtitle(" ".join(source_lines))
        by_id: dict[str, TextMatch] = {}
        candidates = self._candidate_strings(source_lines)
        # Comic speech bubbles frequently wrap over four or more OCR rows. They
        # can also scroll, leaving only a long prefix or middle section visible.
        # Wider contiguous windows give the cinematic matcher enough context to
        # recover the complete official TextMap line without ever storing the
        # clipped on-screen fragment itself.
        cleaned = [display_text(line) for line in source_lines if display_text(line)]
        for size in range(4, min(7, len(cleaned)) + 1):
            for start in range(0, len(cleaned) - size + 1):
                candidate = " ".join(cleaned[start : start + size])
                value = (candidate, False)
                if value not in candidates:
                    candidates.append(value)

        for candidate, allow_short in candidates:
            result = self.match_text(
                candidate,
                threshold=threshold,
                allow_short=allow_short,
                channel=channel,
            )
            if result is None:
                result = self._match_cinematic_fragment(candidate, threshold)
                if result is None:
                    continue
            previous = by_id.get(result.text_id)
            if previous is None or (result.score, len(normalize_subtitle(result.source_ocr))) > (
                previous.score,
                len(normalize_subtitle(previous.source_ocr)),
            ):
                by_id[result.text_id] = result

        def screen_position(item: TextMatch) -> tuple[int, int]:
            source = normalize_subtitle(item.source_ocr)
            position = joined.find(source)
            return (position if position >= 0 else -1, len(source))

        return sorted(by_id.values(), key=screen_position)

    def _match_cinematic_fragment(
        self,
        source_ocr: str,
        threshold: float,
    ) -> TextMatch | None:
        """Resolve a substantial clipped comic bubble to its full official line."""
        from .bilingual import contains_han, normalize_subtitle
        chinese = contains_han(source_ocr)
        normalized = normalize_subtitle(source_ocr)
        if len(normalized) < (14 if chinese else 28):
            return None
        with self._lock:
            # Prepared with the complete snapshot. Rebuilding these choices on
            # every Hanzi fragment can consume the next frame's stability
            # window, especially when several high-resolution regions overlap.
            choices = (self._chinese_lookup._choices.get("cinematic", [])
                       if chinese and self._chinese_lookup else self._cinematic_choices)
            if not choices:
                return None
            matches = process.extract(
                normalized,
                choices,
                scorer=fuzz.partial_ratio,
                score_cutoff=max(92, threshold),
                limit=2,
            )
            if not matches:
                return None
            matched_normalized, score, _choice_index = matches[0]
            # Require a meaningful share of the official sentence. This keeps a
            # generic phrase inside a very long line from becoming a false hit.
            coverage = min(len(normalized), len(matched_normalized)) / max(
                len(normalized), len(matched_normalized)
            )
            if coverage < 0.45:
                return None
            if len(matches) > 1 and matches[1][1] >= score - 1:
                return None
            records = [
                record
                for record in (self._chinese_lookup.records[matched_normalized]
                               if chinese else self._records_by_normalized[matched_normalized])
                if self._is_allowed_record(record, "cinematic")
            ]
            if not records:
                return None
            chinese_counts = Counter(record.chinese for record in records)
            selected_chinese, _ = chinese_counts.most_common(1)[0]
            selected = next(record for record in records if record.chinese == selected_chinese)
        return TextMatch(
            text_id=selected.text_id,
            english=selected.english,
            chinese=selected.chinese,
            source_ocr=source_ocr,
            score=round(float(score), 1),
            kind="fuzzy",
            ambiguous=len(chinese_counts) > 1,
        )

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
        from .bilingual import contains_han
        if contains_han(source_ocr):
            return self._match_chinese(source_ocr, threshold, channel)
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
                fuzzy_choices = (
                    self._cinematic_choices if channel == "cinematic"
                    else self._gameplay_choices if channel == "gameplay"
                    else self._choices
                )
                fuzzy_match = process.extractOne(
                    normalized,
                    fuzzy_choices,
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

    def _match_chinese(self, source: str, threshold: float, channel: str) -> TextMatch | None:
        from .bilingual import normalize_chinese
        with self._lock:
            if self._chinese_lookup is None:
                return None
            result = self._chinese_lookup.match(source, threshold,
                lambda record: self._is_allowed_record(record, channel), channel)
            if result is None:
                return None
            records, score = result
            # A name is sometimes repeated under a dialogue key too.
            if any(record.chinese == records[0].chinese
                   and ("name" in record.text_id.casefold() or "speaker" in record.text_id.casefold())
                   for record in self._chinese_lookup.records.get(
                       normalize_chinese(source), [])):
                return None
            record = records[0]
            return TextMatch(text_id=record.text_id, english=record.english, chinese=record.chinese,
                             source_ocr=source, score=round(score, 1),
                             kind="exact" if score == 100 else "fuzzy",
                             ambiguous=len({r.text_id for r in records}) > 1)

    @staticmethod
    def _is_dialogue_record(record: _Record) -> bool:
        text_id = record.text_id.casefold()
        if "name" in text_id or "speaker" in text_id:
            return False
        return any(marker in text_id for marker in DIALOGUE_ID_MARKERS)

    @classmethod
    def _is_allowed_record(cls, record: _Record, channel: str) -> bool:
        text_id = record.text_id.casefold()
        # TextMap "SubTitle" is a menu subheading, not evidence of spoken
        # subtitles. Newbie tips are unvoiced tutorial/inventory notices.
        if (
            normalize_english(record.english) in UI_LABELS
            or record.english.rstrip().endswith((":", "："))
            or text_id.startswith("tips_newbie_")
            or ("subtitle" in text_id and not any(
                marker in text_id for marker in CINEMATIC_ID_MARKERS
            ))
        ):
            return False
        if channel == "tip":
            text_id = record.text_id.casefold()
            if "name" in text_id or "speaker" in text_id:
                return False
            if FORMAT_RE.search(record.english):
                return False
            return any(marker in text_id for marker in TIP_ID_MARKERS)
        if channel == "cinematic":
            text_id = record.text_id.casefold()
            if "name" in text_id or "speaker" in text_id:
                return False
            return any(marker in text_id for marker in CINEMATIC_ID_MARKERS)
        if channel == "gameplay":
            if "name" in text_id or "speaker" in text_id:
                return False
            return any(marker in text_id for marker in GAMEPLAY_ID_MARKERS)
        return cls._is_dialogue_record(record)

    @classmethod
    def is_capture_text(cls, text_id: str, english: str, channel: str) -> bool:
        return cls._is_allowed_record(_Record(text_id, english, ""), channel)
