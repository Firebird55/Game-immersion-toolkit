"""Consented complete original ZZZ dub preparation and local voice restoration."""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct

from .atomic_files import write_bytes
from .sophon_assets import descriptor
from .zzz_dialogue_records import LANGUAGE_INDEX_VERSION, SCOPE, TEXT_LOCALES, _dialogue_records, _group_links
from .zzz_source_bindings import original_bindings, voice_directory
from . import zzz_publisher_cinematics as cinema
from . import zzz_hotfix
from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage, SnapshotSource, SourceProof
from .language_snapshot import write_payload
from .languages import audio_locale, resolve_locale
from .private_data_paths import MAX_AUDIO, MAX_TEXT, MAX_ROWS
from .zzz_audio_catalogue import Catalogue
from .zzz_audio_sources import AudioSources
from .zzz_game_data import _safe

SCHEMA = 'zzz-pc-official-audio-v1'
MAX_PLAN = 32 * 1024**2
SCRATCH_BYTES = 3 * MAX_TEXT + 3 * MAX_AUDIO


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _path(ctx, category, digest):
    if category not in ('candidates', 'plans') or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise GameDataError('zzz_audio_stage_changed', 'Check the selected original audio source again.', 409)
    return _safe(Path(ctx.cache_directory) / 'zzz-audio' / category / (digest + '.json'))


def _store(ctx, category, value):
    raw = encoded(value)
    maximum = MAX_TEXT if category == 'candidates' else MAX_PLAN
    if len(raw) > maximum:raise GameDataError('zzz_audio_stage_bounds', 'The selected original audio metadata exceeds its supported bounds.')
    digest = hashlib.sha256(raw).hexdigest();path = _path(ctx, category, digest)
    path.parent.mkdir(parents=True, exist_ok=True);ctx.check();write_bytes(path, raw, check=ctx.check)
    return digest


def _load(ctx, category, digest):
    path = _path(ctx, category, digest)
    maximum = MAX_TEXT if category == 'candidates' else MAX_PLAN
    if not path.is_file() or not 0 < path.stat().st_size <= maximum:
        raise GameDataError('zzz_audio_stage_missing', 'Original audio preparation inputs are unavailable. Check their size again.', 409)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise GameDataError('zzz_audio_stage_integrity', 'The local original audio inputs failed validation.', 409)
    ctx.check();return json.loads(raw)


def _candidate(ctx, handle, revision, reader):
    if not (isinstance(handle, dict) and handle.get('request') == ctx.request.json()
            and handle.get('revision') == revision and handle.get('reader') == reader.identity and handle.get('candidate')):
        return None
    result = _load(ctx, 'candidates', handle['candidate'])
    if (result.get('request') != ctx.request.json() or result.get('revision') != revision
            or result.get('reader') != reader.identity or result.get('schema') != SCHEMA):
        raise GameDataError('zzz_audio_stage_changed', 'The original audio inputs belong to another selection.', 409)
    return result


def save_candidate(ctx, handle, result, reader):
    value = {'schema': SCHEMA, 'revision': handle['revision'], 'request': ctx.request.json(),
             'reader': reader.identity, 'content': result}
    digest = _store(ctx, 'candidates', value)
    return PreparationStage({**handle, 'candidate': digest}, 'Original dialogue and voice references verified. Check the selected audio download size.')


def _range(name, offset, size):return {'name': name, 'offset': offset, 'size': size}


def _headers(files):return [_range(name, 0, 28) for name in sorted(files)]


def _tables(sources, files):
    ranges = []
    for name, asset in sorted(files.items()):
        raw = sources.read(asset, 0, 28)
        if raw[:4] != b'AKPK':raise GameDataError('zzz_audio_package_schema', 'The original ZZZ package header changed.')
        size, endian, *parts = struct.unpack_from('<6I', raw, 4)
        if endian != 1 or size != 20 + sum(parts) or not 20 <= size <= min(asset.size - 8, 32 * 1024**2):
            raise GameDataError('zzz_audio_package_schema', 'The original ZZZ package tables changed.')
        ranges.append(_range(name, 0, size + 8))
    return ranges


