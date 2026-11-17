"""Coherent publisher snapshots for NTE text, authoring and original voices."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time

from . import nte_archive_metadata as metadata, nte_release as release
from . import nte_publisher_pak as pak, nte_publisher_iostore as iostore
from . import nte_type_metadata as type_metadata
from .game_tools import _atomic_file
from .preparation_errors import PreparationFailure

ROOT = 'Client/WindowsNoEditor/HT/Content/'
SCHEMA = 1
# Frozen existing format descriptions, proved against original archive indices
# and localization in both supplied generations. No latest source is followed
# for the original-native recipe. Rotated parameters remain explicit failures.
NATIVE_ARCHIVE = ('7f3fb1dee733d36338766467b0c54cbd47d58851', 'aba72c557c302444c85c89a0789a4cac04a7a3e7f56b6324330c897db2a00566')
NATIVE_LOCALIZATION = ('d45c24674d84c3c2c61ae5315a37a80dac97e04f', '855abc7dbf3b39f5a7cf04ac5c613a3281992afb8cdb4c4f844722f816b7ea34')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def _path(tools, stamp):
    pak.check(isinstance(stamp, str) and re.fullmatch(r'nte-[0-9a-f]{64}', stamp))
    return Path(tools) / 'nte-publisher' / stamp / 'release.json'


def snapshot(tools, stamp):
    raw = _path(tools, stamp).read_bytes()
    pak.check('nte-' + hashlib.sha256(raw).hexdigest() == stamp)
    result = json.loads(raw)
    pak.check(result['schema'] == SCHEMA and result['region'] in release.HOSTS and
              isinstance(result['files'], dict) and 0 < len(result['files']) <= 100_000)
    for name, info in result['files'].items():
        pak.check(isinstance(name, str) and name.startswith(ROOT) and '..' not in name and '\\' not in name)
        pak._file(release.File(**info), 1024**4)
    if 'publisher_files' in result:
        from . import nte_native_provider as native
        original = native.discovery(result)
        pak.check({name: row for name, row in original['files'].items() if name.startswith(ROOT)} == result['files'])
        reference = result.get('type_schema', {})
        if reference.get('kind') == native.KIND:
            pak.check(set(reference) == {'kind', 'generator', 'validator', 'inventory_sha256', 'seed_sha256',
                                        'reader_sha256', 'baseline_inventory_sha256', 'baseline_native_sha256'})
            for key in ('inventory_sha256', 'seed_sha256', 'reader_sha256', 'baseline_inventory_sha256', 'baseline_native_sha256'):
                pak.check(isinstance(reference[key], str) and re.fullmatch('[0-9a-f]{64}', reference[key]))
            for key in ('generator', 'validator'):
                pak.check(isinstance(reference[key], str) and re.fullmatch('[a-z0-9-]{1,128}', reference[key]))
            pak.check(reference['inventory_sha256'] == hashlib.sha256(native.metadata._json(original)).hexdigest()
                      and reference['reader_sha256'] == result['reader'])
    return result


def snapshot_available(tools, stamp):
    try:
        snapshot(tools, stamp)
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False


def _reader_identity():
    from .runtime_bundle import discover_layout
    layout = discover_layout()
    if layout.mode == 'bundle':
        from .prebuilt_readers import reader_source_identity
        return reader_source_identity('nte', layout=layout)
    root = Path(__file__).resolve().parents[1] / 'scripts/game-readers'
    return hashlib.sha256(b''.join((root / n).read_bytes() for n in ('NteReader.cs', 'NteReader.csproj'))).hexdigest()


def _discovery(region):
    branch, version, files, sections = release.discover(region)
    selected = {name: asdict(item) for name, item in files.items() if name.startswith(ROOT)}
    pak.check(selected)
    return {'region': region, 'branch': branch, 'version': version, 'files': selected, 'sections': sections,
            'publisher_files': {name: asdict(item) for name, item in files.items()}}


@lru_cache(maxsize=2)
def _current(tools, period, region):
    from . import nte_assets
    from . import nte_native_provider as native
    value = _discovery(region)
    cache = Path(tools) / 'nte-publisher/format'
    reader = _reader_identity()
    archive = metadata.load(revision=NATIVE_ARCHIVE[0], digest=NATIVE_ARCHIVE[1], cache=cache)
    localization = metadata.load_localization(revision=NATIVE_LOCALIZATION[0], digest=NATIVE_LOCALIZATION[1], cache=cache)
    types = native.source_reference(native.discovery(value), reader)
    value.update(schema=SCHEMA, reader=reader, type_schema=types,
                 index_schema=nte_assets.LANGUAGE_INDEX_VERSION,
                 archive=[archive.revision, archive.digest], localization=[localization.revision, localization.digest])
    raw = _json(value)
    stamp = 'nte-' + hashlib.sha256(raw).hexdigest()
    if not snapshot_available(tools, stamp):
        _atomic_file(_path(tools, stamp), raw)
    return stamp, value


def fingerprint(tools):
    from .publisher_regions import selected_region
    region = 'nte-' + selected_region(Path(tools), 'nte')
    return _current(Path(tools), int(time.monotonic() // 60), region)[0]


def priority(name):
    """Match CUE/Unreal's numeric _P patch order; reject equal-order overlaps."""
    match = re.search(r'_(\d+)_P\.(?:pak|utoc)$', name, re.I)
    if match:
        number = int(match[1])
        pak.check(number <= 0x7fffffff)
        return 100 * (number + 1) + 3
    return 103 if re.search(r'_P\.(?:pak|utoc)$', name, re.I) else 3


