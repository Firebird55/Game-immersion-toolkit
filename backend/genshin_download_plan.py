"""Manifest-owned transfer/cache budgets; no large publisher payload is read.

A caller-owned authenticated design catalog narrows text packages exactly.
Without it, every design package is an explicit upper bound. This plan covers
the original TextMap/native-input and complete selected-dub PCK cache only;
unquoted components must be added before claiming a whole-game download size.
"""
import hashlib
import json
import re

from .genshin_official_text import CODES, shard_inventory
from .genshin_original_containers import DesignCatalog, asset_identity
from .genshin_original_excel import MANUAL_PATH, MAX_METADATA, metadata_name


TEXT_CODES = {'en': 'EN', 'zh-Hans': 'CHS', 'zh-Hant': 'CHT', 'ja': 'JP', 'ko': 'KR',
              'fr': 'FR', 'de': 'DE', 'es-ES': 'ES', 'pt-BR': 'PT', 'ru': 'RU', 'th': 'TH',
              'vi': 'VI', 'id': 'ID', 'it': 'IT', 'tr': 'TR'}
VOICES = frozenset({'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'})
INDEX_PACKAGE = 'blocks/00/31049741.blk'
MAX_DECODED_BODY = 512 * 1024**2


def check(value):
    if not value:
        raise ValueError('Incomplete or ambiguous official Genshin download plan.')