def _bank_metadata_ranges(sources, files, name, entry, identifier, language):
    result = [_range(name, entry.offset, 20)]
    if not sources.ranges_available(files, result):return result
    first = sources.read(files[name], entry.offset, 20)
    if first[:4] != b'BKHD' or struct.unpack_from('<3I', first, 8) != (135, identifier, cinema.wwise_hash(language)):
        raise GameDataError('zzz_audio_bank_schema', 'The original ZZZ bank format or language changed. Previous prepared data is kept.', 409)
    position = 0
    while position + 8 <= entry.size:
        header = _range(name, entry.offset + position, 8);result.append(header)
        if not sources.ranges_available(files, [header]):return result
        kind, size = struct.unpack('<4sI', sources.read(files[name], entry.offset + position, 8))
        end = position + 8 + size
        if end > entry.size:raise GameDataError('zzz_audio_bank_schema', 'The original ZZZ bank has invalid chunk bounds.')
        if kind in (b'HIRC', b'DIDX') and size:
            result.append(_range(name, entry.offset + position + 8, size))
        # DATA bodies are selected only after an actual event/media join.
        position = end
    if position != entry.size:raise GameDataError('zzz_audio_bank_schema', 'The original ZZZ bank has a truncated chunk header.')
    return result


def _banks(sources, files, catalogue, links, registry):
    _, _, events = cinema.requested_events(links, registry)
    wanted = set().union(*(registry.get(event, set()) for event in events))
    if any(mode == 'unconditional_voice_layer' for _, mode in events.values()):
        wanted.add(cinema.wwise_hash(cinema.INITIAL_BANK_FILENAME.rsplit('.', 1)[0]))
    banks, _, dependencies = catalogue.inventory(wanted)
    ranges = []
    for entries, language in ((banks, catalogue.namespace), (dependencies, 'sfx')):
        for identifier, (name, entry) in entries.items():
            ranges += _bank_metadata_ranges(sources, files, name, entry, identifier, language)
    return ranges


def _payload(ctx, current, content, catalogue, registry):
    links, tables = content['links'], content['tables']
    expanded, channels, evidence, kinds = _group_links(links)
    consistent = [row for row in expanded if evidence[row['text_id']] == {'unavailable'}]
    bindings = original_bindings(consistent, catalogue.externals(), catalogue.locale,
        current['version'], voice_directory(content['voice_directory']))
    contexts = catalogue.bindings(links, registry)
    for identity, value in contexts.items():bindings.setdefault(identity, value)
    for link in links:
        if 'start_ms' in link and (binding := bindings.get(link['text_id'])):
            bindings[link['text_id']] = {**binding, 'start_ms': link['start_ms'], 'end_ms': link['end_ms']}
    rows = _dialogue_records(tables, ctx.request.source_locale, set(tables), channels, evidence, kinds, bindings)
    coverage = dict(content['coverage'])
    coverage['cinema_context_recordings'] = len({sound['event'] for sound in contexts.values()})
    coverage['cinema_context_subtitle_bindings'] = len(contexts)
    coverage['presentation_owners'] = {**coverage['presentation_owners'],
        'subtitle_audio_acquisition': 'partial-subtitle-tracks-and-original-film-contexts'}
    available = {locale for row in rows for locale in row['texts']}
    payload = {'format': 2, 'game': 'zzz', 'source_locale': ctx.request.source_locale, 'content_mode': 'text-audio',
        'source_mode': 'publisher', 'publisher_region': ctx.request.region, 'install': None,
        'fingerprint': descriptor(current)[0],
        'metadata_revision': current['build'] + '/' + current['hotfix']['revisions']['design'],
        'records': rows, 'coverage': coverage,
        'missing_translation_locales': [locale for locale in ctx.request.target_locales
            if resolve_locale(locale, TEXT_LOCALES) not in available],
        'coverage_warnings': [SCOPE], 'message': 'Official ZZZ dialogue and selected original audio prepared.'}
    from .zzz_cinema_occurrences import FIELD, build
    occurrences = build(payload, content['cinema_occurrences'], ctx.request.json()) if content.get('cinema_occurrences') else None
    if occurrences is not None:
        payload[FIELD] = occurrences
    return payload


def _selection(ctx, current, content, sources):
    files = sources.assets()
    catalogue = Catalogue(files, sources.locale, descriptor(current)[0], sources.read)
    registry = cinema.audio_registry(base64.b64decode(content['registry'], validate=True))
    metadata = _headers(files)
    if not sources.ranges_available(files, metadata):return 'audio-package-headers', files, metadata, None
    metadata = _tables(sources, files)
    if not sources.ranges_available(files, metadata):return 'audio-package-tables', files, metadata, None
    metadata += _banks(sources, files, catalogue, content['links'], registry)
    if not sources.ranges_available(files, metadata):return 'audio-banks', files, metadata, None
    payload = _payload(ctx, current, content, catalogue, registry)
    recordings = {}
    for row in payload['records']:
        if not row.get('audio'):continue
        name, entry = catalogue.recording(row['audio'])
        recordings[name, entry.offset, entry.size] = _range(name, entry.offset, entry.size)
    return 'audio-recordings', files, [*metadata, *recordings.values()], payload


