"""Portable private libraries for the shared desktop/Android Python core.

Only prepared text and already decoded audio cross this boundary. Original game
archives, account credentials and executable code are never imported or run.
"""
from __future__ import annotations

from contextlib import nullcontext
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import zipfile

from .local_game import LocalDialogue
from .languages import audio_locale
from .multilingual_index import MultilingualTextIndex

FORMAT = 'toolkit-prepared-library-v1'
MAX_LIBRARY = 64 * 1024**3
MAX_TEXT = 512 * 1024**2
MAX_MANIFEST = 256 * 1024**2
MAX_AUDIO = 128 * 1024**2
# Current publisher snapshots already exceed 250k entries. Leave bounded
# headroom for player branches and ordinary updates without changing the app.
MAX_ROWS = 1000000
SHA = re.compile(r'[0-9a-f]{64}')
CLIP = re.compile(r'audio/([0-9a-f]{64})\.(mp3|wav)')


def _json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate library field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def _no_links(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('A private library cannot follow filesystem links')


def _safe_entries(archive, total_limit):
    result, total, names = {}, 0, set()
    if len(archive.infolist()) > MAX_ROWS + 64:
        raise ValueError('Library has too many files')
    for item in archive.infolist():
        name = item.filename
        path = PurePosixPath(name)
        if (item.is_dir() or item.orig_filename != name or not path.parts or path.is_absolute() or path.as_posix() != name
                or any(part in {'', '.', '..'} for part in name.split('/')) or '\\' in name
                or ':' in name or '\0' in name or name.casefold() in names or item.flag_bits & 1
                or item.compress_type != zipfile.ZIP_STORED or stat.S_ISLNK(item.external_attr >> 16)):
            raise ValueError('Unsafe library member')
        total += item.file_size
        if total > total_limit or item.file_size < 0:
            raise ValueError('Library exceeds its storage limit')
        names.add(name.casefold()); result[name] = item
    return result, total


def _snapshot(raw, audio):
    if len(raw) > MAX_TEXT:
        raise ValueError('Prepared text is too large')
    value = _json(raw)
    if 'publisher_world_dialogue_ui' in value:
        from .endfield_presentation import validate_world_dialogue_ui
        if value.get('game') != 'endfield':
            raise ValueError('World dialogue metadata belongs to its original game')
        value['publisher_world_dialogue_ui'] = validate_world_dialogue_ui(value['publisher_world_dialogue_ui'])
    if 'publisher_sns_dialogue_ui' in value:
        from .endfield_sns_presentation import validate_sns_dialogue_ui
        if value.get('game') != 'endfield':
            raise ValueError('Baker dialogue metadata belongs to its original game')
        value['publisher_sns_dialogue_ui'] = validate_sns_dialogue_ui(value['publisher_sns_dialogue_ui'])
        if value['publisher_sns_dialogue_ui']['revision'] != value.get('fingerprint'):
            raise ValueError('Original Baker UI and prepared records have different revisions')
    if (value.get('format') != 2 or not isinstance(value.get('game'), str)
            or not isinstance(value.get('source_locale'), str)
            or not isinstance(value.get('records'), list) or not 0 < len(value['records']) <= MAX_ROWS
            or value.get('install') is not None):
        raise ValueError('Incomplete prepared library')
    allowed = {field.name for field in fields(LocalDialogue)}
    identities = set()
    for row in value['records']:
        if not isinstance(row, dict) or set(row) - allowed:
            raise ValueError('Unsupported prepared dialogue fields')
        record = LocalDialogue(**row)
        # Keep full authored context/branch identity without retaining a second
        # serialized copy of every translation in the validation set.
        identity = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).digest()
        if (identity in identities or record.source_locale != value['source_locale']
                or record.source_text != (record.texts or {}).get(value['source_locale'])
                or record.audio_locale != audio_locale(value['source_locale'], value['game'])):
            raise ValueError('Duplicate or cross-language library row')
        identities.add(identity)
        if record.audio:
            if set(record.audio) != {'prepared_clip', 'locale'} or record.audio.get('locale') != record.audio_locale:
                raise ValueError('Library contains an unprepared original voice reference')
            name = record.audio['prepared_clip']
            if name not in audio or not CLIP.fullmatch(name):
                raise ValueError('Prepared original voice is missing')
    return value


