"""Observe a complete experimental environment, never approve redistribution.

The supplier archive and every installed wheel payload are compared byte for
byte before PyInstaller runs. No installer, account, game or user profile is read.
"""
import argparse
from importlib import metadata
import importlib.util
import json
import marshal
from pathlib import Path
import sys
import tarfile
import zipfile
from types import CodeType

from closure import ROOT, ClosureError, checked_file, digest, normalized
from record_diagnostic import record, wheel_metadata

RESOURCES = (
    'package.json', 'LICENSE', 'THIRD_PARTY_NOTICES.md',
    'public/mobile-capture/games-data.json',
    'assets/fireredvad/fireredvad_vad.onnx', 'assets/fireredvad/cmvn.ark',
    'assets/fireredvad/LICENSE', 'assets/fireredvad/NOTICE.md', 'assets/fireredvad/PROVENANCE.json',
    'scripts/check-capture-readiness.py', 'scripts/select-game-folders.ps1',
    'scripts/select-export-folder.ps1', 'scripts/endfield-reader-sources.json',
)


def verified_nte(evidence, resources, commit, source):
    """Bind only the owned bridge. An external game chain cannot enter here."""
    from types import SimpleNamespace
    from backend.prebuilt_readers import prebuilt_reader
    entries = {item['path']: item['sha256'] for item in resources}
    def resource(name):
        if name not in entries:
            raise ClosureError('NTE helper is missing from the outer resource inventory.')
        return checked_file(evidence, {'path': name, 'sha256': entries[name]})
    helper = prebuilt_reader('nte', layout=SimpleNamespace(mode='bundle', source_commit=commit,
        resource_root=evidence, resources=entries, resource=resource))
    if helper.manifest['source_inputs'] != {name: digest(source / name) for name in helper.manifest['source_inputs']}:
        raise ClosureError('Owned NTE bridge sources differ from the runtime source commit.')
    return helper


def collect_nte(helper_root, evidence, commit, source):
    import shutil
    from backend.prebuilt_readers import _no_links
    helper_root = helper_root.absolute()
    for path in (helper_root, *helper_root.rglob('*')):
        _no_links(path)
        if not (path.is_file() or path.is_dir()):
            raise ClosureError('Owned helper inputs must be regular files/directories.')
    target = evidence / 'helpers/nte'
    # Check destination ancestry before copytree can traverse an existing
    # helpers junction and write owned bytes outside the private evidence root.
    _no_links(target.absolute())
    target.parent.mkdir(exist_ok=True)
    shutil.copytree(helper_root, target)
    resources = [{'path': path.relative_to(evidence).as_posix(), 'sha256': digest(path), 'version': commit,
        'source': 'https://github.com/Firebird55/Game-immersion-toolkit/tree/' + commit,
        'license_expression': 'Owned bridge and exact Microsoft runtime notices; exact-output review pending'}
        for path in sorted(target.rglob('*')) if path.is_file()]
    helper = verified_nte(evidence, resources, commit, source)
    return resources, {'nte': {'build_id': helper.manifest['build_id'], 'source_identity': helper.source_identity,
        'manifest_sha256': digest(target / 'helper-manifest.json'), 'game_execution_approved': False}}


def verified_codec(evidence, resources, commit, source):
    from types import SimpleNamespace
    from backend.prebuilt_codecs import prebuilt_flac_decoder
    entries = {item['path']: item['sha256'] for item in resources}
    def resource(name):
        if name not in entries:
            raise ClosureError('Codec is missing from the outer resource inventory.')
        return checked_file(evidence, {'path': name, 'sha256': entries[name]})
    codec = prebuilt_flac_decoder(layout=SimpleNamespace(mode='bundle', profile='runtime-experiment',
        source_commit=commit, resource_root=evidence, resources=entries, resource=resource))
    if codec.manifest['source_inputs'] != {name: digest(source / name) for name in codec.manifest['source_inputs']}:
        raise ClosureError('Codec preparation sources differ from the runtime source commit.')
    return codec