def plan(build, native, voice_files, design_files, *, metadata, content_mode, study_locales, target_locales=(),
         catalog=None, catalog_publisher=None):
    """Budget immutable official inputs, deduplicating their actual cache keys.

    Metadata and catalog authenticity belong to the publisher acquisition layer.
    ``catalog_publisher`` must name that same fully authenticated generation.
    No file's read() operation is called and no cache hit is assumed verified.
    """
    check(isinstance(build, dict) and build.get('channel') in {'genshin-global', 'genshin-cn'})
    raw = json.dumps(build, sort_keys=True, separators=(',', ':')).encode()
    publisher = 'sophon-' + hashlib.sha256(raw).hexdigest()
    studies, targets = tuple(study_locales), tuple(target_locales)
    check(content_mode in {'text', 'text-audio'} and studies
          and all(locale in TEXT_CODES for locale in studies + targets))
    if content_mode == 'text-audio':
        check(all(locale in VOICES for locale in studies) and set(voice_files) == set(studies))
    else:
        check(not voice_files)
    codes = sorted({TEXT_CODES[locale] for locale in studies + targets})
    check(type(native.size) is int and 512 <= native.size <= 768 * 1024**2)
    check(type(metadata.size) is int and 512 <= metadata.size <= MAX_METADATA)
    check(isinstance(getattr(metadata, 'chunks', None), tuple) and metadata.chunks)
    check(set(codes) <= CODES and INDEX_PACKAGE in design_files)
    selected = set(design_files)
    text_kind = 'upper-bound'
    if catalog is not None:
        check(isinstance(catalog, DesignCatalog) and catalog_publisher == publisher)
        selected = {catalog.locate(row['identity']).package for code in codes for row in shard_inventory(catalog, code)}
        selected.add(INDEX_PACKAGE)
        selected.add(catalog.locate(asset_identity(MANUAL_PATH)).package)
        check(selected <= design_files.keys())
        text_kind = 'exact'
    objects = {}

    def add(kind, digest, wire, stored, part):
        check(isinstance(digest, str) and re.fullmatch('[a-f0-9]{32}', digest)
              and type(wire) is type(stored) is int and 0 < wire <= 8 * 1024**3 and 0 < stored <= 8 * 1024**3)
        key = kind + ':' + digest
        if key in objects:
            previous = objects[key]
            check(previous['cache_bytes'] == stored)
            # Several verified encodings can share the same decoded cache key.
            # Keep the largest declared wire size, never an arbitrary estimate.
            previous['wire_bytes'] = max(previous['wire_bytes'], wire)
            previous['parts'].add(part)
            return
        objects[key] = {'kind': kind, 'md5': digest, 'wire_bytes': wire, 'cache_bytes': stored, 'parts': {part}}

    def asset(item, part):
        check(type(item.size) is int and 0 < item.size <= 8 * 1024**3
              and isinstance(item.digest, str) and re.fullmatch('[a-f0-9]{32}', item.digest))
        chunks = getattr(item, 'chunks', None)
        if chunks is None:
            add('genshin-http-package', item.digest, item.size, item.size, part)
            return
        check(isinstance(chunks, tuple) and chunks)
        end = 0
        for row in chunks:
            check(isinstance(row, tuple) and len(row) == 5)
            offset, size, compressed, name, digest = row
            check(type(offset) is type(size) is type(compressed) is int and offset == end
                  and 0 < size <= 64 * 1024**2 and 0 < compressed <= 64 * 1024**2
                  and isinstance(digest, str) and re.fullmatch('[a-f0-9]{32}', digest)
                  and isinstance(name, str) and re.fullmatch('[a-f0-9]{16}_' + re.escape(digest), name))
            add('sophon-chunk', digest, compressed, size, part)
            end += size
        check(end == item.size)

    asset(native, 'native')
    asset(metadata, 'native-metadata')
    for files in voice_files.values():
        check(isinstance(files, dict) and files)
        for item in files.values():
            asset(item, 'voice')
    for name in sorted(selected):
        row = design_files[name]
        check(isinstance(row, dict) and row.get('remoteName') == name
              and re.fullmatch(r'blocks/[0-9]{2,10}/[0-9]{1,10}\.blk', name))
        add('genshin-http-package', row['md5'], row['fileSize'], row['fileSize'], 'text')
    ledger = [{**row, 'cache_key': key, 'parts': sorted(row['parts'])} for key, row in sorted(objects.items())]
    wire = sum(row['wire_bytes'] for row in ledger)
    cache = sum(row['cache_bytes'] for row in ledger)
    # Existing PC source execution retains bounded decoded containers. This is
    # deliberately conservative, not an inferred compression ratio. A platform
    # adapter may quote less only with a separately enforced eviction contract.
    decoded = len(selected) * MAX_DECODED_BODY
    staging = sum(sorted((row['cache_bytes'] for row in ledger), reverse=True)[:6]) + MAX_DECODED_BODY
    result = {'schema': 'genshin-official-download-plan-v1', 'publisher': publisher,
        'region': build['channel'].removeprefix('genshin-'), 'content_mode': content_mode,
        'study_locales': sorted(set(studies)), 'text_codes': codes,
        'scope': ('current-original-textmap-manual-native-input-and-complete-selected-dub-pck-cache'
                  if content_mode == 'text-audio' else 'current-original-textmap-manual-native-input'),
        'complete_game_quote': False, 'text_selection': text_kind, 'selected_design_packages': len(selected),
        'catalog_sha256': catalog.sha256 if catalog is not None else None,
        'transfer_bytes_upper_bound': wire, 'official_object_cache_bytes_upper_bound': cache,
        'native_materialization_bytes_exact': native.size, 'metadata_materialization_bytes_exact': metadata.size,
        'native_metadata': {'name': metadata_name(build['channel']), 'publisher_md5': metadata.digest,
                            'bytes': metadata.size, 'chunks_sha256': hashlib.sha256(json.dumps(metadata.chunks,
                                separators=(',', ':')).encode()).hexdigest()},
        'decoded_containers_bytes_upper_bound': decoded,
        'resident_bytes_upper_bound': cache + native.size + metadata.size + decoded,
        'peak_bytes_upper_bound': cache + native.size + metadata.size + decoded + staging,
        'cache_reuse_subtracted': False, 'objects': ledger,
        'unquoted_components': ['metadata-api-and-manifest-fetches', 'controlled-binding-archives',
            'dispatch-bootstrap-parameter-source', 'Readable/Subtitle-source-routes',
            'publisher-movie-assets-and-film-audio', 'derived-dialogue-index', 'shared-runtime-codecs', 'historical-audio-retention']}
    result['sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result