def plan_inputs(ctx, current, handle, *, transport_factory, verification=None):
    sources = AudioSources(ctx, current, audio_locale(ctx.request.source_locale), transport_factory=transport_factory, verification=verification)
    if sources.inputs_available():return None
    network, disk = sources.quote_inputs()
    return GameDataPlan(handle['revision'], network, disk, handle={**handle, 'mode': 'audio-indexes'},
        runtime_available=True, stage='audio-indexes', download_is_upper_bound=True,
        message='Download the selected official dub indexes first, then check the required recording size.')


def plan_candidate(ctx, current, handle, reader, *, transport_factory, final_metadata_bytes, verification=None):
    previous = getattr(ctx, 'stage_handle', None)
    candidate = _candidate(ctx, previous, handle['revision'], reader)
    if candidate is None:return None
    handle = {**handle, 'candidate': previous['candidate']}
    sources = AudioSources(ctx, current, audio_locale(ctx.request.source_locale), transport_factory=transport_factory, verification=verification)
    mode, files, ranges, _ = _selection(ctx, current, candidate['content'], sources)
    document = {'schema': SCHEMA, 'revision': handle['revision'], 'request': ctx.request.json(),
        'candidate': handle['candidate'], 'mode': mode, 'ranges': ranges,
        'files': [files[name].json() for name in sorted({row['name'] for row in ranges})]}
    digest = _store(ctx, 'plans', document)
    network, disk = sources.quote_ranges(files, ranges, scratch_bytes=SCRATCH_BYTES)
    handle.update(mode=mode, audio_plan=digest, source_network_bytes=network)
    allowance = final_metadata_bytes if mode == 'audio-recordings' else 0
    return GameDataPlan(handle['revision'], network + allowance, disk, handle=handle,
        runtime_available=True, stage=mode, download_is_upper_bound=True, final_transfer=mode == 'audio-recordings',
        message='Download the selected complete original recordings and their required bank containers. Previously prepared data is kept.')


