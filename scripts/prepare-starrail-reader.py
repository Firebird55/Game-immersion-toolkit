"""Build-host-only preparation of exact frozen GPL/MIT software inputs.

No client files or derived descriptions enter this tree. End-user preparation
uses the prebuilt apphost and never invokes this script or a source compiler.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / 'packaging/starrail-reader/inputs.json'
MAX_ARCHIVE = 32 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def no_links(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Build inputs cannot follow links.')


def archive(data):
    """Check the entire ZIP before selecting any compiler input."""
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        if len(source.infolist()) > 20000:
            raise ValueError('Oversized source inventory.')
        total = 0
        for entry in source.infolist():
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (not path.parts or path.is_absolute() or path.as_posix() != entry.filename.rstrip('/')
                    or '\\' in entry.orig_filename or '\0' in entry.orig_filename or ':' in entry.filename
                    or any(p in {'.', '..'} for p in entry.filename.rstrip('/').split('/'))
                    or stat.S_ISLNK(mode) or entry.flag_bits & 1):
                raise ValueError('Unsafe source archive member.')
            if entry.is_dir():
                continue
            name = path.as_posix()
            total += entry.file_size
            if name.casefold() in result or entry.file_size > MAX_ARCHIVE or total > 128 * 1024 * 1024:
                raise ValueError('Ambiguous or oversized source archive.')
            result[name.casefold()] = (name, source.read(entry))
    return dict(result.values())


def acquire(cache, pin, download):
    path = cache / pin['artifact']
    no_links(path)
    if not path.exists():
        if not download:
            raise ValueError('A pinned build input is missing.')
        pending = path.with_suffix(path.suffix + '.pending')
        no_links(pending)
        with urllib.request.urlopen(pin['source'], timeout=90) as response, pending.open('xb') as target:
            total = 0
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE:
                    raise ValueError('Oversized build input.')
                target.write(block)
        pending.replace(path)
    if not path.is_file() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('Invalid build input.')
    data = path.read_bytes()
    if digest(data) != pin['sha256']:
        raise ValueError('Pinned source digest mismatch.')
    return data


def prepare(cache, output, *, download=False, pins=None):
    pins = json.loads(PINS.read_text()) if pins is None else pins
    cache, output = Path(cache).absolute(), Path(output).absolute()
    no_links(cache); no_links(output)
    if output.exists():
        raise ValueError('Choose a new source preparation directory.')
    cache.mkdir(parents=True, exist_ok=True)
    raw = {name: acquire(cache, pin, download) for name, pin in (
        ('metadata', pins['metadata']), ('decoder', pins['decoder']), ('package', pins['decoder']['package']))}
    metadata, decoder, package = (archive(raw[key]) for key in ('metadata', 'decoder', 'package'))
    prefix = 'HSRGlobalMetadata-' + pins['metadata']['revision'] + '/'
    # The compile allowlist excludes dummy assembly export, its embedded binary
    # and Mono.Cecil. Every selected source is individually pinned as well.
    selected = {}
    for name, expected in pins['metadata']['files'].items():
        path = prefix + 'HSRGlobalMetadata/' + name
        data = metadata[path]
        if digest(data) != expected:
            raise ValueError('A selected compiler input changed.')
        selected['source/' + name] = data
    license_data = metadata[prefix + 'LICENSE']
    if digest(license_data) != pins['metadata']['license_sha256']:
        raise ValueError('GPL license changed.')
    dependency = pins['decoder']['package']
    if base64.b64encode(hashlib.sha512(raw['package']).digest()).decode() != dependency['sha512_base64']:
        raise ValueError('Decoder package digest mismatch.')
    dll, mit = package[dependency['dll_member']], package[dependency['license_member']]
    if digest(dll) != dependency['dll_sha256'] or digest(mit) != dependency['license_sha256']:
        raise ValueError('Decoder assembly or license changed.')
    # Preserve exact corresponding source, excluding uncompiled dummy assembly
    # export and its embedded DLL. The whole authenticated upstream archive is
    # retained privately for build replay, never copied into the distributable.
    decoder_license = next((data for name, data in decoder.items()
                            if name.endswith('/LICENSE.txt') and digest(data) == digest(mit)), None)
    if decoder_license is None:
        raise ValueError('Decoder source license does not match its binary package.')
    corresponding = io.BytesIO()
    with zipfile.ZipFile(corresponding, 'w', compression=zipfile.ZIP_STORED) as source:
        source.writestr(zipfile.ZipInfo('LICENSE'), license_data)
        for name in sorted(pins['metadata']['files']):
            source.writestr(zipfile.ZipInfo('HSRGlobalMetadata/' + name), selected['source/' + name])
    selected.update({'Iced.dll': dll, 'notices/HSRGlobalMetadata-LICENSE.txt': license_data,
                     'notices/Iced-LICENSE.txt': mit,
                     'iced.1.21.0.nupkg': raw['package'],
                     'build-inputs/hsr-metadata-source.zip': raw['metadata'],
                     'corresponding-source/hsr-metadata-source.zip': corresponding.getvalue(),
                     'corresponding-source/iced-source.zip': raw['decoder']})
    output.mkdir()
    for name, data in selected.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    proof = {'schema': 'proxy-starrail-prepared-software-v1',
             'pins_sha256': digest(PINS.read_bytes()),
             'files': {name: digest(data) for name, data in sorted(selected.items())}}
    (output / 'prepared-software.json').write_text(json.dumps(proof, sort_keys=True, indent=2) + '\n')
    return proof


def verify(output):
    output = Path(output).absolute(); no_links(output)
    proof = json.loads((output / 'prepared-software.json').read_text())
    if proof.get('schema') != 'proxy-starrail-prepared-software-v1' or proof.get('pins_sha256') != digest(PINS.read_bytes()):
        raise ValueError('Source preparation does not match the build policy.')
    # Replay preparation from the retained authenticated archives to derive the
    # complete expected inventory; a caller-edited receipt is never authority.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='verify-starrail-', dir=output.parent) as temporary:
        cache = Path(temporary) / 'cache'; cache.mkdir()
        pins = json.loads(PINS.read_text())
        shutil.copyfile(output / 'build-inputs/hsr-metadata-source.zip', cache / pins['metadata']['artifact'])
        shutil.copyfile(output / 'corresponding-source/iced-source.zip', cache / pins['decoder']['artifact'])
        # A package is retained for binary provenance and offline source replay.
        shutil.copyfile(output / 'iced.1.21.0.nupkg', cache / pins['decoder']['package']['artifact'])
        expected = prepare(cache, Path(temporary) / 'expected')
    files = {}
    for path in output.rglob('*'):
        no_links(path)
        if path.is_file() and path.relative_to(output).as_posix() != 'prepared-software.json':
            files[path.relative_to(output).as_posix()] = digest(path.read_bytes())
    if files != expected['files'] or proof != expected:
        raise ValueError('Prepared source inventory changed.')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    elif args.cache:
        prepare(args.cache, args.output, download=args.download)
    else:
        parser.error('--cache is required for preparation')
