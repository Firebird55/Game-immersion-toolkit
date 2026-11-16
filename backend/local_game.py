"""Indexes of official subtitles and verified original voice references."""
from __future__ import annotations

import json
import re
import threading
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from .bilingual import ChineseLookup, contains_han, normalize_subtitle, subtitle_candidates
from .models import TextMatch
from .textmaps import display_text, normalize_english


def _english_key(value: str) -> str:
    # OCR renders compatibility glyphs such as superscript/full-width digits
    # as ordinary digits. Preserve their values instead of discarding them.
    return normalize_english(unicodedata.normalize('NFKC', value))


def dialogue_voice_status(audio, status=None):
    status = status or ('voiced' if audio else 'unknown')
    if status not in {'voiced', 'unvoiced', 'unavailable', 'unknown'}:
        raise ValueError('Invalid dialogue voice status')
    if bool(audio) != (status == 'voiced'):
        raise ValueError('Dialogue voice status does not agree with its audio binding')
    return status


def dialogue_audio_scope(audio, scope=None):
    if scope not in {None, 'line', 'context', 'paragraph'}:
        raise ValueError('Invalid original voice scope')
    # Older adapters already preserve complete-performance metadata. Honor it
    # consistently for every game, even before its index is rebuilt.
    return 'paragraph' if audio and audio.get('playback_scope') == 'full_track' else scope or 'line'


DEFAULT_CAPTURE_CHANNELS = frozenset(('dialogue', 'tip', 'cinematic', 'gameplay'))


def dialogue_capture_channels(channels=None):
    if channels is None:
        return DEFAULT_CAPTURE_CHANNELS
    if (not isinstance(channels, list)
            or any(not isinstance(channel, str) or channel not in DEFAULT_CAPTURE_CHANNELS for channel in channels)):
        raise ValueError('Invalid dialogue capture channels')
    return frozenset(channels)


def validate_original_recording_metadata(digest, speaker, status, scope):
    if speaker is not None and (not isinstance(speaker, str) or
            re.fullmatch(r'[A-Za-z0-9_.:-]{1,256}', speaker) is None):
        raise ValueError('Invalid original speaker identity')
    if digest is not None and (not isinstance(digest, str) or
            re.fullmatch(r'[0-9a-f]{64}', digest) is None or not speaker or status != 'voiced' or scope != 'line'):
        raise ValueError('Invalid original recording identity')


def original_recording_context(row):
    """Preserve every capture condition when two original exports share bytes."""
    digest, speaker = row.get('original_recording_sha256'), row.get('original_speaker_id')
    validate_original_recording_metadata(digest, speaker, row.get('voice_status'), row.get('audio_scope', 'line'))
    if digest is None:
        return None
    audio = row['audio']
    context = {name: value for name, value in row.items() if name not in {'text_id', 'audio'}}
    # These two authored presentations can expose the same original utterance.
    # All other source fields, including full translations, predecessor/member
    # identities, OCR anchors and scope, must still agree without normalization.
    if row.get('dialogue_kind') in {'conversation', 'operator_voice'}:
        context.pop('dialogue_kind', None)
    if (set(audio) == {'publisher', 'file_id', 'source', 'locale'}
            and isinstance(audio['publisher'], str) and audio['publisher'].startswith('endfield-')):
        context['audio_export'] = {'publisher': audio['publisher'], 'locale': audio['locale']}
    else:
        # Portable clips retain their actual content-addressed export identity.
        # Unknown audio options and different encodings are never discarded.
        context['audio_export'] = audio
    return json.dumps(context, sort_keys=True, separators=(',', ':'))


