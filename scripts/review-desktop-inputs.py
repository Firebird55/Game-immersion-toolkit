"""Inspect actual desktop supplier bytes and report exact acceptance blockers.

This command never edits a runtime, installs dependencies, downloads artifacts,
or accepts a declaration of approval. Evidence paths are kept out of its public
report. Source-built outputs are distinguished from byte-identical supplier
outputs; native execution remains the separate target acceptance probe.
"""
from __future__ import annotations

import argparse
import base64
import csv
from email.parser import BytesParser
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
from types import SimpleNamespace
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
from backend.runtime_bundle import relative_resource
from backend.runtime_payload import digest, no_links, validate
from backend.desktop_frontend import FrontendBuild, FrontendError
from python_supplier import archive_plan, mutable_build_file, PIN_FILES

CHECKS = ('python_supplier', 'exact_wheels', 'native_inputs', 'complete_notices',
          'corresponding_sources', 'frontend_licenses')
JSON_LIMIT = 32 * 1024 * 1024
MEMBER_LIMIT = 100_000
NATIVE_SUFFIX = re.compile(r'(?:\.dll|\.pyd|\.exe|\.dylib|\.so(?:\.\d+)*)$', re.I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    no_links(path)
    if not path.is_file() or path.stat().st_size > JSON_LIMIT:
        raise ValueError('Evidence must be a bounded regular JSON file.')
    return json.loads(path.read_text(encoding='utf-8'))


def inventory_digest(receipt):
    return sha(json.dumps({key: receipt[key] for key in ('files', 'directories')},
                          sort_keys=True, separators=(',', ':')).encode())


def source_matches(data, expected, name):
    if sha(data) == expected:
        return True
    # Git's text checkout conversion is not a source modification. This
    # equivalence applies only to the Git checkout observation; supplier
    # archives and actual delivered notices are checked byte-for-byte later.
    if b'\0' not in data:
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            return False
        return sha(data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')) == expected
    return False


class Snapshot:
    def __init__(self, root, commit, names):
        self.files = {}
        if not re.fullmatch('[a-f0-9]{40}', commit):
            raise ValueError('Source review requires an exact commit.')
        names = sorted(set(relative_resource(name) for name in names))
        result = subprocess.run(['git', 'cat-file', '--batch'], cwd=root,
            input=''.join(commit + ':' + name + '\n' for name in names).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        stream = io.BytesIO(result.stdout)
        for name in names:
            header = stream.readline().decode().strip().split()
            if len(header) == 2 and header[-1] == 'missing':
                continue
            if len(header) != 3 or header[1] != 'blob':
                raise ValueError('Source evidence is not a regular Git blob: ' + name)
            size = int(header[2])
            if size > 128 * 1024 * 1024:
                raise ValueError('Source evidence is oversized: ' + name)
            data = stream.read(size)
            if len(data) != size or stream.read(1) != b'\n':
                raise ValueError('Truncated source evidence.')
            self.files[name] = data


def notice_member(name):
    path = PurePosixPath(name)
    return (any(part.lower() in {'licenses', 'licences'} for part in path.parts)
            and path.suffix.lower() in {'', '.txt', '.md', '.rst', '.html', '.license'}
        or path.name.lower().startswith(('license', 'licence', 'notice', 'copying', 'copyright'))
        or path.name.lower() in {'thirdpartynotices.txt', 'third_party_notices.txt'})


def wheel_evidence(path):
    """Verify RECORD against each actual member, including full native notices."""
    no_links(path)
    hashes, notices = {}, {}
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MEMBER_LIMIT or sum(m.file_size for m in members) > 2 * 1024**3:
            raise ValueError('Wheel inventory exceeds review limits.')
        names = [relative_resource(m.filename.rstrip('/')) for m in members]
        if len({name.casefold() for name in names}) != len(names):
            raise ValueError('Wheel contains duplicate or aliased paths.')
        metadata_names = [name for name in names if name.count('/') == 1 and name.endswith('.dist-info/METADATA')]
        record_names = [name for name in names if name.count('/') == 1 and name.endswith('.dist-info/RECORD')]
        if len(metadata_names) != 1 or len(record_names) != 1:
            raise ValueError('Wheel needs exactly one METADATA and RECORD.')
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        rows = list(csv.reader(io.StringIO(archive.read(record_names[0]).decode())))
        records = {}
        for row in rows:
            if len(row) != 3 or row[0] in records:
                raise ValueError('Invalid or duplicated wheel RECORD.')
            records[row[0]] = row[1:]
        expected = {m.filename for m in members if not m.is_dir()}
        # Detached RECORD signatures are allowed to be absent from RECORD.
        if set(records) != expected - {record_names[0] + '.jws', record_names[0] + '.p7s'}:
            raise ValueError('Wheel RECORD is not a closed payload inventory.')
        for member in members:
            if member.is_dir():
                continue
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Wheel contains a symbolic link.')
            data = archive.read(member)
            name = member.filename
            hashes[name] = sha(data)
            if name != record_names[0] and name in records:
                encoded, size = records[name]
                if '=' not in encoded or int(size) != len(data):
                    raise ValueError('Incomplete wheel RECORD member: ' + name)
                algorithm, expected_digest = encoded.split('=', 1)
                if algorithm not in {'sha256', 'sha384', 'sha512'} or base64.urlsafe_b64encode(
                        hashlib.new(algorithm, data).digest()).decode().rstrip('=') != expected_digest:
                    raise ValueError('Wheel RECORD digest differs: ' + name)
            if notice_member(name):
                notices[name] = hashes[name]
    return {'name': metadata['Name'], 'version': metadata['Version'], 'sha256': digest(path),
            'files': hashes, 'notices': notices}


def normalized(name):
    return re.sub('[-_.]+', '-', name).lower()


class Review:
    def __init__(self, root, receipt, target):
        self.root, self.receipt, self.target = root, receipt, target
        self.checks = {name: {'evidence': [], 'blockers': []} for name in CHECKS}
        self.inventory = {item['path']: item for item in receipt['files']}
        self.origins = {}
        self.wheels = {}
        self.native_files = []

    def block(self, check, code, detail, paths=()):
        item = {'code': code, 'detail': detail}
        if paths:
            item['files'] = sorted(paths)
        self.checks[check]['blockers'].append(item)

    def evidence(self, check, **value):
        self.checks[check]['evidence'].append(value)

    def origin(self, file_sha, supplier):
        self.origins.setdefault(file_sha, set()).add(supplier)

    def has_hash(self, value, prefix=''):
        return any(item['sha256'] == value and not item.get('link') and name.startswith(prefix)
                   for name, item in self.inventory.items())

    def python(self, archive, pin):
        actual = self.receipt.get('python_supplier') or {}
        if any(actual.get(key) != pin.get(key) for key in ('version', 'archive', 'sha256', 'source_commit')):
            raise ValueError('Recorded Python supplier differs from the independently pinned input.')
        entries = archive_plan(archive, pin)
        expected = []
        with tarfile.open(archive) as source:
            for name, member in entries.items():
                relative = name[len('python/'):]
                if member.isdir():
                    continue
                if member.issym():
                    item = {'path': relative, 'link': member.linkname, 'sha256': sha(member.linkname.encode())}
                else:
                    value = hashlib.file_digest(source.extractfile(member), 'sha256').hexdigest()
                    item = {'path': relative, 'sha256': value}
                    self.origin(value, 'CPython supplier: ' + relative)
                if not mutable_build_file(relative):
                    expected.append(item)
        recorded = actual.get('installed_files')
        if not isinstance(recorded, list) or sorted(recorded, key=lambda x:x['path']) != sorted(expected, key=lambda x:x['path']):
            self.block('python_supplier', 'python-installed-inputs', 'Recorded installed Python files differ from the pinned supplier archive.')
        executable = pin.get('executable', 'python.exe')
        expected_exe = next((x['sha256'] for x in expected if x['path'] == executable), None)
        if expected_exe != self.receipt.get('python_executable_sha256'):
            self.block('python_supplier', 'python-build-executable', 'The build interpreter hash does not match the actual supplier executable.')
        libraries = [name for name in self.inventory if re.search(r'(?:python312\.dll|libpython3\.12[^/]*|Python)$', name)]
        if not libraries or any(self.inventory[name]['sha256'] not in self.origins for name in libraries):
            self.block('python_supplier', 'python-frozen-library', 'Frozen Python library bytes need supplier or recorded native post-processing verification.', libraries)
        license_hashes = [x['sha256'] for x in expected if x['path'] in {'LICENSE', 'LICENSE.txt', 'lib/python3.12/LICENSE.txt'}]
        if not license_hashes or not any(self.has_hash(h, 'THIRD_PARTY/') for h in license_hashes):
            self.block('complete_notices', 'python-license', 'The full exact Python supplier license is not retained.')
        self.evidence('python_supplier', archive=pin['archive'], archive_sha256=digest(archive), verified_installed_files=len(expected), frozen_libraries=libraries)

    def wheelhouse(self, directory):
        no_links(directory)
        if not directory.is_dir() or not self.receipt.get('components'):
            raise ValueError('Wheel review requires the observed component list and artifact directory.')
        available = {}
        for path in directory.glob('*.whl'):
            available[digest(path)] = path
        for component in self.receipt['components']:
            name = component['name']
            path = available.get(component.get('artifact_sha256'))
            if path is None:
                self.block('exact_wheels', 'wheel-missing', 'The exact recorded wheel artifact is missing: ' + name)
                continue
            value = wheel_evidence(path)
            if normalized(value['name']) != normalized(name) or value['version'] != component['version']:
                raise ValueError('Wheel metadata differs from the recorded input: ' + name)
            self.wheels[normalized(name)] = value
            for member, value_sha in value['files'].items():
                self.origin(value_sha, name + '==' + value['version'] + ': ' + member)
            missing = [member for member, value_sha in value['notices'].items()
                       if not self.has_hash(value_sha, 'THIRD_PARTY/' + name + '/')]
            if missing:
                self.block('complete_notices', 'wheel-notices', 'Full exact wheel notices are missing: ' + name, missing)
            if not value['notices'] and normalized(name) not in {'rapidocr-onnxruntime', 'sherpa-onnx-core', 'flatbuffers', 'oneocr'}:
                self.block('complete_notices', 'wheel-no-grant', 'Wheel has no full primary license evidence; an independently pinned source notice is needed: ' + name)
            self.evidence('exact_wheels', name=name, version=value['version'], archive_sha256=value['sha256'], verified_members=len(value['files']))

    def locked_components(self, snapshot):
        from packaging.markers import default_environment
        from packaging.requirements import Requirement
        system, machine = {'windows-x64': ('Windows', 'AMD64'), 'linux-x64': ('Linux', 'x86_64'),
                           'macos-arm64': ('Darwin', 'arm64')}[self.target]
        env = {**default_environment(), 'sys_platform': {'Windows': 'win32', 'Linux': 'linux', 'Darwin': 'darwin'}[system],
            'os_name': 'nt' if system == 'Windows' else 'posix', 'platform_system': system,
            'platform_machine': machine, 'python_version': '3.12', 'python_full_version': '3.12.16',
            'implementation_name': 'cpython', 'implementation_version': '3.12.16', 'extra': ''}
        expected = {}
        for name in ('requirements.lock.txt', 'packaging/desktop/build-requirements.lock.txt'):
            for line in snapshot.files[name].decode().splitlines():
                if not line.strip() or line.startswith('#'):
                    continue
                item = Requirement(line)
                if item.marker and not item.marker.evaluate(env):
                    continue
                pins = list(item.specifier)
                if len(pins) != 1 or pins[0].operator != '==' or '*' in pins[0].version:
                    raise ValueError('Runtime dependencies must use exact version pins.')
                expected[normalized(item.name)] = pins[0].version
        actual = {normalized(item['name']): item['version'] for item in self.receipt['components']}
        if actual != expected or len(actual) != len(self.receipt['components']):
            raise ValueError('Observed wheel component inventory differs from the target source locks.')
        self.evidence('exact_wheels', locked_target_components=len(expected))

    def native_archives(self, archives, trusted_hashes):
        for path in archives:
            no_links(path)
            value_sha = digest(path)
            with path.open('rb') as stream:
                sha512_bytes = hashlib.file_digest(stream, 'sha512').digest()
            if not {value_sha, sha512_bytes.hex(), base64.b64encode(sha512_bytes).decode()} & trusted_hashes:
                raise ValueError('Additional native archive is not pinned by the recorded source.')
            size = 0
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as source:
                    for count, member in enumerate(source.infolist(), 1):
                        if member.is_dir():
                            continue
                        relative_resource(member.filename)
                        size += member.file_size
                        if count > MEMBER_LIMIT or size > 2*1024**3 or member.file_size > 512*1024**2:
                            raise ValueError('Native archive exceeds review limits.')
                        self.origin(sha(source.read(member)), 'Supplier archive ' + value_sha + ': ' + member.filename)
            else:
                with tarfile.open(path) as source:
                    for count, member in enumerate(source, 1):
                        if not member.isfile():
                            continue
                        relative_resource(member.name)
                        size += member.size
                        if count > MEMBER_LIMIT or size > 2*1024**3 or member.size > 512*1024**2:
                            raise ValueError('Native archive exceeds review limits.')
                        self.origin(hashlib.file_digest(source.extractfile(member), 'sha256').hexdigest(), 'Supplier archive ' + value_sha + ': ' + member.name)
            self.evidence('native_inputs', supplier_archive_sha256=value_sha, inspected_bytes=size)

    def helpers(self, snapshot):
        """Verify the actual owned reader and pinned unmodified managed supplier."""
        prefix = '_internal/helpers/nte/'
        if prefix + 'helper-manifest.json' not in self.inventory:
            return
        from backend.prebuilt_readers import prebuilt_reader
        from backend.nte_toolchain import dependencies
        resources = {name[len('_internal/'):]: item['sha256'] for name, item in self.inventory.items()
                     if name.startswith('_internal/')}
        layout = SimpleNamespace(mode='bundle', resource_root=self.root / '_internal', resources=resources,
            source_commit=self.receipt['source_commit'], resource=lambda name: self.root / '_internal' / relative_resource(name))
        helper = prebuilt_reader('nte', layout=layout)
        for name, value in helper.manifest['source_inputs'].items():
            if name not in snapshot.files or not source_matches(snapshot.files[name], value, name):
                raise ValueError('Owned reader source differs from the exact candidate commit: ' + name)
        dependencies(layout=layout)
        for name in (helper.executable.name, 'NteReader.dll'):
            self.origin(self.inventory[prefix + name]['sha256'], 'Owned .NET reader; exact source/build receipt verified')
        spec_path = 'packaging/game-readers/managed-components.json'
        spec = json.loads(snapshot.files[spec_path])
        delivered = read_json(self.root / '_internal/toolchains/nte/notices/MANAGED-COMPONENTS.json')
        if delivered != spec:
            raise ValueError('Embedded managed dependency inventory differs from the pinned source.')
        assembly = self.inventory['_internal/toolchains/nte/UEExtractor.dll']
        if assembly['sha256'] != spec['supplier_sha256']:
            raise ValueError('Managed supplier assembly differs from its pinned inspected identity.')
        self.origin(assembly['sha256'], 'Pinned UEExtractor 1.0.8.7; 30 embedded assembly identities inspected')
        for component in spec['components']:
            for index, notice in enumerate(component['notices'], 1):
                name = f'_internal/toolchains/nte/notices/{component["name"]}-{index:02d}.txt'
                if self.inventory.get(name, {}).get('sha256') != notice['sha256']:
                    self.block('complete_notices', 'managed-notice', 'Full pinned embedded dependency notice is missing.', [name])
        self.evidence('native_inputs', helper_manifest_sha256=digest(helper.executable.parent / 'helper-manifest.json'),
                      managed_supplier_sha256=spec['supplier_sha256'])
        self.evidence('corresponding_sources', managed_components=len(spec['components']),
            basis='Unmodified permissive suppliers, exact assembly hashes and complete retained notices; source references are not claims of reproducible builds.')

    def resources(self, snapshot):
        for manifest in self.receipt.get('native_resources', []):
            files = manifest.get('files', [])
            if not files:
                raise ValueError('Empty native resource receipt.')
            for entry in files:
                name = '_internal/' + relative_resource(entry['path'])
                actual = self.inventory.get(name)
                if not actual or any(actual.get(k) != entry.get(k) for k in ('sha256', 'bytes')):
                    raise ValueError('Native resource receipt differs from delivered bytes: ' + name)
            for name, expected in manifest.get('source_inputs', {}).items():
                if name not in snapshot.files or not source_matches(snapshot.files[name], expected, name):
                    self.block('native_inputs', 'native-owned-source', 'Owned helper source differs from the candidate source commit.', [name])
            recipe_sha = manifest.get('build_recipe_sha256')
            if recipe_sha:
                recipes = [item for item in files if item['sha256'] == recipe_sha and item['path'].endswith('.py')]
                matched = any(any(source_matches(data, recipe_sha, name) for name, data in snapshot.files.items()
                                  if name.endswith('/' + PurePosixPath(item['path']).name)) for item in recipes)
                components = manifest.get('components', [])
                pinned = json.loads(snapshot.files['packaging/codecs/audio-runtime.json'])
                if (not isinstance(components, list) or {c.get('name') for c in components} - {'lame', 'ffmpeg', 'vgmstream'}
                        or not {'lame', 'ffmpeg'} <= {c.get('name') for c in components}
                        or any(any(c.get(key) != value for key, value in pinned[c['name']].items()) for c in components)):
                    raise ValueError('Codec source build inputs differ from the exact owned source pins.')
                archive_pins = [c for c in components if isinstance(c, dict) and c.get('archive') and c.get('sha256')] if isinstance(components, list) else []
                archive_pins += [pin for c in list(archive_pins) for pin in c.get('dependency_sources', [])]
                missing = [c['archive'] for c in archive_pins if not self.has_hash(c['sha256'], '_internal/codecs/')]
                if matched and archive_pins and not missing:
                    if self.target != 'windows-x64':
                        adapter_name = '_internal/codecs/audio/sources/audio_runtime_posix.py'
                        adapter = self.inventory.get(adapter_name, {})
                        if not source_matches(snapshot.files['scripts/audio_runtime_posix.py'], adapter.get('sha256'), adapter_name):
                            raise ValueError('Native codec adapter differs from the exact owned source.')
                    # This is a known first-party source build, not a claim that
                    # its binary is identical to some prebuilt supplier file.
                    for item in files:
                        # The Windows vgmstream CLI/DLLs are upstream prebuilt
                        # artifacts. They must match the pinned supplier ZIP;
                        # the adjacent FFmpeg recipe cannot certify them.
                        filename = PurePosixPath(item['path']).name
                        if filename in {'ffmpeg', 'ffmpeg.exe'} or (self.target != 'windows-x64' and filename == 'vgmstream-cli'):
                            self.origin(item['sha256'], 'Owned source-build recipe ' + recipe_sha)
                    self.evidence('native_inputs', source_build_recipe_sha256=recipe_sha, retained_source_archives=len(archive_pins))
                    self.evidence('corresponding_sources', source_build_recipe_sha256=recipe_sha,
                        source_archive_sha256=[c['sha256'] for c in archive_pins])
                else:
                    self.block('native_inputs', 'native-source-build', 'Source-built native output needs its actual pinned sources and matching owned recipe.', missing)
            self.evidence('native_inputs', resource_files_verified=len(files))

    def native_inventory(self):
        owned = {'GameImmersionToolkit.exe', 'GameImmersionToolkit', 'asr/GameImmersionToolkitAsr.exe', 'asr/GameImmersionToolkitAsr'}
        missing = []
        for name, entry in self.inventory.items():
            if entry.get('link'):
                continue
            path = self.root / name
            with path.open('rb') as stream:
                magic = stream.read(4)
            if not (magic[:2] == b'MZ' or magic in {b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe'}):
                continue
            suppliers = sorted(self.origins.get(entry['sha256'], []))
            if name in owned:
                suppliers = ['Owned PyInstaller output; source/input receipt verified, not independently reproduced']
            self.native_files.append({'path': name, 'sha256': entry['sha256'], 'origins': suppliers})
            if not suppliers:
                missing.append(name)
        if missing:
            self.block('native_inputs', 'unmapped-native-bytes', 'Native binaries do not match a verified supplier artifact or a verified source-build input. Supply the pinned native archive or native post-processing evidence.', missing)

    def collection(self, pins, kind, selected):
        inspector = load_script('build-native-notices.py' if kind == 'native' else 'build-qt-resources.py')
        for pin in pins['components']:
            if pin['name'] not in selected:
                continue
            prefix = f'_internal/third-party/{kind}/{pin["name"]}/'
            name = prefix + pin['archive']
            item = self.inventory.get(name)
            if not item or item['sha256'] != pin['sha256']:
                self.block('corresponding_sources', 'source-archive-missing', 'Exact pinned source input is not shipped: ' + pin['name'], [name])
                self.block('complete_notices', 'source-notices-missing', 'Source-only full notices are not retained: ' + pin['name'], [prefix + 'notices/'])
                continue
            archive = self.root / name
            if kind == 'native':
                records = inspector.notices(archive, {**pin, 'required_notices': pin.get('required_notices', [])})
            else:
                records = inspector.notices(archive, pin['archive'].removesuffix('.tar.xz'), pin.get('required_notices'))
            index_path = self.root / prefix / 'notices/index.json'
            index = read_json(index_path) if index_path.is_file() else {}
            missing = []
            for source_path, data in records:
                filename = sha(source_path.encode())[:16] + '-' + PurePosixPath(source_path).name
                expected = {'source_path': source_path, 'sha256': sha(data)}
                delivered = self.inventory.get(prefix + 'notices/' + filename)
                if index.get(filename) != expected or not delivered or delivered['sha256'] != expected['sha256']:
                    missing.append(source_path)
            if missing:
                self.block('complete_notices', 'source-notice-bytes', 'Retained notices differ from their actual source archive: ' + pin['name'], missing)
            self.evidence('corresponding_sources', component=pin['name'], archive_sha256=pin['sha256'], source_url=pin['url'], full_notice_members=len(records))

    def sources(self, policy_root):
        native_pins = read_json(policy_root / 'packaging/desktop/native-notices.json')
        qt_pins = read_json(policy_root / 'packaging/desktop/qt-sources.json')
        names = set(self.wheels)
        for name, version in native_pins['distributions'].items():
            if name in self.wheels and self.wheels[name]['version'] != version:
                raise ValueError('Source-notice adapter version differs from the selected wheel: ' + name)
        selected = set()
        for name in ('flatbuffers', 'oneocr'):
            if name in names:
                pin = next(item for item in native_pins['components'] if item['name'] == name)
                if self.wheels[name]['version'] != pin['version']:
                    raise ValueError('Supplemental full license differs from selected package version: ' + name)
                selected.add(name)
        if 'rapidocr-onnxruntime' in names:
            selected.update({'rapidocr', 'paddleocr-model-license'})
            for item in native_pins['ocr_models']['files']:
                if not self.has_hash(item['sha256']):
                    self.block('complete_notices', 'ocr-model-identity', 'The model differs from the source/license binding.', [item['installed_path']])
        if 'sherpa-onnx-core' in names:
            selected.update(pin['name'] for pin in native_pins['components'] if pin['name'] not in {'rapidocr', 'paddleocr-model-license', 'geos', 'mesa-qt', 'llvm-mesa', 'flatbuffers', 'oneocr'})
        if 'shapely' in names:
            selected.add('geos')
        mesa = [name for name in self.inventory if name.lower().endswith('/opengl32sw.dll')]
        if mesa:
            selected.update({'mesa-qt', 'llvm-mesa'})
            self.block('corresponding_sources', 'mesa-supplier-build', 'Selected Qt software renderer needs supplier patch/build correspondence; upstream Mesa/LLVM source versions alone do not prove the supplier build. Remove the optional renderer with native raster-UI validation, or retain the exact supplier build source.', mesa)
        self.collection(native_pins, 'native', selected)
        if 'pyside6-essentials' in names:
            qt = {'pyside-setup', 'qtbase', 'qtsvg', 'qtimageformats'}
            if any(name.endswith('.qm') for name in self.inventory):
                qt.add('qttranslations')
            if any('wayland' in name.lower() for name in self.inventory):
                qt.add('qtwayland')
            if mesa:
                qt.add('qtdoc')
            self.collection(qt_pins, 'qt', qt)

    def frontend(self, source_root, node):
        frontend = FrontendBuild(self.root / '_internal/desktop')
        platform, arch = {'windows-x64': ('win32', 'x64'), 'linux-x64': ('linux', 'x64'),
                          'macos-arm64': ('darwin', 'arm64'), 'macos-x64': ('darwin', 'x64')}[self.target]
        code = "import {dependencyNoticeAudit} from './scripts/dependency-notices.mjs'; console.log(JSON.stringify(dependencyNoticeAudit({root:process.argv[1],platform:process.argv[2],arch:process.argv[3]})));"
        result = subprocess.run([node, '--input-type=module', '-e', code, str(source_root), platform, arch],
            cwd=source_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        audit = json.loads(result.stdout)
        if audit['lock_sha256'] != frontend.value['lock_sha256']:
            raise ValueError('Installed frontend notice closure uses a different package lock.')
        text = (frontend.root / 'notices/THIRD_PARTY_LICENSES.txt').read_text(encoding='utf-8')
        missing = [item['package'] + ' @ ' + item['version'] + ': ' + item['file']
            for item in audit['records'] if (item['package'] + ' @ ' + item['version'] not in text or item['text'] not in text)]
        if missing:
            self.block('frontend_licenses', 'frontend-notice-text', 'Full production dependency notices are missing from the actual frontend payload.', missing)
        for item in audit['omissions']:
            self.block('frontend_licenses', 'frontend-production-gap', item['reason'], [item['package']])
        font = source_root / 'styles/GEIST-OFL.txt'
        if (frontend.root / 'notices/GEIST-OFL.txt').read_bytes() != font.read_bytes():
            self.block('frontend_licenses', 'font-license', 'Retained font license differs from the pinned frontend source.')
        self.evidence('frontend_licenses', lock_sha256=audit['lock_sha256'], full_notice_records=len(audit['records']),
                      exclusions=audit['excluded'], delivered_notice_sha256=digest(frontend.root / 'notices/THIRD_PARTY_LICENSES.txt'))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix('.py').replace('-', '_'), ROOT / 'scripts' / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_observation(receipt, observed, snapshot):
    if observed.get('schema') != 'proxy-desktop-observed-build-v1':
        raise ValueError('Expected the actual desktop input observation.')
    for key in ('source_commit', 'build_id', 'version', 'profile', 'python_supplier', 'components', 'native_resources', 'python_executable_sha256'):
        if observed.get(key) != receipt.get(key):
            raise ValueError('Observed input identity differs from the candidate receipt: ' + key)
    inputs = observed.get('source_inputs')
    if not isinstance(inputs, dict) or not inputs or sha(json.dumps(inputs, sort_keys=True).encode()) != receipt['source_inputs_sha256']:
        raise ValueError('Observed source fingerprint differs from the receipt.')
    return [name for name, expected in inputs.items()
            if name not in snapshot.files or not source_matches(snapshot.files[name], expected, name)]


def review(args):
    receipt = read_json(args.provenance)
    validate(args.runtime_root, receipt, args.target, candidate=True)
    observed = read_json(args.observed_inputs)
    extra = ['packaging/runtime-bundle/' + PIN_FILES[args.target], 'backend/node_tools.py', 'scripts/build-node-toolchain.py',
             'packaging/codecs/audio-runtime.json', 'packaging/game-readers/managed-components.json', 'backend/prebuilt_readers.py']
    source_names = set(observed.get('source_inputs', {})) | set(extra)
    for manifest in receipt.get('native_resources', []):
        source_names.update(manifest.get('source_inputs', {}))
    snapshot = Snapshot(args.source_root, receipt['source_commit'], source_names)
    mismatches = verify_observation(receipt, observed, snapshot)
    result = Review(args.runtime_root, receipt, args.target)
    if mismatches:
        result.block('native_inputs', 'source-observation-mismatch',
            'The build observation differs from its claimed source commit.', mismatches)
    pin_path = 'packaging/runtime-bundle/' + PIN_FILES[args.target]
    pin = json.loads(snapshot.files[pin_path])
    pin.setdefault('target', args.target)
    source_bytes = b'\n'.join(snapshot.files.values())
    trusted_archives = {h.decode() for h in re.findall(rb'(?<![a-zA-Z0-9])(?:[a-f0-9]{128}|[a-f0-9]{64}|[a-zA-Z0-9+/]{86}==)(?![a-zA-Z0-9])', source_bytes)}
    stages = [('python_supplier', lambda: result.python(args.python_archive, pin)),
              ('exact_wheels', lambda: result.locked_components(snapshot)),
              ('exact_wheels', lambda: result.wheelhouse(args.wheelhouse)),
              ('native_inputs', lambda: result.native_archives(args.native_archive, trusted_archives))]
    stages += [('native_inputs', lambda: result.resources(snapshot)),
               ('native_inputs', lambda: result.helpers(snapshot)),
               ('corresponding_sources', lambda: result.sources(args.source_root)),
               ('frontend_licenses', lambda: result.frontend(args.source_root, args.node))]
    for check, action in stages:
        try:
            action()
        except (OSError, ValueError, KeyError, RuntimeError, tarfile.TarError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
            # Report safe domain messages; subprocess output and OS exceptions
            # can contain host profile paths, so never serialize their strings.
            detail = str(error) if isinstance(error, ValueError) else type(error).__name__ + ': required evidence could not be verified.'
            result.block(check, 'evidence-verification', detail)
    result.native_inventory()
    checks = {name: not detail['blockers'] for name, detail in result.checks.items()}
    # Missing artifact stages cannot silently certify dependent notice/source
    # checks by leaving an empty list of inspected packages.
    if not checks['exact_wheels'] or not checks['python_supplier']:
        for name in ('complete_notices', 'corresponding_sources'):
            result.block(name, 'supplier-review-incomplete', 'Complete dependency evidence requires the exact Python supplier and all wheel artifacts.')
            checks[name] = False
    capabilities = {'capture': 'host-permission', 'game-voice': 'requires-installed-pack'}
    for name in ('ffmpeg', 'vgmstream-cli'):
        capabilities[name] = 'available' if any(PurePosixPath(item['path']).name in {name, name + '.exe'} and item['origins'] for item in result.native_files) else 'unavailable'
    return {'schema': 'toolkit-desktop-input-review-v1', 'source_commit': receipt['source_commit'],
        'build_id': receipt['build_id'], 'target': args.target, 'runtime_receipt_sha256': digest(args.provenance),
        'file_inventory_sha256': inventory_digest(receipt), 'approved': all(checks.values()), 'checks': checks,
        'capabilities': capabilities, 'details': result.checks, 'native_inventory': result.native_files,
        'reviewer_sha256': digest(Path(__file__)), 'observed_inputs_sha256': digest(args.observed_inputs),
        'scope': 'Exact supplied artifacts, delivered notices and known source adapters. Not independent reproduction of compiled outputs, native execution acceptance or legal certification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-root', 'provenance', 'observed-inputs', 'python-archive', 'wheelhouse', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--target', choices=sorted(PIN_FILES), required=True)
    parser.add_argument('--native-archive', type=Path, action='append', default=[])
    parser.add_argument('--node', default='node')
    args = parser.parse_args()
    try:
        no_links(args.output)
        if args.output.exists() or args.runtime_root.absolute() in args.output.absolute().parents:
            raise ValueError('Choose a new report outside the immutable runtime.')
        value = review(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, indent=2) + '\n')
        print(json.dumps({'approved': value['approved'], 'checks': value['checks'],
                          'blockers': sum(len(x['blockers']) for x in value['details'].values())}))
        return 0 if value['approved'] else 2
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print('Desktop input review failed: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