def codec_identity(codec):
    return {'ffmpeg-flac': {'build_id': codec.manifest['build_id'],
        'manifest_sha256': digest(codec.executable.parent / 'codec-manifest.json'),
        'artifact_sha256': codec.manifest['archive_sha256'], 'production_execution_allowed': False}}


def collect_codec(codec_root, evidence, commit, source):
    import shutil
    from backend.prebuilt_readers import _no_links
    codec_root = codec_root.absolute()
    for path in (codec_root, *codec_root.rglob('*')):
        _no_links(path)
        if not (path.is_file() or path.is_dir()):
            raise ClosureError('Codec inputs must be regular files/directories.')
    target = evidence / 'codecs/ffmpeg-flac'
    _no_links(target.absolute())
    target.parent.mkdir(exist_ok=True)
    shutil.copytree(codec_root, target)
    resources = [{'path': path.relative_to(evidence).as_posix(), 'sha256': digest(path), 'version': '7.1',
        'source': 'https://pypi.org/project/imageio-ffmpeg/0.6.0/',
        'license_expression': 'Exact upstream notices retained; GPL/source/native review pending'}
        for path in sorted(target.rglob('*')) if path.is_file()]
    codec = verified_codec(evidence, resources, commit, source)
    return resources, codec_identity(codec)


def verify_python(archive, prefix, pin):
    if digest(archive) != pin['sha256']:
        raise ClosureError('Python supplier archive differs from the exact observed pin.')
    files, seen = [], set()
    with tarfile.open(archive) as package:
        for member in package:
            from backend.runtime_bundle import relative_resource
            name = relative_resource(member.name.rstrip('/'))
            if name == 'python' and member.isdir():
                continue
            if name.casefold() in seen or not (member.isfile() or member.isdir()) or not name.startswith('python/'):
                raise ClosureError('Python archive contains aliases, links or unexpected roots.')
            seen.add(name.casefold())
            relative = name[len('python/'):]
            # pip is build-only and is changed when preparing the wheelhouse.
            if not member.isfile() or relative.endswith('.pyc') or relative.startswith('Lib/site-packages/') or relative.startswith('Scripts/'):
                continue
            path = prefix / relative
            import hashlib
            expected = hashlib.file_digest(package.extractfile(member), 'sha256').hexdigest()
            if not path.is_file() or path.is_symlink() or digest(path) != expected:
                raise ClosureError('Provisioned Python differs from the supplier archive: ' + relative)
            files.append({'path': relative, 'sha256': expected})
    if not files or not any(item['path'] == 'python312.dll' for item in files):
        raise ClosureError('Windows Python shared runtime is missing.')
    return files


def verified_recompiled_cache(package, name, installed, distribution):
    """Accept pip's generated bytecode only when it compiles verified source."""
    if installed.suffix != '.pyc' or installed.parent.name != '__pycache__':
        return False
    try:
        source_name = Path(importlib.util.source_from_cache(name)).as_posix()
        source = Path(distribution.locate_file(source_name))
        if (source.is_symlink() or Path(sys.prefix).resolve() not in source.resolve().parents
                or source.read_bytes() != package.read(source_name)):
            return False
        # Only this interpreter's standard cache names and optimization levels
        # may differ. Sourceless/vendor bytecode still requires exact bytes.
        optimization = next((level for level in (0, 1, 2)
            if Path(importlib.util.cache_from_source(str(source), optimization=level or '')) == installed), None)
        if optimization is None:
            return False
        payload = installed.read_bytes()
        if len(payload) < 16 or payload[:4] != importlib.util.MAGIC_NUMBER:
            return False
        code = marshal.loads(payload[16:])
        return isinstance(code, CodeType) and code == compile(
            package.read(source_name), str(source), 'exec', dont_inherit=True, optimize=optimization)
    except (OSError, KeyError, ValueError, EOFError, TypeError):
        return False