@dataclass(frozen=True)
class LocalDialogue:
    text_id: str
    english: str
    chinese: str
    audio: dict | None = None
    speaker_english: str | None = None
    speaker_chinese: str | None = None
    player_voice: str | None = None
    # Extra OCR anchors may identify a resource; display text stays scoped to
    # its authored page and whole recordings are explicitly marked below.
    ocr_english: list[str] | None = None
    ocr_chinese: list[str] | None = None
    source_locale: str | None = None
    source_text: str | None = None
    texts: dict[str, str] | None = None
    audio_locale: str | None = None
    audio_scope: str = 'line'
    channels: list[str] | None = None
    ocr_texts: dict[str, list[str]] | None = None
    member_text_ids: list[str] | None = None
    # Silence must be established by the authored dialogue format, never by
    # failure to locate a voice pack. Older snapshots without evidence remain
    # unknown until their adapter rebuilds them.
    voice_status: str | None = None
    dialogue_kind: str | None = None
    previous_text_id: str | None = None
    requires_previous: bool = False
    text_binding_unresolved: bool = False
    unresolved_text_locales: list[str] | None = None
    original_recording_sha256: str | None = None
    original_speaker_id: str | None = None
    # Only the adapter can establish that this is authored, displayed dialogue.
    # Generic localization/UI entries must never opt into text-only capture.
    text_capture_verified: bool = False

    def __post_init__(self):
        status = dialogue_voice_status(self.audio, self.voice_status)
        dialogue_capture_channels(self.channels)
        if type(self.text_capture_verified) is not bool:
            raise ValueError('Invalid authored text capture evidence')
        if type(self.text_binding_unresolved) is not bool or (
                self.unresolved_text_locales is not None and
                (not isinstance(self.unresolved_text_locales, list) or
                 any(not isinstance(locale, str) or not locale for locale in self.unresolved_text_locales))):
            raise ValueError('Invalid unresolved text binding metadata')
        if self.text_binding_unresolved and self.audio:
            raise ValueError('Unresolved study text cannot bind an original recording')
        object.__setattr__(self, 'audio_scope', dialogue_audio_scope(self.audio, self.audio_scope))
        validate_original_recording_metadata(self.original_recording_sha256, self.original_speaker_id,
                                            status, self.audio_scope)
        if self.requires_previous and not self.previous_text_id:
            raise ValueError('Conditional dialogue requires an authored predecessor')
        if self.dialogue_kind is not None and (not isinstance(self.dialogue_kind, str) or not self.dialogue_kind.strip()):
            raise ValueError('Invalid dialogue category')
        object.__setattr__(self, 'voice_status', status)