def _overlay(sources, paths):
    result, seen = {}, set()
    for name, source in sorted(sources.items(), key=lambda item: (-priority(item[0]), item[0])):
        order = priority(name)
        for path in paths(source):
            key = path.casefold()
            # Equal-priority duplicate claims have no evidenced winner, even if
            # their basenames or container sizes happen to sort consistently.
            pak.check((key, order) not in seen)
            seen.add((key, order))
            if key not in result:
                result[key] = (name, source, path)
    return result


class Catalog:
    def __init__(self, tools, stamp, progress=lambda _message: None):
        self.tools, self.stamp = Path(tools), stamp
        self.snapshot = snapshot(tools, stamp)
        self.region, self.branch = self.snapshot['region'], self.snapshot['branch']
        self.files = {n: release.File(**v) for n, v in self.snapshot['files'].items()}
        self.cache = self.tools / 'nte-publisher'
        revision, digest = self.snapshot['archive']
        self.format = metadata.load(revision=revision, digest=digest, cache=self.cache / 'format')
        self.progress, self.archives = progress, {}
        names = [n for n in self.files if n.endswith('.pak')]
        pak.check(0 < len(names) <= 128)
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.archives = dict(zip(names, pool.map(self.archive, names)))
        self.locations = _overlay(self.archives, lambda archive: archive.locations)

    def archive(self, name):
        if name not in self.archives:
            pak.check(name in self.files and name[:-4] + '.sig' in self.files)
            source = pak.SignedSource(self.region, self.branch, self.files[name], self.files[name[:-4] + '.sig'],
                                      self.cache / 'ranges', self.progress)
            return pak.Archive(source, self.format)
        return self.archives[name]

    def location(self, name):
        value = self.locations.get(name.casefold())
        return value if value and value[1].entry(value[2]) is not None else None

    def read(self, name):
        value = self.location(name)
        if value is None:
            raise FileNotFoundError('The selected NTE publisher snapshot has no live resource at this path.')
        return value[1].read(value[2])

    def containers(self):
        names = [n for n in self.files if n.endswith('.utoc')]
        pak.check(0 < len(names) <= 128)
        proven = next((archive for archive in self.archives.values() if archive.cipher is not None), None)
        pak.check(proven is not None)
        def read(name):
            pak.check(name[:-5] + '.ucas' in self.files)
            return iostore.Container(self.region, self.branch, self.files[name], self.files[name[:-5] + '.ucas'],
                                     proven, self.cache / 'iostore')
        with ThreadPoolExecutor(max_workers=4) as pool:
            values = dict(zip(names, pool.map(read, names)))
        globals_ = {n: v for n, v in values.items() if n.endswith('/global.utoc')}
        # NTE publishes the current global import context with PatchPaks. Base
        # globals are retained for historical/base-only releases, never combined.
        global_name = ROOT + 'PatchPaks/global.utoc'
        if global_name not in globals_:
            global_name = ROOT + 'Paks/global.utoc'
        pak.check(global_name in globals_ and not globals_[global_name].paths)
        ordinary = {n: v for n, v in values.items() if n not in globals_}
        _overlay(ordinary, lambda container: (p[0] for p in container.paths.values()))
        selected = {global_name[len(ROOT):]: globals_[global_name]}
        for name, container in ordinary.items():
            # A table can import types/objects from a container with no table
            # directory of its own. Register its checked index too; package
            # bytes remain fetched only when the parser actually needs them.
            if container.paths:
                selected[name[len(ROOT):]] = container
        pak.check(len(selected) > 1)
        return selected

    def prefetch(self, paths):
        """Read adjacent bank blocks in bounded batches before parsing each bank."""
        grouped = {}
        for name in paths:
            value = self.location(name)
            if not value:
                continue
            archive_name, archive, path = value
            entry = archive.entry(path)
            if entry.blocks:
                begin = entry.blocks[0][0]
                end, length = entry.blocks[-1]
                end += (length + 15) // 16 * 16 if entry.encrypted else length
            else:
                begin = entry.offset + entry.header_size
                length = (entry.size + 15) // 16 * 16 if entry.encrypted else entry.size
                end = begin + length
            if end > begin:
                grouped.setdefault(archive_name, set()).update(range(begin // pak.CHUNK, (end + pak.CHUNK - 1) // pak.CHUNK))
        for name, blocks in grouped.items():
            source = self.archives[name].source
            ordered = sorted(blocks)
            i = 0
            while i < len(ordered):
                j = i + 1
                while j < len(ordered) and ordered[j] == ordered[j - 1] + 1 and j - i < pak.TRANSFER // pak.CHUNK:
                    j += 1
                at = ordered[i] * pak.CHUNK
                source.read(at, min(source.item.size, (ordered[j - 1] + 1) * pak.CHUNK) - at)
                i = j


def _localization(catalog, locales, source_locale, destination):
    from .nte_assets import TEXT_LOCALES
    from .nte_locres import parse
    revision, digest = catalog.snapshot['localization']
    parameter = metadata.load_localization(revision=revision, digest=digest, cache=catalog.cache / 'format').parameter
    tables = {}
    for locale in locales:
        code = TEXT_LOCALES[locale]
        if code in tables:
            continue
        path = 'HT/Content/Localization/Game/' + code + '/Game.locres'
        if catalog.location(path):
            tables[code] = parse(catalog.read(path), parameter)
    source = tables.get(TEXT_LOCALES[source_locale])
    if not source:
        raise PreparationFailure('missing_text_pack', 'The selected NTE edition does not provide this text language. Choose the Global edition or another available study language in Setup.')
    hashes = {(r['ns'], r['key']): r['source_hash'] for r in source}
    rejected = {}
    for code, rows in tables.items():
        filtered = [r for r in rows if hashes.get((r['ns'], r['key'])) == r['source_hash']]
        if len(filtered) < len(rows):
            rejected[code] = len(rows) - len(filtered)
        tables[code] = filtered
    _atomic_file(destination / 'localization.json', _json(tables))
    return tables, rejected


def build_language(tools, source_locale, targets, progress=lambda _message: None):
    from . import nte_assets as assets
    from .languages import resolve_locale
    from .nte_cinematics import catalog_rows, movie_bindings, movie_namespaces
    from .publisher_regions import selected_region
    tools = Path(tools)
    if source_locale not in assets.SUPPORTED_LOCALES:
        raise ValueError('Unsupported NTE study/audio locale.')
    region = 'nte-' + selected_region(tools, 'nte')
    stamp, value = _current(tools, int(time.monotonic() // 60), region)
    resolved = {target: resolve_locale(target, assets.TEXT_LOCALES) for target in targets}
    locales = {source_locale, *(locale for locale in resolved.values() if locale)}
    progress('Reading coherent NTE publisher text, original authoring and selected voice banks')
    catalog = Catalog(tools, stamp, progress)
    executable = assets.ensure_extractor(tools)
    staging_root = tools.parent / 'nte-publisher-staging'
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=staging_root) as folder:
        staging = Path(folder)
        tables, rejected = _localization(catalog, locales, source_locale, staging)
        context = catalog.cache / 'empty-context'
        context.mkdir(parents=True, exist_ok=True)
        progress('Reading original NTE dialogue and movie authoring')
        native_proof = None
        if value['type_schema'].get('kind') == 'nte-original-native-v1':
            from . import nte_native_provider as native
            native_proof = native.read_authoring(catalog, executable, staging, progress)
        else:
            assets.run_publisher_reader(context, executable, staging, catalog.containers(),
                catalog.format.parameters[region], schema_cache=catalog.cache / 'schemas',
                table_schema=type_metadata.load(value['version'], catalog.cache / 'format/types', reference=value['type_schema']))
        movie_catalog = json.loads((staging / 'movie-tables.json').read_bytes())
        bindings = movie_bindings(catalog_rows(movie_catalog), movie_namespaces(movie_catalog, required=True))
        subtitles = {b['subtitle']: catalog.read(b['subtitle']).decode('utf-8-sig')
                     for b in bindings if catalog.location(b['subtitle'])}
        _atomic_file(staging / 'cinema-subtitles.json', _json(subtitles))
        language = assets.VOICE_LOCALES[source_locale]
        bank_root = 'HT/Content/WwiseAudio/Event/' + language + '/'
        media_root = 'HT/Content/WwiseAudio/Media/' + language + '/'
        banks, media = [], []
        for _, _, path in catalog.locations.values():
            if path.casefold().startswith(bank_root.casefold()) and re.fullmatch(r'Play_Vo_[A-Za-z0-9_]+\.bnk', Path(path).name, re.I) and catalog.location(path):
                banks.append(path)
            elif path.casefold().startswith(media_root.casefold()) and re.fullmatch(r'[0-9]+\.wem', Path(path).name) and catalog.location(path):
                media.append(media_root + Path(path).name)
        progress(f'Reading {len(banks):,} original {language} NTE voice banks')
        catalog.prefetch(banks)
        bank_dir = staging / 'banks'
        bank_dir.mkdir()
        seen, batches = set(), {}
        for path in banks:
            archive_name, archive, original = catalog.location(path)
            batches.setdefault(archive_name, (archive, []))[1].append(original)
        for archive, names in batches.values():
            batch, size, stored = [], 0, 0
            def write_batch():
                for path, data in zip(batch, archive.read_many(batch)):
                    name = 'Play_Vo_' + Path(path).name[8:]
                    pak.check(name.casefold() not in seen)
                    seen.add(name.casefold())
                    (bank_dir / name).write_bytes(data)
            for path in names:
                entry = archive.entry(path)
                if batch and (len(batch) == 256 or size + entry.size > pak.TRANSFER or stored + entry.stored > 2 * pak.TRANSFER):
                    write_batch()
                    batch, size, stored = [], 0, 0
                batch.append(path)
                size += entry.size
                stored += entry.stored
            if batch:
                write_batch()
        _atomic_file(staging / 'media.json', _json(media))
        available = {locale for locale in locales if tables.get(assets.TEXT_LOCALES[locale])}
        from .nte_native_metadata import CLASS_GENERATOR
        records = assets.build_records(staging, bindings, source_locale=source_locale, target_locales=available - {source_locale},
                                       dialogue_graphs=value['type_schema'].get('generator') == CLASS_GENERATOR)
    pak.check(records)
    for row in records:
        if row.get('audio'):
            location = catalog.location(row['audio']['depot'])
            pak.check(location)
            row['audio'].update(publisher=stamp, archive=location[0])
    expected = {key: value[key] for key in ('region', 'branch', 'version', 'files', 'sections')}
    if 'publisher_files' in value: expected['publisher_files'] = value['publisher_files']
    observed = _discovery(region)
    if 'publisher_files' not in value: observed = {key: observed[key] for key in expected}
    if 'nte-' + selected_region(tools, 'nte') != region or observed != expected:
        raise PreparationFailure('game_files_changed', 'NTE publisher resources changed during preparation. Retry; the previous completed index is retained.')
    warnings = assets.coverage_warnings(records, publisher=True)
    warnings.extend(f'{count:,} {code} translation entries did not match the selected source revision and were excluded.' for code, count in rejected.items())
    source_count = len(tables[assets.TEXT_LOCALES[source_locale]])
    warnings.extend(f'NTE {code} translations cover {len(rows):,} of {source_count:,} matching text keys in this snapshot.'
                    for code, rows in tables.items() if code != assets.TEXT_LOCALES[source_locale] and len(rows) < source_count)
    missing = [target for target, locale in resolved.items() if locale not in available]
    result = {'format': 2, 'game': 'nte', 'install': None, 'source_mode': 'publisher', 'source_region': region[4:],
            'fingerprint': stamp, 'source_locale': source_locale, 'records': records,
            'missing_translation_locales': missing, 'coverage_warnings': warnings,
            'message': f'{len(records):,} official {source_locale} lines; {sum(bool(r.get("audio")) for r in records):,} original voices'}
    if native_proof is not None:
        result.update(type_schema=native_proof[0], native_schema_validation=native_proof[1])
    return result


@lru_cache(maxsize=2)
def _voices(tools, stamp):
    return Catalog(tools, stamp)


def extract(tools, audio):
    from .nte_assets import _voice_language
    _voice_language(audio)
    catalog = _voices(Path(tools), audio['publisher'])
    value = catalog.location(audio['depot'])
    pak.check(value and value[0] == audio.get('archive'))
    data = catalog.read(audio['depot'])
    pak.check(data[:4] == b'RIFF' and data[8:12] == b'WAVE' and int.from_bytes(data[4:8], 'little') + 8 == len(data))
    return data