class PreparedLibraryStore:
    def __init__(self, root):
        self.root = Path(root).absolute()
        _no_links(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.pointer = self.root / 'current.json'

    def current(self):
        if not self.pointer.is_file():
            return None
        _no_links(self.pointer)
        pointer = _json(self.pointer.read_bytes())
        revision = pointer.get('revision', '')
        if not SHA.fullmatch(revision):
            raise ValueError('Invalid private library generation')
        directory = self.root / revision
        _no_links(directory)
        text = directory / 'textmap.json'
        if text.stat().st_size > MAX_TEXT:
            raise ValueError('Prepared library text exceeds its bound')
        with text.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != pointer.get('text_sha256'):
            raise ValueError('Prepared library text changed')
        return directory

    def import_archive(self, path, *, cancelled=lambda: False, publish_guard=nullcontext, activate=lambda _directory, _index: None):
        path = Path(path)
        if path.stat().st_size > MAX_LIBRARY:
            raise ValueError('Library exceeds its storage limit')
        with zipfile.ZipFile(path) as archive:
            entries, total = _safe_entries(archive, MAX_LIBRARY)
            if entries.get('manifest.json') is None or entries['manifest.json'].file_size > MAX_MANIFEST:
                raise ValueError('Library manifest is missing or oversized')
            manifest = _json(archive.read('manifest.json'))
            if manifest.get('format') != FORMAT:
                raise ValueError('Import a prepared toolkit library; older browser libraries must be exported again')
            files = manifest.get('files')
            if (not isinstance(files, dict) or set(files) != set(entries) - {'manifest.json'}
                    or 'textmap.json' not in files or any(name != 'textmap.json' and not CLIP.fullmatch(name) for name in files)):
                raise ValueError('Unexpected prepared library contents')
            if total + 16 * 1024**2 > shutil.disk_usage(self.root).free:
                raise ValueError('Not enough free storage to prepare this library')
            revision = hashlib.sha256(archive.read('manifest.json')).hexdigest()
            with tempfile.TemporaryDirectory(prefix='library-', dir=self.root) as temporary:
                stage = Path(temporary)
                for name, expected in files.items():
                    if (not isinstance(expected, dict) or set(expected) != {'sha256', 'size'}
                            or not SHA.fullmatch(str(expected['sha256'])) or type(expected['size']) is not int
                            or expected['size'] != entries[name].file_size
                            or expected['size'] > (MAX_TEXT if name == 'textmap.json' else MAX_AUDIO)):
                        raise ValueError('Invalid prepared file checksum or size')
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    with archive.open(name) as source, target.open('xb') as destination:
                        while block := source.read(1024 * 1024):
                            if cancelled():
                                raise InterruptedError('Library import cancelled')
                            digest.update(block); destination.write(block)
                    if digest.hexdigest() != expected['sha256']:
                        raise ValueError('A prepared library file is corrupt')
                raw = (stage / 'textmap.json').read_bytes()
                payload = _snapshot(raw, files)
                game, rows = payload['game'], len(payload['records'])
                text_digest = hashlib.sha256(raw).hexdigest()
                # Validation and production indexing need not keep two complete
                # decoded publisher tables (plus raw bytes) alive together.
                del payload, raw
                index = MultilingualTextIndex(game, stage)
                if not index.ready or index.entry_count != rows:
                    raise ValueError('The shared matcher rejected the prepared library')
                if cancelled():
                    raise InterruptedError('Library import cancelled')
                with publish_guard() as mark_committed:
                    if cancelled():
                        raise InterruptedError('Library import cancelled')
                    complete = self.root / revision
                    if complete.exists():
                        # A receipt alone is not authority for reusing a prior import.
                        for name, expected in files.items():
                            _no_links(complete / name)
                            with (complete / name).open('rb') as source:
                                if hashlib.file_digest(source, 'sha256').hexdigest() != expected['sha256']:
                                    raise ValueError('The existing library generation is corrupt')
                    else:
                        stage.rename(complete)
                    pointer = {'revision': revision, 'text_sha256': text_digest}
                    pending = self.pointer.with_suffix('.pending')
                    pending.write_text(json.dumps(pointer), encoding='utf8')
                    pending.replace(self.pointer)
                    if mark_committed:
                        mark_committed()
                    index.path = complete / 'textmap.json'
                    activate(complete, index)
        return self.current()


def write_prepared_library(snapshot, destination, clips, *, cancelled=lambda: False, publish_guard=nullcontext):
    """Author/export a portable snapshot with exact already-decoded voice bytes.

    clips maps original text IDs to .mp3/.wav paths. The original archive refs
    are replaced by local content-addressed clips; credentials are never copied.
    """
    def guard():
        if cancelled():
            raise InterruptedError('Prepared library export cancelled')
    guard()
    payload = {key: snapshot[key] for key in ('format', 'game', 'source_locale')}
    for key in ('fingerprint', 'source_region', 'source_mode', 'reader_revision'):
        if key not in snapshot:
            continue
        value = snapshot[key]
        if key == 'reader_revision':
            valid = type(value) is int and 0 <= value <= 2**31 - 1
        elif key == 'fingerprint':
            valid = isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,255}', value))
        elif key == 'source_region':
            valid = isinstance(value, str) and value in {'global', 'cn', 'mainland'}
        else:
            valid = isinstance(value, str) and value in {'publisher', 'installed', 'prepared'}
        if not valid:
            raise ValueError('Invalid prepared library source identity')
        payload[key] = value
    for key in ('capture_capabilities',):
        if key in snapshot:
            payload[key] = snapshot[key]
    for key in ('publisher_song_cues', 'publisher_song_voices', 'publisher_film_cues', 'publisher_top_dialogue_cues'):
        if key in snapshot:
            if type(snapshot[key]) is not int or not 0 <= snapshot[key] <= MAX_ROWS:
                raise ValueError('Invalid authored caption inventory count')
            payload[key] = snapshot[key]
    payload.update(install=None, records=[])
    if 'publisher_world_dialogue_ui' in snapshot:
        from .endfield_presentation import validate_world_dialogue_ui
        if snapshot.get('game') != 'endfield':
            raise ValueError('World dialogue metadata belongs to its original game')
        payload['publisher_world_dialogue_ui'] = validate_world_dialogue_ui(snapshot['publisher_world_dialogue_ui'])
    if 'publisher_sns_dialogue_ui' in snapshot:
        from .endfield_sns_presentation import validate_sns_dialogue_ui
        if snapshot.get('game') != 'endfield':
            raise ValueError('Baker dialogue metadata belongs to its original game')
        payload['publisher_sns_dialogue_ui'] = validate_sns_dialogue_ui(snapshot['publisher_sns_dialogue_ui'])
    audio = {}
    for original in snapshot['records']:
        guard()
        row = dict(original)
        if row.get('audio'):
            clip = clips(original) if callable(clips) else clips.get((row['text_id'], row.get('player_voice')), clips.get(row['text_id']))
            if clip is None:
                row.update(audio=None, voice_status='unavailable')
            else:
                clip = Path(clip)
                _no_links(clip)
                if clip.suffix not in {'.mp3', '.wav'} or not 0 < clip.stat().st_size <= MAX_AUDIO:
                    raise ValueError('Unsupported prepared audio clip')
                with clip.open('rb') as source:
                    digest = hashlib.file_digest(source, 'sha256').hexdigest()
                name = f'audio/{digest}{clip.suffix}'
                audio[name] = clip
                row['audio'] = {'prepared_clip': name, 'locale': row['audio_locale']}
        payload['records'].append(row)
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    _snapshot(raw, audio)
    manifest = {'format': FORMAT, 'game': payload['game'], 'files': {
        'textmap.json': {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}}
    for name, clip in audio.items():
        manifest['files'][name] = {'size': clip.stat().st_size, 'sha256': CLIP.fullmatch(name)[1]}
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    if (len(manifest_raw) > MAX_MANIFEST
            or len(raw) + len(manifest_raw) + sum(item['size'] for name, item in manifest['files'].items()
                if name != 'textmap.json') + 4096 + 512 * len(manifest['files']) > MAX_LIBRARY):
        raise ValueError('Prepared library exceeds its bounded storage capacity')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_suffix(destination.suffix + '.pending')
    _no_links(pending)
    try:
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            archive.writestr('manifest.json', manifest_raw)
            archive.writestr('textmap.json', raw)
            for name, clip in audio.items():
                digest, size = hashlib.sha256(), 0
                with clip.open('rb') as source, archive.open(name, 'w', force_zip64=True) as output:
                    while block := source.read(1024 * 1024):
                        guard();size += len(block)
                        if size > MAX_AUDIO:
                            raise ValueError('Prepared audio changed during export')
                        digest.update(block);output.write(block)
                if digest.hexdigest() != manifest['files'][name]['sha256'] or size != manifest['files'][name]['size']:
                        raise ValueError('Prepared audio changed during export')
        if pending.stat().st_size > MAX_LIBRARY:
            raise ValueError('Prepared library exceeds its bounded storage capacity')
        with publish_guard() as mark_committed:
            guard()
            pending.replace(destination)
            if mark_committed:
                mark_committed()
    except BaseException:
        pending.unlink(missing_ok=True)
        raise
    return destination