class LocalGameTextIndex:
    def __init__(self, game: str, data_dir: Path):
        self.game, self.path = game, data_dir / "textmap.json"
        self.ready = False
        self.state, self.message = "not_ready", "Waiting for official game-file index"
        self.entry_count = self.audio_count = 0
        self._lock = threading.RLock()
        self._records: dict[str, list[LocalDialogue]] = {}
        self._chinese = ChineseLookup([])
        self._chinese_anchors: dict[str, list[LocalDialogue]] = {}
        self.player_voice = "unconfigured"
        self.capture_unvoiced = False
        self._unvoiced_english, self._unvoiced_chinese = {}, {}
        self.voice_counts = dict.fromkeys(('voiced', 'unvoiced', 'unavailable', 'unknown'), 0)
        self._loaded_signature = None
        self.load()

    def load(self) -> bool:
        try:
            stat = self.path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if self.ready and self._loaded_signature == signature:
                return True
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = [LocalDialogue(**item) for item in payload["records"]]
            voiced = [record for record in records if record.audio and not record.requires_previous]
            unvoiced_english, unvoiced_chinese = {}, {}
            counts = dict.fromkeys(self.voice_counts, 0)
            for record in records:
                counts[record.voice_status] += 1
                if record.voice_status != 'unvoiced':
                    continue
                for value in [record.english, *(record.ocr_english or [])]:
                    if key := _english_key(value):
                        unvoiced_english.setdefault(key, []).append(record)
                for value in [record.chinese, *(record.ocr_chinese or [])]:
                    if key := normalize_subtitle(value):
                        unvoiced_chinese.setdefault(key, []).append(record)
            lookup: dict[str, list[LocalDialogue]] = {}
            chinese_anchors: dict[str, list[LocalDialogue]] = {}
            for record in voiced:
                for values in (record.ocr_english, record.ocr_chinese):
                    if values is not None and (not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values)):
                        raise ValueError('Invalid authored OCR page anchors')
                for english in dict.fromkeys([record.english, *(record.ocr_english or [])]):
                    lookup.setdefault(_english_key(english), []).append(record)
                for chinese in dict.fromkeys([record.chinese, *(record.ocr_chinese or [])]):
                    chinese_anchors.setdefault(normalize_subtitle(chinese), []).append(record)
            chinese = ChineseLookup(voiced)
            with self._lock:
                self._records, self._chinese = lookup, chinese
                self._chinese_anchors = chinese_anchors
                self._unvoiced_english, self._unvoiced_chinese = unvoiced_english, unvoiced_chinese
                self.voice_counts = counts
                self.entry_count, self.audio_count = len(records), len(voiced)
                capabilities = payload.get('capture_capabilities') or {}
                text_only = capabilities.get('voiced') is False and capabilities.get('unvoiced') is True
                self.ready, self.state = True, "ready" if voiced else "unvoiced_only" if text_only else "missing_voice"
                self._loaded_signature = signature
                self.message = payload.get("message") or f"{len(records):,} bilingual pairs; {len(voiced):,} Mandarin voices"
            return True
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.message = str(error) if self.path.exists() else "Waiting for official game-file index"
            return False

    def status(self) -> dict:
        with self._lock:
            return {"ready": self.ready, "state": self.state, "message": self.message,
                    "entry_count": self.entry_count, "audio_count": self.audio_count,
                    "unvoiced_count": self.voice_counts['unvoiced'], "voice_counts": dict(self.voice_counts)}

    def match_lines(self, lines, threshold: float = 88, exact_only: bool = False) -> TextMatch | None:
        matches = []
        with self._lock:
            for source in subtitle_candidates(lines):
                if self.capture_unvoiced:
                    key = normalize_subtitle(source) if contains_han(source) else _english_key(source)
                    lookup = self._unvoiced_chinese if contains_han(source) else self._unvoiced_english
                    silent = [r for r in lookup.get(key, []) if not r.player_voice or r.player_voice == self.player_voice]
                    if len(key) >= 3 and len({(r.english, r.chinese) for r in silent}) == 1:
                        record = silent[0]
                        matches.append(TextMatch(game=self.game, text_id=record.text_id,
                            english=display_text(record.english), chinese=display_text(record.chinese),
                            source_ocr=source, score=100., kind='exact', voice_status='unvoiced',
                            dialogue_kind=record.dialogue_kind, speaker_english=record.speaker_english,
                            speaker_chinese=record.speaker_chinese))
                score = 100.0
                if contains_han(source):
                    if exact_only:
                        exact_records = self._chinese_anchors.get(normalize_subtitle(source))
                        hit = (exact_records, 100.0) if exact_records else None
                    else:
                        exact_records = self._chinese_anchors.get(normalize_subtitle(source))
                        hit = (exact_records, 100.0) if exact_records else self._chinese.match(source, threshold)
                    if hit is None:
                        continue
                    records, score = hit
                else:
                    key = _english_key(source)
                    if len(key) < 3:
                        continue
                    records = self._records.get(key)
                    if not records:
                        if exact_only:
                            continue
                        if len(key) < 8:
                            continue
                        hits = process.extract(key, self._records.keys(), scorer=fuzz.ratio,
                                               score_cutoff=max(88, threshold), limit=2)
                        if not hits or (len(hits) > 1 and hits[1][1] >= hits[0][1] - 2):
                            continue
                        choice, score, _ = hits[0]
                        records = self._records[choice]
                records = [r for r in records if not r.player_voice or r.player_voice == self.player_voice]
                # A shared recording may cover several independently translated
                # pages. The voice alone cannot disambiguate those pages.
                voices = {('verified-original-export', original_recording_context(asdict(r)))
                          if self.game == 'endfield' and r.original_recording_sha256 else
                          (json.dumps(r.audio, sort_keys=True), r.english, r.chinese) for r in records}
                if len(voices) != 1:
                    continue
                record = records[0]
                matches.append(TextMatch(game=self.game, text_id=record.text_id,
                    english=display_text(record.english), chinese=display_text(record.chinese),
                    source_ocr=source, score=float(score), kind="exact" if score == 100 else "fuzzy",
                    speaker_english=record.speaker_english, speaker_chinese=record.speaker_chinese,
                    voice_status=record.voice_status, dialogue_kind=record.dialogue_kind,
                    audio_scope=record.audio_scope))
        if not matches:
            return None
        best = max(matches, key=lambda m: (m.score, len(normalize_subtitle(m.source_ocr))))
        equally_good = [m for m in matches if m.score == best.score
                        and len(normalize_subtitle(m.source_ocr)) == len(normalize_subtitle(best.source_ocr))]
        if len({m.text_id for m in equally_good}) > 1:
            return None
        return best

    def is_capture_text(self, text_id: str, english: str, _channel: str) -> bool:
        return text_id.startswith(self.game + ":") and bool(display_text(english))
