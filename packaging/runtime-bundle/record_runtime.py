"""Observe a complete experimental environment, never approve redistribution.

The supplier archive and every installed wheel payload are compared byte for
byte before PyInstaller runs. No installer, account, game or user profile is read.
"""
import argparse
from importlib import metadata
import json
from pathlib import Path
import sys
import tarfile
import zipfile

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
    return {'xiph-flac': {'build_id': codec.manifest['build_id'],
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
    target = evidence / 'codecs/xiph-flac'
    _no_links(target.absolute())
    target.parent.mkdir(exist_ok=True)
    shutil.copytree(codec_root, target)
    resources = [{'path': path.relative_to(evidence).as_posix(), 'sha256': digest(path), 'version': '1.5.0',
        'source': 'https://github.com/xiph/flac/releases/tag/1.5.0',
        'license_expression': 'GPL-2.0-or-later CLI, BSD library, LGPL support; source kit retained; production/native review pending'}
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
            path = (data_path or Path(distribution.locate_file(name))).resolve()
            if Path(sys.prefix).resolve() not in path.parents or not path.is_file() or path.is_symlink() or path.read_bytes() != package.read(member):
                raise ClosureError('Installed wheel payload differs from archive: ' + info['Name'])


def python_supplier_notice_files(source, pin):
    """Validate retained primary texts, without approving native applicability."""
    from backend.prebuilt_readers import _no_links
    root = source / 'packaging/runtime-bundle/python-notices'
    _no_links(root.absolute())
    provenance = root / 'PROVENANCE.json'
    _no_links(provenance.absolute())
    if not provenance.is_file() or provenance.stat().st_size > 65536:
        raise ClosureError('Retained Python supplier notice provenance is missing or oversized.')
    value = json.loads(provenance.read_text(encoding='utf-8'))
    supplier = {key: pin[key] for key in ('supplier', 'version', 'architecture', 'release', 'source_commit', 'sha256')}
    archive = value.get('archive', {})
    name = f"cpython-{pin['version']}+{pin['release']}-x86_64-pc-windows-msvc-pgo-full.tar.zst"
    url = f"https://github.com/astral-sh/python-build-standalone/releases/download/{pin['release']}/{name.replace('+', '%2B')}"
    if (value.get('schema') != 'proxy-python-supplier-notices-v1' or value.get('supplier') != supplier
            or value.get('native_closure') != 'unverified' or value.get('redistribution_review') != 'pending-exact-output'
            or not isinstance(archive, dict) or archive.get('name') != name or archive.get('url') != url
            or archive.get('github_release_id') != pin['github_release_id']
            or type(archive.get('github_asset_id')) is not int or archive['github_asset_id'] <= 0
            or type(archive.get('bytes')) is not int or not 0 < archive['bytes'] <= 100 * 1024 * 1024
            or not isinstance(archive.get('sha256'), str) or len(archive['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in archive['sha256'])):
        raise ClosureError('Retained Python notices differ from the exact observed supplier identity.')
    files = value.get('files')
    if not isinstance(files, list) or len(files) != 20:
        raise ClosureError('Retain all twenty original supplier notice files.')
    entries, names = [], set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {'path', 'archive_member', 'bytes', 'sha256'}:
            raise ClosureError('Supplier notice attributes are incomplete.')
        name = entry['path']
        if (not isinstance(name, str) or not name.startswith('LICENSE.') or not name.endswith('.txt')
                or Path(name).name != name or '/' in name or '\\' in name or ':' in name
                or name.casefold() in names or entry['archive_member'] != 'python/licenses/' + name
                or type(entry['bytes']) is not int or not 0 < entry['bytes'] <= 256 * 1024):
            raise ClosureError('Supplier notice member identity is invalid or aliased.')
        _no_links((root / name).absolute())
        original = checked_file(root, entry)
        if original.stat().st_size != entry['bytes']:
            raise ClosureError('Retained supplier notice length differs from provenance.')
        names.add(name.casefold()); entries.append(original)
    if {path.name.casefold() for path in root.iterdir()} != names | {'provenance.json'}:
        raise ClosureError('Retained supplier notice directory contains unrecorded files.')
    return [provenance, *entries]


def expected_python_notice_records(source, pin):
    return [{'path': 'licenses/cpython/supplier/' + path.name,
        'sha256': digest(path), 'bytes': path.stat().st_size}
        for path in python_supplier_notice_files(source, pin)]


def collect_python_notices(evidence, source, pin):
    """Copy notice-only delivery into the existing hashed THIRD_PARTY path."""
    import shutil
    from backend.prebuilt_readers import _no_links
    originals = python_supplier_notice_files(source, pin)
    target = evidence / 'licenses/cpython/supplier'
    _no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Never replace an existing evidence set.
    records = []
    for original in originals:
        destination = target / original.name
        shutil.copyfile(original, destination)
        if digest(destination) != digest(original):
            raise ClosureError('Supplier notice changed during evidence delivery.')
        records.append({'path': destination.relative_to(evidence).as_posix(),
            'sha256': digest(destination), 'bytes': destination.stat().st_size})
    return records


def collect_onnx_third_party_notice(evidence, component):
    """Bind the wheel's incorporated notices, which the generic prefix scan misses."""
    import hashlib
    from backend.prebuilt_readers import _no_links
    member = 'onnxruntime/ThirdPartyNotices.txt'
    if normalized(component['name']) != 'onnxruntime' or component['architecture'] != 'win-amd64':
        raise ClosureError('ONNX native notices need the selected Windows x64 component.')
    archive = checked_file(evidence, component['artifact'])
    _no_links(archive.absolute())
    with zipfile.ZipFile(archive) as package:
        info = wheel_metadata(package)
        if (normalized(info['Name']) != 'onnxruntime' or info['Version'] != component['version']
                or package.namelist().count(member) != 1):
            raise ClosureError('ONNX third-party notices are missing, ambiguous or from another wheel.')
        data = package.read(member)
    if not 1 <= len(data) <= 2 * 1024 * 1024:
        raise ClosureError('ONNX third-party notice text is empty or oversized.')
    checksum = hashlib.sha256(data).hexdigest()
    installed = metadata.distribution(component['name'])
    original = Path(installed.locate_file(member)).absolute()
    prefix = Path(sys.prefix).absolute()
    _no_links(original)
    if installed.version != component['version'] or prefix not in original.parents:
        raise ClosureError('Installed ONNX notice differs from the selected build environment.')
    installed_record = {'path': original.relative_to(prefix).as_posix(), 'sha256': checksum}
    if installed_record not in component['installed_files']:
        raise ClosureError('Installed ONNX third-party notice is not bound to its observed wheel bytes.')
    if checked_file(prefix, installed_record).stat().st_size != len(data):
        raise ClosureError('Installed ONNX third-party notice length differs from the wheel.')
    target = evidence / 'licenses/onnxruntime/ThirdPartyNotices.txt'
    _no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as stream:
        stream.write(data)
    return {'path': target.relative_to(evidence).as_posix(), 'sha256': checksum, 'bytes': len(data)}


def _flatbuffers_notice_inputs(evidence, source, component, *, check_installed):
    """Bind the retained source notice to the exact source-identical wheel."""
    import hashlib
    from backend.prebuilt_readers import _no_links
    from backend.runtime_bundle import relative_resource
    root = source / 'packaging/runtime-bundle/flatbuffers-notices'
    provenance = root / 'PROVENANCE.json'
    _no_links(provenance.absolute())
    if not provenance.is_file() or provenance.stat().st_size > 65536:
        raise ClosureError('Retained Flatbuffers source provenance is missing or oversized.')
    value = json.loads(provenance.read_bytes())
    if not isinstance(value, dict):
        raise ClosureError('Retained Flatbuffers source provenance is invalid.')
    wheel, origin, notice = value.get('wheel', {}), value.get('source', {}), value.get('notice', {})
    version = component['version']
    if (value.get('schema') != 'proxy-flatbuffers-source-notices-v1' or value.get('version') != version
            or normalized(component['name']) != 'flatbuffers' or component['architecture'] != 'any'
            or value.get('redistribution_review') != 'pending-exact-output' or value.get('native_closure') != 'unverified'
            or value.get('production_execution_allowed') is not False or value.get('upstream_NOTICE_file_observed') is not False
            or not isinstance(wheel, dict) or wheel.get('sha256') != component['artifact']['sha256']
            or wheel.get('name') != f'flatbuffers-{version}-py2.py3-none-any.whl'
            or not isinstance(origin, dict) or origin.get('repository') != 'https://github.com/google/flatbuffers'
            or origin.get('tag') != 'v' + version or not isinstance(origin.get('commit'), str)
            or len(origin['commit']) != 40 or any(c not in '0123456789abcdef' for c in origin['commit'])
            or origin.get('archive_url') != 'https://codeload.github.com/google/flatbuffers/tar.gz/' + origin['commit']
            or not isinstance(origin.get('archive_sha256'), str) or len(origin['archive_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in origin['archive_sha256'])
            or not isinstance(notice, dict) or set(notice) != {'path', 'source_member', 'bytes', 'sha256'}
            or notice.get('path') != 'LICENSE' or notice.get('source_member') != 'LICENSE'
            or type(notice.get('bytes')) is not int or not 0 < notice['bytes'] <= 256 * 1024):
        raise ClosureError('Retained Flatbuffers notice differs from the exact observed wheel/source identity.')
    license_file = checked_file(root, notice)
    _no_links(license_file.absolute())
    if license_file.stat().st_size != notice['bytes']:
        raise ClosureError('Retained Flatbuffers notice length differs from source provenance.')
    payload = value.get('python_payload')
    if not isinstance(payload, list) or len(payload) != 10:
        raise ClosureError('Retain all ten source-identical Flatbuffers Python member identities.')
    archive = checked_file(evidence, component['artifact'])
    _no_links(archive.absolute())
    if archive.stat().st_size != wheel.get('bytes'):
        raise ClosureError('Flatbuffers wheel length differs from source provenance.')
    installed = metadata.distribution('flatbuffers') if check_installed else None
    if installed is not None and installed.version != version:
        raise ClosureError('Installed Flatbuffers version differs from the observed wheel.')
    seen = set()
    with zipfile.ZipFile(archive) as package:
        info = wheel_metadata(package)
        if normalized(info['Name']) != 'flatbuffers' or info['Version'] != version:
            raise ClosureError('Flatbuffers source notices belong to another wheel identity.')
        for entry in payload:
            if not isinstance(entry, dict) or set(entry) != {'path', 'source_member', 'bytes', 'sha256'}:
                raise ClosureError('Flatbuffers source member attributes are incomplete.')
            name = relative_resource(entry['path'])
            if (not name.startswith('flatbuffers/') or not name.endswith('.py') or name in seen
                    or entry['source_member'] != 'python/' + name or package.namelist().count(name) != 1
                    or type(entry['bytes']) is not int or not 0 < entry['bytes'] <= 1024 * 1024):
                raise ClosureError('Flatbuffers source member identity is missing or aliased.')
            seen.add(name)
            data = package.read(name)
            records = [row for row in component.get('installed_files', [])
                if row['path'] == name or row['path'].endswith('/' + name)]
            if (len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']
                    or len(records) != 1 or records[0]['sha256'] != entry['sha256']):
                raise ClosureError('Flatbuffers source/wheel/observed installed bytes differ.')
            relative_resource(records[0]['path'])
            if installed is not None:
                original = Path(installed.locate_file(name)).absolute()
                _no_links(original)
                prefix = Path(sys.prefix).absolute()
                if (prefix not in original.parents or original.relative_to(prefix).as_posix() != records[0]['path']
                        or checked_file(prefix, records[0]).stat().st_size != entry['bytes']):
                    raise ClosureError('Installed Flatbuffers payload differs from its verified wheel.')
        if seen != {name for name in package.namelist() if name.startswith('flatbuffers/') and name.endswith('.py')}:
            raise ClosureError('Flatbuffers wheel has unbound Python source members.')
    return [license_file, provenance]


def expected_flatbuffers_notice_records(evidence, source, component):
    return [{'path': 'licenses/flatbuffers/source/' + path.name,
        'sha256': digest(path), 'bytes': path.stat().st_size}
        for path in _flatbuffers_notice_inputs(evidence, source, component, check_installed=False)]


def collect_flatbuffers_notices(evidence, source, component):
    import shutil
    from backend.prebuilt_readers import _no_links
    originals = _flatbuffers_notice_inputs(evidence, source, component, check_installed=True)
    target = evidence / 'licenses/flatbuffers/source'
    _no_links(target.absolute())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # Preserve any existing evidence instead of replacing it.
    records = []
    for original in originals:
        destination = target / original.name
        shutil.copyfile(original, destination)
        if digest(destination) != digest(original):
            raise ClosureError('Retained Flatbuffers notice changed during delivery.')
        records.append({'path': destination.relative_to(evidence).as_posix(),
            'sha256': digest(destination), 'bytes': destination.stat().st_size})
    return records


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
    python['licenses'].extend(collect_python_notices(evidence, source, pin))
    python['notice_review'] = 'Exact supplier texts retained; native applicability, ownership and redistribution conditions remain pending'
    onnx = next((item for item in value['components'] if normalized(item['name']) == 'onnxruntime'), None)
    if onnx is None:
        raise ClosureError('The locked ONNX Runtime component is missing.')
    onnx['licenses'].append(collect_onnx_third_party_notice(evidence, onnx))
    flatbuffers = next((item for item in value['components'] if normalized(item['name']) == 'flatbuffers'), None)
    if flatbuffers is None:
        raise ClosureError('The locked Flatbuffers component is missing.')
    flatbuffers['licenses'].extend(collect_flatbuffers_notices(evidence, source, flatbuffers))
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
