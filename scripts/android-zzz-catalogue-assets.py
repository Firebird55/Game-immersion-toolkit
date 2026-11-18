"""Verify and package the exact optional Android ZZZ reader and corresponding source."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links

PIN = 'packaging/android/zzz-catalogue/manifest-pin.json'
NAMESPACE = 'assets/zzz-catalogue/'
SOURCE_BUNDLE = 'sources.bundle'
MANIFEST = 'manifest.json'
HEX = re.compile(r'[0-9a-f]{64}')
LEAF = re.compile(r'[A-Za-z0-9_.-]{1,96}')
MAX_RUNTIME = 128 * 1024
MAX_SOURCE = 64 * 1024**2
MAX_MANIFEST = 16 * 1024
OWNED_SOURCES = {
    'catalogue-bytes.mjs': 'packaging/android/zzz-catalogue/catalogue-bytes.mjs',
    'catalogue-runtime.mjs': 'packaging/android/zzz-catalogue/catalogue-runtime.mjs',
    'catalogue-host.js': 'packaging/android/zzz-catalogue/catalogue-host.js',
    'catalogue-worker.mjs': 'packaging/android/zzz-catalogue/catalogue-worker.mjs',
    **{name: 'scripts/' + name for name in (
        'scene-catalog.mjs', 'comic-links.mjs', 'cinematic-links.mjs', 'zzz-dialogue.mjs',
        'zzz-presentation-config.mjs', 'zzz-cinema-timeline.mjs', 'zzz-publisher-dialogue.mjs',
    )},
}
OWNED_RECIPES = {
    'original-oodle-adapter.mjs': 'packaging/android/publisher-oodle/decoder.mjs',
    'build-ooz-runtime.py': 'scripts/build-ooz-runtime.py',
    'ooz-build.json': 'packaging/zzz-reader/ooz-build.json',
    'production-inputs.json': 'packaging/zzz-reader/production-inputs.json',
    'stage-android-zzz-catalogue.mjs': 'scripts/stage-android-zzz-catalogue.mjs',
    'zzz-android-mhy-source.mjs': 'scripts/zzz-android-mhy-source.mjs',
    'LICENSE': 'LICENSE',
}


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def member(path, limit):
    _no_links(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit, 'Invalid ZZZ catalogue software member')
    with path.open('rb') as source:
        raw = source.read(info.st_size + 1)
    require(len(raw) == info.st_size, 'ZZZ catalogue software changed during validation')
    return raw


def receipts(raw, repository):
    pin = json.loads(member(repository / PIN, MAX_MANIFEST))
    identity = digest(raw)
    require(pin['schema'] == 'toolkit-android-zzz-catalogue-pin-v1' and identity == pin['manifest_sha256'],
            'The ZZZ catalogue software manifest differs from the reviewed pin')
    manifest = json.loads(raw)
    require(manifest['schema'] == 'toolkit-android-zzz-catalogue-assets-v1' and
            len(manifest['modules']) == pin['modules'] and len(manifest['sources']) == pin['sources'],
            'The ZZZ catalogue software manifest has the wrong closure')
    runtime = {**manifest['modules'], 'catalogue-host.js': manifest['host'], 'catalogue-worker.mjs': manifest['worker']}
    source = manifest['sources']
    require(not {MANIFEST, SOURCE_BUNDLE} & runtime.keys(), 'Invalid ZZZ catalogue runtime member')
    for records, limit, total in ((runtime, MAX_RUNTIME, 512 * 1024), (source, MAX_SOURCE, MAX_SOURCE)):
        for name, row in records.items():
            require(bool(LEAF.fullmatch(name)) and name not in {'.', '..'} and type(row['bytes']) is int and
                    0 < row['bytes'] <= limit and bool(HEX.fullmatch(row['sha256'])), 'Invalid ZZZ catalogue member receipt')
        require(sum(row['bytes'] for row in records.values()) <= total, 'ZZZ catalogue file inventory is oversized')
    for records, owned in ((runtime, OWNED_SOURCES), (source, OWNED_RECIPES)):
        for name, path in owned.items():
            check_bytes(member(repository / path, MAX_RUNTIME).replace(b'\r\n', b'\n'), records[name])
    return identity, runtime, source


def check_bytes(raw, row):
    require(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'A ZZZ catalogue software member differs from its pin')
    return raw


def zip_member(archive, name, limit):
    info = archive.getinfo(name)
    require(0 < info.file_size <= limit and not info.is_dir() and
            not stat.S_ISLNK(info.external_attr >> 16), 'Invalid packaged ZZZ catalogue software member')
    with archive.open(info) as source:
        raw = source.read(info.file_size + 1)
    require(len(raw) == info.file_size, 'Truncated packaged ZZZ catalogue software member')
    return raw


def verify_members(names, read, repository=ROOT):
    require(MANIFEST in names, 'The ZZZ catalogue software manifest is missing')
    raw = read(MANIFEST, MAX_MANIFEST)
    identity, runtime, sources = receipts(raw, repository)
    expected = set(runtime) | {MANIFEST, SOURCE_BUNDLE}
    require(len(names) == len(expected) and set(names) == expected, 'Unexpected ZZZ catalogue APK asset namespace')
    for name, row in runtime.items():
        check_bytes(read(name, row['bytes']), row)
    source_bytes = read(SOURCE_BUNDLE, MAX_SOURCE)
    source_identity = digest(source_bytes)
    pin = json.loads(member(repository / PIN, MAX_MANIFEST))
    require(source_identity == pin['corresponding_source_bundle_sha256'], 'The ZZZ corresponding source bundle differs from its pin')
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
        expected = set(sources)
        require(len(archive.namelist()) == len(expected) and set(archive.namelist()) == expected,
                'The corresponding ZZZ catalogue source bundle has the wrong inventory')
        for name, row in sources.items():
            check_bytes(zip_member(archive, name, row['bytes']), row)
    return {'present': True, 'manifest_sha256': identity, 'runtime_files': len(runtime) + 1,
            'source_files': len(sources), 'corresponding_source_bundle_sha256': source_identity}


def verify_apk(archive, repository=ROOT):
    all_names = archive.namelist()
    require(NAMESPACE.rstrip('/') not in all_names, 'The ZZZ catalogue asset namespace is a file')
    names = [name.removeprefix(NAMESPACE) for name in all_names
             if name.startswith(NAMESPACE) and name != NAMESPACE]
    if not names:
        return {'present': False}
    return verify_members(names, lambda name, limit: zip_member(archive, NAMESPACE + name, limit), repository)


def source_files(directory, repository=ROOT):
    raw = member(directory / MANIFEST, MAX_MANIFEST)
    identity, runtime, sources = receipts(raw, repository)
    require({path.name for path in directory.iterdir()} == set(runtime) | {MANIFEST, 'sources'},
            'The staged catalogue software has unexpected files')
    code = {name: check_bytes(member(directory / name, row['bytes']), row) for name, row in runtime.items()}
    source_root = directory / 'sources'
    _no_links(source_root)
    require({path.name for path in source_root.iterdir()} == set(sources), 'The staged catalogue source has unexpected files')
    source = {name: check_bytes(member(source_root / name, row['bytes']), row) for name, row in sources.items()}
    return identity, {**code, MANIFEST: raw}, source


def assemble(directory, output, repository=ROOT):
    directory, output = (Path(path).absolute() for path in (directory, output))
    for path in (directory, output):
        _no_links(path)
    directory, output = directory.resolve(strict=True), output.resolve()
    require(directory != output and directory not in output.parents and output not in directory.parents,
            'Use a separate Android catalogue assembly directory')
    identity, runtime, sources = source_files(directory, repository)
    if output.exists():
        return verify_members([path.name for path in output.iterdir()], lambda name, limit: member(output / name, limit), repository)
    with tempfile.TemporaryDirectory(prefix='zzz-catalogue-', dir=output.parent) as temporary:
        staged = Path(temporary)
        for name, raw in runtime.items():
            (staged / name).write_bytes(raw)
        # AAPT expands a bare tar.gz asset. Preserve the exact archives as
        # ordinary uncompressed members of an opaque corresponding-source bundle.
        with zipfile.ZipFile(staged / SOURCE_BUNDLE, 'x') as archive:
            for name, raw in sorted(sources.items()):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, raw)
        result = verify_members([path.name for path in staged.iterdir()],
                                lambda name, limit: member(staged / name, limit), repository)
        require(result['manifest_sha256'] == identity, 'The assembled ZZZ catalogue identity changed')
        staged.rename(output)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        result = assemble(args.input, args.output)
    else:
        identity, runtime, sources = source_files(args.input)
        result = {'manifest_sha256': identity, 'runtime_files': len(runtime), 'source_files': len(sources)}
    print(json.dumps(result, sort_keys=True))