def download(ctx, planned, reader, codecs, *, transport_factory, verify_current, verification=None, crypto=None):
    handle = planned.handle
    if (codecs is None or handle.get('request') != ctx.request.json() or ctx.request.content_mode != 'text-audio'
            or handle.get('revision') != planned.revision or handle.get('reader') != reader.identity
            or descriptor(handle['build'])[0] != planned.revision):
        raise GameDataError('zzz_audio_stage_changed', 'Check the selected original audio download and runtime again.', 409)
    sources = AudioSources(ctx, handle['build'], audio_locale(ctx.request.source_locale),
                           transport_factory=transport_factory, verification=verification)
    if handle['mode'] == 'audio-indexes':
        if sources.quote_inputs() != (planned.download_bytes, planned.required_disk_bytes):
            raise GameDataError('zzz_audio_stage_changed', 'The cached original audio inputs changed. Check their size again.', 409)
        sources.download_inputs()
        return PreparationStage(handle, 'Original dub indexes verified. Check the next download size.')
    candidate = _candidate(ctx, handle, planned.revision, reader)
    if candidate is None:raise GameDataError('zzz_audio_stage_missing', 'The original dialogue inputs are unavailable. Check again.', 409)
    document = _load(ctx, 'plans', handle['audio_plan'])
    if any(document.get(key) != handle.get(key) for key in ('revision', 'request', 'candidate', 'mode')):
        raise GameDataError('zzz_audio_stage_changed', 'The original audio range plan belongs to another selection.', 409)
    files = sources.assets()
    expected = [files[name].json() for name in sorted({row['name'] for row in document['ranges']})]
    network, _ = sources.quote_ranges(files, document['ranges'])
    if expected != document['files'] or network > handle['source_network_bytes']:
        raise GameDataError('zzz_audio_stage_changed', 'The selected audio owners changed. Check the download size again.', 409)
    sources.download_ranges(files, document['ranges'])
    if handle['mode'] != 'audio-recordings':
        return PreparationStage(handle, 'Original audio ownership containers verified. Check the remaining recording size.')
    ctx.progress('verifying', ctx.consumed, ctx.budget, 'Verifying the downloaded ZZZ recordings…')
    mode, _, ranges, payload = _selection(ctx, handle['build'], candidate['content'], sources)
    if mode != 'audio-recordings' or ranges != document['ranges'] or not sources.ranges_available(files, ranges):
        raise GameDataError('zzz_audio_stage_changed', 'Complete selected originals are not available. Check their size again.', 409)
    # A successful index with only remote recording addresses is never Ready.
    verify_current(ctx, handle['build'], planned.revision, transport_factory, crypto=crypto)
    destination = _safe(ctx.directory / 'textmap.json')
    write_payload('zzz', payload, ctx.request.source_locale, ctx.request.target_locales, destination, check=ctx.check, reader_revision=LANGUAGE_INDEX_VERSION)
    with destination.open('rb') as stream:snapshot_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    keys = _binding_keys(payload)
    raw_keys = encoded({'schema': 'zzz-original-bindings-v1', 'revision': planned.revision, 'keys': sorted(keys)})
    if len(raw_keys) > MAX_TEXT:raise GameDataError('zzz_audio_binding_bounds', 'The selected original binding index exceeds its supported size.')
    ctx.check();write_bytes(_safe(ctx.directory / 'original-bindings.json'), raw_keys, check=ctx.check)
    receipt = {'schema': SCHEMA, 'revision': planned.revision, 'request': ctx.request.json(), 'build': handle['build'],
        'reader': reader.identity, 'codecs': codecs.identity, 'candidate': handle['candidate'], 'audio_plan': handle['audio_plan'],
        'snapshot_sha256': snapshot_sha, 'bindings_sha256': hashlib.sha256(raw_keys).hexdigest(),
        'player_bindings': 1, 'reader_revision': LANGUAGE_INDEX_VERSION}
    raw = encoded(receipt);digest = hashlib.sha256(raw).hexdigest()
    ctx.check();write_bytes(_safe(ctx.directory / 'source-receipt.json'), raw, check=ctx.check)
    restored = {'schema': SCHEMA, 'game': 'zzz', 'revision': planned.revision, 'request': ctx.request.json(),
        'receipt_sha256': digest, 'snapshot_sha256': snapshot_sha}
    source = LocalOriginals(sources, files, planned.revision, keys, codecs)
    return SnapshotSource(destination, restored, SourceProof('official', digest, True), source)


def _audio_key(audio):return hashlib.sha256(encoded({key: value for key, value in audio.items() if value is not None})).hexdigest()


def _binding_keys(payload):
    from .zzz_cinema_occurrences import recording_rows
    return {(row['text_id'], _audio_key(row['audio'])) for row in (*payload['records'], *recording_rows(payload))
            if row.get('audio') and row['voice_status'] == 'voiced'}


def _restore_keys(ctx, receipt, verification):
    path = _safe(ctx.directory / 'original-bindings.json')
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_TEXT:
        raise GameDataError('zzz_audio_restore_integrity', 'The retained original binding index is unavailable.', 409)
    key = str(path), zzz_hotfix._stamp(path.stat()), receipt['bindings_sha256'], receipt['revision']
    cached = {} if verification is None else verification.setdefault('bindings', {})
    if key not in cached:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt['bindings_sha256']:
            raise GameDataError('zzz_audio_restore_integrity', 'The retained original binding index failed validation.', 409)
        value = json.loads(raw)
        if (value.get('schema') != 'zzz-original-bindings-v1' or value.get('revision') != receipt['revision']
                or not isinstance(value.get('keys'), list) or len(value['keys']) > MAX_ROWS
                or any(not isinstance(row, list) or len(row) != 2 or not isinstance(row[0], str)
                       or not row[0] or len(row[0]) > 4096 or not isinstance(row[1], str)
                       or not re.fullmatch('[a-f0-9]{64}', row[1]) for row in value['keys'])):
            raise GameDataError('zzz_audio_restore_integrity', 'The original binding index has an unsupported schema.', 409)
        cached[key] = frozenset(tuple(row) for row in value['keys'])
    ctx.check();return cached[key]


