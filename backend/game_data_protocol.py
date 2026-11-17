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


@dataclass(frozen=True)
class GameDataRequest:
    region: str
    source_locale: str
    target_locales: tuple[str, ...] = ()
    content_mode: str = 'text'

    def __post_init__(self):
        if (self.region not in {'global', 'cn'} or self.content_mode not in {'text', 'text-audio'} or not isinstance(self.source_locale, str)
                or LOCALE.fullmatch(self.source_locale) is None or len(self.target_locales) > 128
                or any(not isinstance(value, str) or LOCALE.fullmatch(value) is None for value in self.target_locales)
                or len(set(self.target_locales)) != len(self.target_locales)):
            raise GameDataError('invalid_game_languages', 'Choose a valid region and game languages.')
        object.__setattr__(self, 'target_locales', tuple(sorted(self.target_locales)))

    @classmethod
    def parse(cls, value):
        if (not isinstance(value, dict) or set(value) != {'region', 'source_locale', 'target_locales', 'content_mode'}
                or not isinstance(value.get('target_locales'), list)):
            raise GameDataError('invalid_game_languages', 'Choose a region and game languages before checking the download.')
        return cls(value['region'], value['source_locale'], tuple(value['target_locales']), value['content_mode'])

    def json(self):
        return {'region': self.region, 'source_locale': self.source_locale, 'target_locales': list(self.target_locales), 'content_mode': self.content_mode}


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

    def __post_init__(self):
        if (not bounded_text(self.revision, 256) or not bounded_text(self.stage, 64)
                or not bounded_text(self.message, 1000, empty=True)
                or type(self.download_is_upper_bound) is not bool or type(self.runtime_available) is not bool
                or any(value is not None and (type(value) is not int or not 0 <= value <= MAX_ASSET_BYTES)
                       for value in (self.download_bytes, self.required_disk_bytes))):
            raise GameDataError('invalid_download_plan', 'The game source did not provide a bounded download plan.')
        object.__setattr__(self, 'handle', private_handle(self.handle))


class PreparationContext(Protocol):
    game: str
    directory: Path
    cache_directory: Path
    request: GameDataRequest
    phase: str
    transfer_lock: Any

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
