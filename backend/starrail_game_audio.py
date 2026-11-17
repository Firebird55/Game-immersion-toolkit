"""Context-owned Star Rail original audio ranges and offline voice delivery.

An AudioV MD5 identifies the complete publisher owner; a partial HTTPS range
does not verify that MD5. Actual strong response ETags pin subsequent ranges.
Only locally checked original members can enter the no-I/O has predicate.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
import wave

from .game_data_protocol import GameDataError, MAX_ASSET_BYTES
from .private_data_paths import _no_links
from .private_data_paths import MAX_ROWS
from .publisher_transport import STRONG_ETAG

MAX_SPAN = 64 * 1024**2
MAX_HEADER = 32 * 1024**2
RECEIPT_LIMIT = 4096
RANGE_SCHEMA = 'starrail-original-audio-range-v1'


def _fail(message='The original Star Rail audio inventory changed. Check its size again.'):
    raise GameDataError('starrail_audio_changed', message, 409)


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@dataclass(frozen=True)
class Owner:
    name: str
    size: int
    md5: str
    url: str
    generation: str

    def __post_init__(self):
        if (not isinstance(self.name, str) or len(self.name) > 1024 or re.fullmatch(r'(?:[A-Za-z0-9_().-]+/)*[A-Za-z0-9_().-]+\.pck', self.name) is None
                or any(part in {'.', '..'} for part in self.name.split('/'))
                or type(self.size) is not int or not 28 < self.size <= MAX_ASSET_BYTES
                or not isinstance(self.md5, str) or re.fullmatch('[0-9a-f]{32}', self.md5) is None
                or not isinstance(self.url, str) or not self.url.startswith('https://')
                or not isinstance(self.generation, str) or re.fullmatch('[0-9a-f]{64}', self.generation) is None):
            _fail()

    def json(self):
        return {'name': self.name, 'bytes': self.size, 'md5': self.md5,
                'url_sha256': hashlib.sha256(self.url.encode()).hexdigest(), 'generation': self.generation}


@dataclass(frozen=True)
class Span:
    owner: Owner
    start: int
    length: int

    def __post_init__(self):
        if (not isinstance(self.owner, Owner) or type(self.start) is not int or type(self.length) is not int
                or not 0 < self.length <= MAX_SPAN or not 0 <= self.start <= self.owner.size - self.length):
            _fail()

    def json(self):
        return {'owner': self.owner.json(), 'start': self.start, 'bytes': self.length}


def owners(build, raw, locale):
    """Select only this dub plus neutral event-bank owners from exact AudioV."""
    from . import starrail_hotfix as hotfix
    from .hoyo_dialogue import voice_namespace
    language = voice_namespace('starrail', locale)
    _, digest, size = build['hotfix']['indexes']['audio']
    if len(raw) != size or hashlib.md5(raw).hexdigest() != digest:
        _fail()
    generation = identity({'build': build, 'audio_md5': digest})
    roots = hotfix.audio_roots(build)
    found = {}
    for line in raw.splitlines():
        try:
            row = json.loads(line); name = row['Path']
            if not isinstance(name, str):
                _fail()
            if not (name.startswith(language + '/') and name.endswith('.pck')
                    or re.fullmatch(r'Banks[0-9]+\.pck', name)):
                continue
            if name in found or type(row['Patch']) is not bool:
                _fail()
            asset = hotfix.audio_file(roots, name, row['Patch'], name, row['Size'], row['Md5'])
            found[name] = Owner(name, asset.size, asset.digest, asset.url, generation)
        except (KeyError, TypeError, ValueError) as error:
            raise GameDataError('starrail_audio_index_changed', 'The original Star Rail audio index is unsupported.') from error
    if not any(name.startswith(language + '/') for name in found):
        _fail('The selected official Star Rail dub inventory is unavailable.')
    return tuple(found[name] for name in sorted(found))


class RangeStore:
    """Owned cache, checked at use; no hidden request on a cache miss."""
    def __init__(self, directory):
        self.directory = Path(directory)
        _no_links(self.directory)

    def _directory(self, owner):
        path = self.directory / owner.generation / identity(owner.json())
        _no_links(path)
        return path

    def _path(self, span):
        path = self._directory(span.owner) / f'{span.start}-{span.length}'
        _no_links(path)
        return path

    def _owner(self, owner):
        path = self._directory(owner) / 'owner.json'; _no_links(path)
        try:
            if not path.is_file() or not 0 < path.stat().st_size <= RECEIPT_LIMIT:
                return None
            value = json.loads(path.read_bytes())
            if (not isinstance(value, dict) or set(value) != {'owner', 'response_etag'}
                    or value['owner'] != owner.json() or not isinstance(value['response_etag'], str)
                    or STRONG_ETAG.fullmatch(value['response_etag']) is None):
                return None
            return value
        except (OSError, ValueError):
            return None

    def receipt(self, span):
        path = self._path(span); receipt = path.with_name(path.name + '.json'); _no_links(receipt)
        try:
            owner = self._owner(span.owner)
            if (owner is None or not path.is_file() or path.stat().st_size != span.length
                    or not receipt.is_file() or not 0 < receipt.stat().st_size <= RECEIPT_LIMIT):
                return None
            value = json.loads(receipt.read_bytes())
            if (not isinstance(value, dict) or set(value) != {'schema', 'span', 'sha256', 'response_etag', 'verification'}
                    or value['schema'] != RANGE_SCHEMA or value['span'] != span.json()
                    or value['response_etag'] != owner['response_etag']
                    or value['verification'] != 'publisher-owned-https-range'
                    or not isinstance(value['sha256'], str) or re.fullmatch('[0-9a-f]{64}', value['sha256']) is None
                    or _hash(path) != value['sha256']):
                return None
            return value
        except (OSError, ValueError):
            return None

    def read(self, span):
        if self.receipt(span) is None:
            _fail('The required original Star Rail audio range is not verified locally.')
        path = self._path(span)
        raw = path.read_bytes()
        # Recheck the actual bytes supplied to the parser/decoder, after the
        # receipt validation, instead of trusting a stat or a previous process.
        value = json.loads(path.with_name(path.name + '.json').read_bytes())
        if len(raw) != span.length or hashlib.sha256(raw).hexdigest() != value['sha256']:
            _fail()
        return raw

    def acquire(self, span, transport):
        if self.receipt(span) is not None:
            return
        owner = self._owner(span.owner)
        if owner is None and (span.start, span.length) != (0, 28):
            _fail('The original Star Rail audio object has no established strong server identity.')
        path = self._path(span); path.parent.mkdir(parents=True, exist_ok=True)
        headers = {'If-Match': owner['response_etag']} if owner else None
        receipt = transport.download_to(span.owner.url, path, limit=span.length, kind='audio',
            expected_size=span.length, original_range=(span.start, span.length, span.owner.size), headers=headers)
        # Learning a tag is allowed only from the exact original prefix. An
        # orphaned bank/member cannot silently start another server generation.
        if receipt.response_etag is None:
            path.unlink(missing_ok=True)
            _fail('The original Star Rail audio object has no established strong server identity.')
        value = {'schema': RANGE_SCHEMA, 'span': span.json(), 'sha256': receipt.sha256,
                 'response_etag': receipt.response_etag, 'verification': 'publisher-owned-https-range'}
        self._write(path.with_name(path.name + '.json'), value)
        if owner is None:
            self._write(path.parent / 'owner.json', {'owner': span.owner.json(), 'response_etag': receipt.response_etag})

    @staticmethod
    def _write(path, value):
        from .game_tools import _atomic_file
        _no_links(path)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        if len(raw) > RECEIPT_LIMIT:
            _fail()
        _atomic_file(path, raw)


@dataclass(frozen=True)
class Quote:
    phase: str
    spans: tuple[Span, ...]

    @property
    def download_bytes(self):
        return sum(span.length for span in self.spans)

    @property
    def disk_bytes(self):
        return self.download_bytes + (len(self.spans) * 2 + 1) * RECEIPT_LIMIT

    @property
    def digest(self):
        return identity({'phase': self.phase, 'spans': [span.json() for span in self.spans]})


def header_quote(selected, store):
    """First quote exact 28-byte prefixes; only those reveal full header sizes."""
    prefixes = tuple(Span(owner, 0, 28) for owner in selected)
    if missing := tuple(span for span in prefixes if store.receipt(span) is None):
        return Quote('audio-inventory-prefixes', missing)
    headers = []
    for prefix in prefixes:
        raw = store.read(prefix)
        total, version, langs, banks, sounds, external = struct.unpack_from('<6I', raw, 4)
        if (raw[:4] != b'AKPK' or version != 1 or 20 + langs + banks + sounds + external != total
                or not 28 < total + 8 <= min(prefix.owner.size, MAX_HEADER)):
            _fail('The original Star Rail PCK header is unsupported or out of bounds.')
        headers.append(Span(prefix.owner, 28, total + 8 - 28))
    return Quote('audio-inventory-headers', tuple(span for span in headers if store.receipt(span) is None))


@dataclass(frozen=True)
class Directory:
    owner: Owner
    external: dict
    banks: dict
    sounds: dict


def directories(selected, store, locale):
    """Parse complete owned directories, never a bank/member payload."""
    from . import starrail_events as events
    from .hoyo_dialogue import voice_namespace
    from .voice_assets import external_table
    language = voice_namespace('starrail', locale)
    result, records = [], 0
    if header_quote(selected, store).spans:
        _fail('The original Star Rail audio directories are incomplete.')
    for owner in selected:
        prefix = store.read(Span(owner, 0, 28))
        total, _, langs, banks, sounds, external = struct.unpack_from('<6I', prefix, 4)
        raw = prefix + store.read(Span(owner, 28, total + 8 - 28))
        for start, length in ((28 + langs, banks), (28 + langs + banks, sounds),
                              (28 + langs + banks + sounds, external)):
            if length < 4 or start > len(raw) - length:
                _fail('The original PCK directory section leaves its header.')
            records += struct.unpack_from('<I', raw, start)[0]
            if records > MAX_ROWS:
                _fail('The original audio directory exceeds its record limit.')
        class Header:
            size = owner.size
            name = owner.name
            digest = owner.md5
            def read(self, directory, start, length):
                if type(start) is not int or type(length) is not int or not 0 < length <= len(raw) or not 0 <= start <= len(raw)-length:
                    _fail('An audio inventory parser requested payload outside the declared header.')
                return raw[start:start+length]
        asset = Header()
        try:
            bank_rows, sound_rows = events._pck(None, asset, 'sfx' if re.fullmatch(r'Banks[0-9]+\.pck', owner.name) else language)
            bank_rows = {key: Span(owner, row.offset, row.size) for key, row in bank_rows.items()}
            sound_rows = {key: Span(owner, row.offset, row.size) for key, row in sound_rows.items()}
            external_rows = {}
            for row in external_table(owner.name, owner.size, lambda start, length: asset.read(None, start, length)):
                if row.offset < len(raw):
                    _fail('The original external recording overlaps its PCK header.')
                if row.file_id in external_rows:
                    _fail('The original audio directory repeats an external member identity.')
                external_rows[row.file_id] = Span(owner, row.offset, row.size)
        except (ValueError, struct.error, UnicodeError) as error:
            raise GameDataError('starrail_audio_directory_changed', 'The original audio directory is malformed or unsupported.') from error
        result.append(Directory(owner, external_rows, bank_rows, sound_rows))
    return tuple(result)


def external_members(inventory, sources, locale):
    """Bind exact authored source hashes; conflicting owners stay unresolved."""
    from .hoyo_dialogue import voice_namespace
    from .voice_assets import voice_hash
    language = voice_namespace('starrail', locale)
    by_hash = {}
    for directory in inventory:
        if not directory.owner.name.startswith(language + '/'):
            continue
        for key, span in directory.external.items():
            by_hash[key] = span if key not in by_hash else None
    result = {}
    for source in set(sources):
        if (not isinstance(source, str) or not 0 < len(source) <= 4096 or '\x00' in source
                or re.split(r'[/\\]', source, maxsplit=1)[0].casefold() != language.casefold()):
            _fail('The authored original voice binding belongs to another dub.')
        if span := by_hash.get(voice_hash(source)):
            result[source] = span
    return result


@dataclass(frozen=True)
class OriginalMember:
    text_id: str
    audio: dict
    span: Span


def _riff(raw):
    if (len(raw) < 12 or raw[:4] != b'RIFF' or raw[8:12] != b'WAVE'
            or struct.unpack_from('<I', raw, 4)[0] + 8 != len(raw)):
        _fail('The original Star Rail recording is incomplete.')


class OriginalVoices:
    """Frozen checked membership; has performs neither I/O nor decoding."""
    def __init__(self, store, members, *, decoder=None, encoder=None):
        from .media_tools import vgmstream_executable, ffmpeg_executable
        self.store = store
        self.decoder = Path(decoder) if decoder is not None else vgmstream_executable()
        self.encoder = Path(encoder) if encoder is not None else ffmpeg_executable()
        self.members = {}
        for member in members:
            if (not isinstance(member, OriginalMember) or not isinstance(member.text_id, str)
                    or not member.text_id or not isinstance(member.audio, dict) or not member.audio
                    or member.audio.get('movie') or member.text_id in self.members):
                _fail()
            frozen = json.loads(json.dumps(member.audio, allow_nan=False))
            raw = store.read(member.span); _riff(raw)
            self.members[member.text_id] = (identity(frozen), OriginalMember(member.text_id, frozen, member.span), hashlib.sha256(raw).hexdigest())

    def has(self, row):
        if (not isinstance(row, Mapping) or not isinstance(row.get('text_id'), str)
                or row.get('voice_status') != 'voiced' or not isinstance(row.get('audio'), dict)):
            return False
        found = self.members.get(row.get('text_id'))
        if found is None:
            return False
        try:
            return found[0] == identity(row['audio'])
        except (TypeError, ValueError, RecursionError):
            return False

    @staticmethod
    def _check(cancelled):
        if cancelled():
            raise GameDataError('game_data_cancelled', 'Original voice preparation was cancelled.', 409)

    @classmethod
    def _run(cls, command, cancelled):
        cls._check(cancelled)
        options = {'stdin': subprocess.DEVNULL, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL,
                   'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}
        with subprocess.Popen(command, **options) as process:
            deadline = time.monotonic() + 90
            try:
                while process.poll() is None:
                    cls._check(cancelled)
                    if time.monotonic() >= deadline:
                        _fail('The original voice decoder exceeded its time limit.')
                    try:
                        process.wait(timeout=.1)
                    except subprocess.TimeoutExpired:
                        pass
                if process.returncode != 0:
                    _fail('The original voice could not be decoded locally.')
            finally:
                if process.poll() is None:
                    process.kill(); process.wait()
        cls._check(cancelled)

    def resolve(self, row, destination, *, cancelled):
        self._check(cancelled)
        if not self.has(row):
            return None
        destination = Path(destination); _no_links(destination)
        if destination.suffix.lower() not in {'.wav', '.mp3'}:
            _fail('The original voice destination must be WAV or MP3.')
        if self.decoder is None or not Path(self.decoder).is_file() or self.encoder is None or not Path(self.encoder).is_file():
            _fail('The delivered original voice codecs are unavailable on this device.')
        _, member, expected = self.members[row['text_id']]
        raw = self.store.read(member.span); _riff(raw); self._check(cancelled)
        if hashlib.sha256(raw).hexdigest() != expected:
            _fail('The materialized original Star Rail recording changed.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='starrail-original-', dir=destination.parent) as value:
            scratch = Path(value); source, decoded = scratch / 'source.wem', scratch / 'decoded.wav'
            source.write_bytes(raw); del raw
            self._run([str(self.decoder), '-i', '-o', str(decoded), str(source)], cancelled)
            with wave.open(str(decoded)) as stream:
                if (stream.getcomptype() != 'NONE' or not 1 <= stream.getnchannels() <= 8
                        or not 8000 <= stream.getframerate() <= 192000 or stream.getnframes() <= 0
                        or stream.getnframes() > stream.getframerate() * 3600):
                    _fail('The original voice decoded to an empty or unsupported recording.')
            from .local_voice import _audio_options
            options = _audio_options(member.audio, decoded)
            output = scratch / ('output' + destination.suffix.lower())
            codec = ['-codec:a', 'libmp3lame', '-q:a', '2'] if output.suffix == '.mp3' else ['-codec:a', 'pcm_s16le']
            self._run([str(self.encoder), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                '-i', str(decoded), *options, *codec, str(output)], cancelled)
            if not output.is_file() or output.stat().st_size <= 44:
                _fail('The original voice decoded to an empty recording.')
            self._check(cancelled)
            # Tampered/deleted originals cannot publish a stale decoded result.
            if hashlib.sha256(self.store.read(member.span)).hexdigest() != expected:
                _fail('The materialized original Star Rail recording changed.')
            self._check(cancelled); _no_links(destination); os.replace(output, destination)
        return destination