def _restore_player_bindings(ctx, receipt, snapshot, keys, verification):
    if receipt.get('player_bindings') == 1:
        return keys
    from .zzz_cinema_occurrences import recording_rows
    identity = receipt['snapshot_sha256'], receipt['bindings_sha256']
    cache = {} if verification is None else verification.setdefault('player_bindings', {})
    if identity not in cache:
        # Existing installations already verified these media. Derive the new
        # occurrence IDs only from the exact retained snapshot and key receipt.
        with snapshot.open('rb') as stream:
            raw = stream.read(MAX_TEXT + 1)
        if len(raw) > MAX_TEXT or hashlib.sha256(raw).hexdigest() != identity[0]:
            raise GameDataError('zzz_audio_restore_integrity', 'The retained dialogue failed validation.', 409)
        payload = json.loads(raw)
        approved_audio = {digest for _, digest in keys}
        extra = set()
        for row in recording_rows(payload):
            digest = _audio_key(row['audio'])
            if digest in approved_audio:
                extra.add((row['text_id'], digest))
        if len(cache) >= 16:
            cache.pop(next(iter(cache)))
        cache[identity] = extra - keys
    ctx.check()
    return keys | cache[identity]


class LocalOriginals:
    def __init__(self, sources, files, revision, keys, codecs):
        self.sources = sources
        self.catalogue = Catalogue(files, sources.locale, revision, sources.read)
        self.codecs = codecs
        self.keys = keys

    def has(self, row):
        return bool(self.codecs is not None and row.get('voice_status') == 'voiced' and not row.get('audio_omitted_by_request')
                    and isinstance(row.get('audio'), dict) and (row.get('text_id'), _audio_key(row['audio'])) in self.keys)

    def resolve(self, row, destination, *, cancelled):
        if not self.has(row):raise GameDataError('zzz_original_not_downloaded', 'This selected original recording is unavailable.', 409)
        def stopped():
            if cancelled():return True
            try:self.sources.ctx.check();return False
            except GameDataError:return True
        if stopped():raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
        raw = self.catalogue.extract(row['audio'])
        return self.codecs.resolve(raw, row['audio'], destination, cancelled=stopped)


def restore(ctx, handle, codecs, *, transport_factory, verification=None):
    if (handle.get('schema') != SCHEMA or handle.get('request') != ctx.request.json() or ctx.request.content_mode != 'text-audio'):
        raise GameDataError('zzz_audio_restore_selection', 'The prepared originals belong to another selection.', 409)
    path = _safe(ctx.directory / 'source-receipt.json');raw = path.read_bytes()
    if len(raw) > MAX_PLAN or hashlib.sha256(raw).hexdigest() != handle.get('receipt_sha256'):
        raise GameDataError('zzz_audio_restore_integrity', 'The original audio source receipt failed validation.', 409)
    receipt = json.loads(raw)
    if (receipt.get('schema') != SCHEMA or receipt.get('request') != ctx.request.json()
            or receipt.get('revision') != handle.get('revision') or descriptor(receipt['build'])[0] != handle['revision']):
        raise GameDataError('zzz_audio_restore_integrity', 'The retained original audio source identity changed.', 409)
    snapshot = _safe(ctx.directory / 'textmap.json')
    with snapshot.open('rb') as stream:digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != handle.get('snapshot_sha256') or digest != receipt.get('snapshot_sha256'):
        raise GameDataError('zzz_audio_restore_integrity', 'The retained dialogue and original bindings failed validation.', 409)
    if codecs is None:raise GameDataError('zzz_audio_runtime_missing', 'The verified original-audio decoder is unavailable. Repair the app runtime.', 409)
    sources = AudioSources(ctx, receipt['build'], audio_locale(ctx.request.source_locale),
                           transport_factory=transport_factory, verification=verification)
    document = _load(ctx, 'plans', receipt['audio_plan'])
    if (document.get('mode') != 'audio-recordings' or document.get('request') != ctx.request.json()
            or document.get('revision') != handle['revision'] or document.get('candidate') != receipt.get('candidate')):
        raise GameDataError('zzz_audio_restore_integrity', 'The retained original recording selection failed validation.', 409)
    files = sources.assets()
    expected = [files[name].json() for name in sorted({row['name'] for row in document['ranges']})]
    if expected != document['files'] or not sources.ranges_available(files, document['ranges']):
        raise GameDataError('zzz_original_not_downloaded', 'Some downloaded originals are missing. Check the game download size again.', 409)
    keys = _restore_keys(ctx, receipt, verification)
    keys = _restore_player_bindings(ctx, receipt, snapshot, keys, verification)
    ctx.check();source = LocalOriginals(sources, files, handle['revision'], keys, codecs)
    return SnapshotSource(snapshot, handle, SourceProof('official', handle['receipt_sha256'], True), source)