def verify_wheel(wheel):
    with zipfile.ZipFile(wheel) as package:
        info = wheel_metadata(package)
        distribution = metadata.distribution(info['Name'])
        seen = set()
        for member in package.infolist():
            from backend.runtime_bundle import relative_resource
            name = relative_resource(member.filename.rstrip('/'))
            if name.casefold() in seen:
                raise ClosureError('Wheel contains aliased or duplicated files.')
            seen.add(name.casefold())
            if member.is_dir():
                continue
            if name.endswith('.dist-info/RECORD'):
                # pip rewrites RECORD to include installed scripts, bytecode
                # and INSTALLER/REQUESTED. It is not executable wheel payload;
                # the recorder separately hashes its actual installed bytes.
                continue
            # Windows entry scripts have installer-rewritten shebangs. They
            # are build-only; no scripts/SDK/compiler enter the frozen tree.
            data_path = None
            if '.data/' in name:
                group, _, rest = name.partition('.data/')
                category, _, tail = rest.partition('/')
                if category == 'scripts':
                    continue
                if category == 'data':
                    # sherpa-onnx-core installs its duplicate command-line DLLs
                    # in prefix/Scripts; these stay build-only, but are verified.
                    relative_resource(tail)
                    data_path = Path(sys.prefix) / tail
                elif category not in {'purelib', 'platlib'}:
                    raise ClosureError('Unreviewed wheel installation scheme: ' + group)
                name = tail
            installed = data_path or Path(distribution.locate_file(name))
            path = installed.resolve()
            reason = None
            if Path(sys.prefix).resolve() not in path.parents:
                reason = 'outside interpreter prefix'
            elif installed.is_symlink():
                reason = 'symbolic link'
            elif not path.is_file():
                reason = 'missing file'
            elif (path.read_bytes() != package.read(member)
                    and not verified_recompiled_cache(package, name, installed, distribution)):
                reason = 'content mismatch'
            if reason:
                # Report only the archive-relative name, never a host profile
                # path. A distribution name alone cannot diagnose native CI.
                raise ClosureError('Installed wheel payload differs from archive: '
                    + info['Name'] + ': ' + member.filename + ' (' + reason + ')')


def observe(evidence, frontend, build_id, source=ROOT, *, nte_helper_root, codec_root):
    import shutil
    pin = json.loads((source / 'packaging/runtime-bundle/python-supplier.json').read_text())
    installed_python = verify_python(evidence / pin['archive'], Path(sys.base_prefix), pin)
    for wheel in sorted((evidence / 'wheelhouse').glob('*.whl')):
        verify_wheel(wheel)
    value = record(evidence, pin['archive'], pin['url'], build_id, source, frontend, metadata_notices=True)
    value['profile'] = 'runtime-experiment'
    for item in value['components']:
        item['review_status'] = 'observed-experiment'
    python = value['components'][0]
    if python['version'] != pin['version']:
        raise ClosureError('Interpreter version differs from the pinned supplier.')
    python['installed_files'] = installed_python
    value['python_supplier'] = pin
    value['runtime_lock_sha256'] = digest(source / 'requirements.lock.txt')
    helpers, value['helpers'] = collect_nte(nte_helper_root, evidence, value['source_commit'], source)
    value['resources'].extend(helpers)
    codecs, value['codecs'] = collect_codec(codec_root, evidence, value['source_commit'], source)
    value['resources'].extend(codecs)
    for name in RESOURCES:
        original = source / name
        destination = evidence / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destination)
        value['resources'].append({'path': name, 'sha256': digest(original), 'version': value['source_commit'],
            'source': 'https://github.com/Firebird55/Game-immersion-toolkit/tree/' + value['source_commit'],
            'license_expression': 'Observed source/model notices; exact-output review pending'})
    model = json.loads((source / 'assets/fireredvad/PROVENANCE.json').read_text())
    for item in model['files']:
        checked_file(source / 'assets/fireredvad', {'path': item['file'], 'sha256': item['sha256']})
    value['status'] = 'Quarantined integrated runtime experiment; rights, Windows 11 and full R19 acceptance remain open'
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--frontend-root', type=Path, required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--nte-helper-root', type=Path, required=True)
    parser.add_argument('--codec-root', type=Path, required=True)
    args = parser.parse_args()
    value = observe(args.evidence.resolve(), args.frontend_root.resolve(), args.build_id,
        nte_helper_root=args.nte_helper_root, codec_root=args.codec_root)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
