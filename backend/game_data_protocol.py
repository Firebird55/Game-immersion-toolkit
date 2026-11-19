"""Platform-independent contracts for publisher preparation and lazy original voice.

Providers are maintained code registered by the host, never downloaded scripts.
Planning permits bounded metadata only. Archive/bootstrap results are stages;
only a verified SnapshotSource may activate the production matcher.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Protocol

GAME_TITLES = {'zzz': 'Zenless Zone Zero', 'genshin': 'Genshin Impact', 'starrail': 'Honkai: Star Rail',
    'endfield': 'Arknights: Endfield', 'wuwa': 'Wuthering Waves', 'nte': 'Neverness to Everness',
    'reverse1999': 'Reverse: 1999', 'infinitynikki': 'Infinity Nikki'}
MAX_METADATA_BYTES = 8 * 1024**2
MAX_HANDLE_BYTES = 1024**2
MAX_ASSET_BYTES = 256 * 1024**3
MAX_SAFE_INTEGER = 2**53 - 1
LOCALE = re.compile(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}')
SHA256 = re.compile(r'[0-9a-f]{64}')
VOICE_GROUP = re.compile(r'starrail:copyright-avatar:([1-9][0-9]{0,9})')
VOICE_ALTERNATIVES = frozenset({'selected-dub', 'copyright-dub'})
REQUEST_REQUIRED = frozenset({'region', 'source_locale', 'target_locales', 'content_mode'})
REQUEST_FIELDS = REQUEST_REQUIRED | {'voice_choices'}


class GameDataError(Exception):
    def __init__(self, code, message, status=400):
        if (not isinstance(code, str) or re.fullmatch(r'[a-z0-9_]{1,96}', code) is None
                or not isinstance(message, str) or not message or len(message) > 1000
                or any(ord(char) < 32 or ord(char) == 127 for char in message)
                or type(status) is not int or not 400 <= status <= 599):
            code, message, status = 'game_data_error', 'Game data preparation did not complete.', 400
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def bounded_text(value, limit=512, *, empty=False):
    return (isinstance(value, str) and (empty or bool(value)) and len(value) <= limit
        and not any(ord(char) < 32 or ord(char) == 127 for char in value))


def private_handle(value):
    """Copy a bounded inert JSON handle; it is never included in public DTOs."""
    if not isinstance(value, dict):
        raise GameDataError('invalid_source_handle', 'The game source did not provide a restorable identity.')
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as error:
        raise GameDataError('invalid_source_handle', 'The game source did not provide a restorable identity.') from error
    if len(raw) > MAX_HANDLE_BYTES:
        raise GameDataError('source_handle_too_large', 'The game source identity exceeds its storage limit.')
    return json.loads(raw)


def _voice_group(key):
    match = VOICE_GROUP.fullmatch(key) if isinstance(key, str) else None
    return bool(match and int(match[1]) < 2**32)


@dataclass(frozen=True)
class VoiceChoiceSelection:
    """Only explicit user choices; no default or inferred selection."""
    choice_set_sha256: str
    choices: tuple[tuple[str, str], ...]

    def __post_init__(self):
        if (not isinstance(self.choice_set_sha256, str) or SHA256.fullmatch(self.choice_set_sha256) is None
                or not isinstance(self.choices, (tuple, list)) or not 0 < len(self.choices) <= 256
                or any(not isinstance(row, (tuple, list)) or len(row) != 2
                       or not _voice_group(row[0]) or not isinstance(row[1], str) or row[1] not in VOICE_ALTERNATIVES for row in self.choices)
                or len({row[0] for row in self.choices}) != len(self.choices)):
            raise GameDataError('invalid_voice_choices', 'Choose each original voice variant once from the current choices.')
        object.__setattr__(self, 'choices', tuple(sorted(tuple(row) for row in self.choices)))

    @classmethod
    def parse(cls, value):
        if value is None:
            return None
        if (not isinstance(value, dict) or set(value) != {'choice_set_sha256', 'choices'}
                or not isinstance(value['choice_set_sha256'], str) or SHA256.fullmatch(value['choice_set_sha256']) is None
                or not isinstance(value['choices'], list) or len(value['choices']) > 256
                or any(not isinstance(row, dict) or set(row) != {'group_key', 'alternative'} for row in value['choices'])):
            raise GameDataError('invalid_voice_choices', 'Choose original voices from the current game choices.')
        return cls(value['choice_set_sha256'], tuple((row['group_key'], row['alternative']) for row in value['choices'])) if value['choices'] else None

    def json(self):
        return {'choice_set_sha256': self.choice_set_sha256,
                'choices': [{'group_key': key, 'alternative': alternative} for key, alternative in self.choices]}


@dataclass(frozen=True)
class VoiceChoiceSet:
    """Public original-choice metadata, never proof of playable audio."""
    choice_set_sha256: str
    generation_sha256: str
    schema_sha256: str
    rows_sha256: str
    groups: tuple[tuple[str, int, str, str], ...]

    def __post_init__(self):
        if (any(not isinstance(value, str) or SHA256.fullmatch(value) is None for value in
                (self.choice_set_sha256, self.generation_sha256, self.schema_sha256, self.rows_sha256))
                or not isinstance(self.groups, (tuple, list)) or not 0 < len(self.groups) <= 256
                or any(not isinstance(row, (tuple, list)) or len(row) != 4 or not _voice_group(row[0])
                       or type(row[1]) is not int or row[0] != f'starrail:copyright-avatar:{row[1]}'
                       or not isinstance(row[2], str) or not isinstance(row[3], str)
                       or row[2] not in {'en', 'ja', 'ko', 'zh-Hans'} or row[3] not in {'en', 'ja', 'ko', 'zh-Hans'}
                       for row in self.groups)
                or len({row[0] for row in self.groups}) != len(self.groups)):
            raise GameDataError('invalid_voice_choice_metadata', 'The original voice choice metadata is unsupported.')
        object.__setattr__(self, 'groups', tuple(sorted(tuple(row) for row in self.groups)))

    def json(self):
        return {'choice_set_sha256': self.choice_set_sha256, 'generation_sha256': self.generation_sha256,
                'schema_sha256': self.schema_sha256, 'rows_sha256': self.rows_sha256,
                'groups': [{'group_key': key, 'owner': {'kind': 'avatar', 'id': owner},
                    'default_status': 'unknown', 'default_alternative': None,
                    'alternatives': [{'alternative': alternative, 'declared_spoken_locale': locale,
                                      'requires_authored_locale_receipt': True}
                                     for alternative, locale in (('selected-dub', selected), ('copyright-dub', copyright))]}
                           for key, owner, selected, copyright in self.groups]}


@dataclass(frozen=True)
class GameDataRequest:
    region: str
    source_locale: str
    target_locales: tuple[str, ...] = ()
    content_mode: str = 'text'
    voice_choices: VoiceChoiceSelection | None = None

    def __post_init__(self):
        if (self.region not in {'global', 'cn'} or self.content_mode not in {'text', 'text-audio'} or not isinstance(self.source_locale, str)
                or LOCALE.fullmatch(self.source_locale) is None or len(self.target_locales) > 128
                or any(not isinstance(value, str) or LOCALE.fullmatch(value) is None for value in self.target_locales)
                or len(set(self.target_locales)) != len(self.target_locales)):
            raise GameDataError('invalid_game_languages', 'Choose a valid region and game languages.')
        object.__setattr__(self, 'target_locales', tuple(sorted(self.target_locales)))
        if self.voice_choices is not None and not isinstance(self.voice_choices, VoiceChoiceSelection):
            raise GameDataError('invalid_voice_choices', 'Choose original voices from the current game choices.')

    @classmethod
    def parse(cls, value):
        if (not isinstance(value, dict) or not REQUEST_REQUIRED <= set(value) <= REQUEST_FIELDS
                or not isinstance(value.get('target_locales'), list)):
            raise GameDataError('invalid_game_languages', 'Choose a region and game languages before checking the download.')
        return cls(value['region'], value['source_locale'], tuple(value['target_locales']), value['content_mode'],
                   VoiceChoiceSelection.parse(value.get('voice_choices')))

    def json(self):
        return {'region': self.region, 'source_locale': self.source_locale, 'target_locales': list(self.target_locales), 'content_mode': self.content_mode,
                **({'voice_choices': self.voice_choices.json()} if self.voice_choices is not None else {})}


@dataclass(frozen=True)
class SourceProof:
    """Provider-verified receipt, including evidence for an exceptional key fallback.

    Both origins still require original publisher text, translations and audio.
    The registry verifies the receipt; this DTO never carries a key or schema.
    """
    origin: str
    receipt_sha256: str
    publisher_content_verified: bool
    official_unavailable_receipt_sha256: str | None = None

    def __post_init__(self):
        if (self.origin not in {'official', 'maintained-community-fallback'}
                or not isinstance(self.receipt_sha256, str) or SHA256.fullmatch(self.receipt_sha256) is None
                or self.publisher_content_verified is not True
                or self.origin == 'maintained-community-fallback' and
                    (not isinstance(self.official_unavailable_receipt_sha256, str)
                     or SHA256.fullmatch(self.official_unavailable_receipt_sha256) is None)
                or self.origin == 'official' and self.official_unavailable_receipt_sha256 is not None):
            raise GameDataError('unverified_source_origin', 'This game source has not completed original-data verification.')


@dataclass(frozen=True)
class GameDataPlan:
    revision: str
    download_bytes: int | None
    required_disk_bytes: int | None
    handle: dict = field(default_factory=dict)
    download_is_upper_bound: bool = False
    runtime_available: bool = False
    stage: str = 'content'
    message: str = ''
    source_proof: SourceProof | None = None
    available_voice_choices: VoiceChoiceSet | None = None
    reuse_installed: bool = False

    def __post_init__(self):
        if (not bounded_text(self.revision, 256) or not bounded_text(self.stage, 64)
                or not bounded_text(self.message, 1000, empty=True)
                or type(self.download_is_upper_bound) is not bool or type(self.runtime_available) is not bool
                or type(self.reuse_installed) is not bool
                or self.reuse_installed and (not self.runtime_available or self.download_bytes != 0 or self.required_disk_bytes != 0)
                or any(value is not None and (type(value) is not int or not 0 <= value <= MAX_ASSET_BYTES)
                       for value in (self.download_bytes, self.required_disk_bytes))):
            raise GameDataError('invalid_download_plan', 'The game source did not provide a bounded download plan.')
        object.__setattr__(self, 'handle', private_handle(self.handle))
        if self.available_voice_choices is not None and not isinstance(self.available_voice_choices, VoiceChoiceSet):
            raise GameDataError('invalid_voice_choice_metadata', 'The original voice choices are unsupported.')


class PreparationContext(Protocol):
    game: str
    directory: Path
    cache_directory: Path
    request: GameDataRequest
    phase: str
    transfer_lock: Any
    # Same-request previously consented bootstrap continuation, local only.
    stage_handle: dict | None
    stage_directory: Path | None

    def check(self) -> None: ...
    def cancelled(self) -> bool: ...
    def consume_bytes(self, count: int, *, kind: str = 'asset') -> None: ...
    def remaining_bytes(self, *, kind: str = 'asset') -> int: ...
    def progress(self, phase: str, downloaded_bytes: int, total_bytes: int | None, message: str = '') -> None: ...


class OriginalVoiceSource(Protocol):
    # has certifies a verified locally materialized original binding. Missing
    # decoded MP3/WAV is fine; a mere remote URL is insufficient for text+audio
    # readiness. No download/decoder/OCR work may run in this predicate.
    def has(self, row: Mapping[str, Any]) -> bool: ...
    # Decode locally materialized originals outside the confirmation lock.
    # Missing originals must fail; transfers belong to explicit download plans.
    def resolve(self, row: dict, destination: Path, *, cancelled: Callable[[], bool]) -> Path | None: ...


@dataclass(frozen=True)
class SnapshotSource:
    snapshot_path: Path
    restore_handle: dict
    source_proof: SourceProof
    voice_source: OriginalVoiceSource | None = None

    def __post_init__(self):
        if not isinstance(self.source_proof, SourceProof):
            raise GameDataError('unverified_snapshot_source', 'The game source has not completed original-data verification.')
        object.__setattr__(self, 'snapshot_path', Path(self.snapshot_path))
        object.__setattr__(self, 'restore_handle', private_handle(self.restore_handle))


@dataclass(frozen=True)
class PreparationStage:
    """A verified download stage needing another estimate, never a ready index."""
    restore_handle: dict
    message: str

    def __post_init__(self):
        if not bounded_text(self.message, 1000):
            raise GameDataError('invalid_preparation_stage', 'The game needs another download estimate.')
        object.__setattr__(self, 'restore_handle', private_handle(self.restore_handle))


class GameDataProvider(Protocol):
    title: str
    def plan(self, request: GameDataRequest, ctx: PreparationContext) -> GameDataPlan: ...
    def download(self, plan: GameDataPlan, ctx: PreparationContext) -> SnapshotSource | PreparationStage: ...
    # Restore and voice.resolve are local/offline. Downloads require a new plan.
    def restore(self, handle: dict, ctx: PreparationContext) -> SnapshotSource: ...
