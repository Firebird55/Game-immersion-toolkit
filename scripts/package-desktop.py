"""Package an exact frozen inventory without acquiring tools or user data.

Candidate packaging is explicit and never turns incomplete R19 evidence into
release eligibility. Published packages require the full reviewed receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.runtime_bundle import relative_resource

TARGETS = {'windows-x64', 'linux-x64', 'macos-x64', 'macos-arm64'}


class PackageError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise PackageError('Package paths must not traverse links or reparse points.')


def executable_target(path):
    data = path.read_bytes()[:4096]
    if data.startswith(b'MZ') and len(data) >= 64:
        offset = struct.unpack_from('<I', data, 60)[0]
        if offset + 6 <= len(data) and data[offset:offset + 4] == b'PE\0\0':
            if struct.unpack_from('<H', data, offset + 4)[0] == 0x8664:
                return 'windows-x64'
    if data[:6] == b'\x7fELF\x02\x01' and len(data) >= 20 and struct.unpack_from('<H', data, 18)[0] == 62:
        return 'linux-x64'
    if data[:4] == b'\xcf\xfa\xed\xfe' and len(data) >= 8:
        cpu = struct.unpack_from('<I', data, 4)[0]
        return {0x1000007: 'macos-x64', 0x100000c: 'macos-arm64'}.get(cpu)
    raise PackageError('Runtime executable has an unsupported architecture or invalid header.')


def validate(root, receipt, target, *, candidate=False):
    root = root.absolute()
    no_links(root)
    if target not in TARGETS:
        raise PackageError('Unsupported installer target.')
    if receipt.get('schema') != 'proxy-runtime-candidate-v1':
        raise PackageError('Expected the exact runtime candidate inventory.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', str(receipt.get('version', ''))):
        raise PackageError('Installer needs an exact numeric version.')
    if not re.fullmatch(r'[a-f0-9]{40}', str(receipt.get('source_commit', ''))):
        raise PackageError('Installer needs an exact source commit.')
    eligible = (receipt.get('profile') == 'runtime' and receipt.get('r19_complete') is True
        and receipt.get('redistribution_review') == 'approved' and receipt.get('native_acceptance') == 'approved')
    if not candidate and not eligible:
        raise PackageError('Release packaging requires completed runtime, redistribution and native acceptance. Use --candidate for private construction tests.')
    expected = {}
    for entry in receipt.get('files', []):
        name = relative_resource(entry.get('path', ''))
        if name.casefold() in expected or not re.fullmatch(r'[a-f0-9]{64}', str(entry.get('sha256', ''))):
            raise PackageError('Duplicate or invalid inventory entry.')
        expected[name.casefold()] = entry
    if not expected:
        raise PackageError('Empty runtime payload.')
    actual = {}
    for path in sorted(root.rglob('*')):
        linked = path.is_symlink()
        if not linked:
            no_links(path)
        if path.is_dir() and not linked:
            continue
        if not path.is_file() and not linked:
            raise PackageError('Runtime payload must contain regular files.')
        name = relative_resource(path.relative_to(root).as_posix())
        if name.casefold() in actual:
            raise PackageError('Aliased runtime file.')
        actual[name.casefold()] = name
        entry = expected.get(name.casefold())
        if linked:
            link = os.readlink(path)
            if (target == 'windows-x64' or os.path.isabs(link) or root.resolve() not in path.resolve().parents
                    or not path.exists() or not entry or entry.get('link') != link):
                raise PackageError('Runtime symbolic link is outside the verified inventory.')
            size, sha = len(link.encode()), hashlib.sha256(link.encode()).hexdigest()
        else:
            size, sha = path.stat().st_size, digest(path)
        if not entry or entry['path'] != name or entry.get('bytes') != size or entry['sha256'] != sha:
            raise PackageError('Runtime inventory differs from the payload: ' + name)
    if set(actual) != set(expected):
        raise PackageError('Runtime inventory has missing files.')
    executable = 'ProxyTranscriptRuntime.exe' if target == 'windows-x64' else 'ProxyTranscriptRuntime'
    if executable_target(root / executable) != target:
        raise PackageError('Runtime executable does not match the installer target.')
    manifest = json.loads((root / '_internal/runtime-manifest.json').read_text(encoding='utf-8'))
    for key in ('source_commit', 'version', 'build_id', 'profile'):
        if manifest.get(key) != receipt.get(key):
            raise PackageError('Embedded runtime identity differs from candidate provenance.')
    if not (root / 'LICENSE').is_file() or not (root / 'THIRD_PARTY').is_dir():
        raise PackageError('Exact application and dependency notices are required.')
    return eligible


def zip_tree(root, destination):
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                info = zipfile.ZipInfo(path.relative_to(root.parent).as_posix())
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, os.readlink(path).encode())
            elif path.is_file():
                name = path.relative_to(root.parent).as_posix()
                info = zipfile.ZipInfo.from_file(path, name)
                if path.name in {'ProxyTranscriptRuntime', 'ProxyTranscriptAsr'}:
                    info.external_attr = (stat.S_IFREG | 0o755) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())


def package(root, receipt_path, target, output, *, candidate=False, iscc=None, dmg=False):
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    eligible = validate(root, receipt, target, candidate=candidate)
    output = output.absolute()
    no_links(output)
    if output.exists():
        raise PackageError('Choose a new output directory; previous packages are preserved.')
    if root.absolute() == output or root.absolute() in output.parents or output in root.absolute().parents:
        raise PackageError('Package output and runtime payload must not overlap.')
    if target == 'windows-x64' and iscc and not Path(iscc).is_file():
        raise PackageError('The build-host Inno Setup compiler is missing.')
    if dmg and (sys.platform != 'darwin' or not target.startswith('macos-')):
        raise PackageError('Create a DMG on the macOS build host.')
    output.mkdir(parents=True)
    name = 'Game-immersion-toolkit-' + receipt['version'] + '-' + target + ('-candidate' if candidate else '')
    payload = output / 'payload' / name
    payload.parent.mkdir()
    shutil.copytree(root, payload, symlinks=True)
    # Bind installed provenance without changing immutable runtime resources.
    (payload / 'PROVENANCE.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    artifacts = []
    if target == 'windows-x64':
        archive = output / (name + '.zip')
        zip_tree(payload, archive)
        artifacts.append(archive)
        if iscc:
            subprocess.run([str(iscc), '/Qp', '/DPayloadRoot=' + str(payload), '/DAppVersion=' + receipt['version'],
                '/DOutputRoot=' + str(output), '/DArtifactName=' + name + '-Setup',
                str(ROOT / 'packaging/desktop/installer.iss')], check=True)
            installer = output / (name + '-Setup.exe')
            if not installer.is_file():
                raise PackageError('Installer compiler did not create the requested output.')
            artifacts.append(installer)
    elif target == 'linux-x64':
        shutil.copyfile(ROOT / 'packaging/desktop/linux-install.sh', payload / 'install.sh')
        (payload / 'install.sh').chmod(0o755)
        (payload / 'ProxyTranscriptRuntime').chmod(0o755)
        archive = output / (name + '.tar.gz')
        def permissions(member):
            if Path(member.name).name in {'ProxyTranscriptRuntime', 'ProxyTranscriptAsr', 'install.sh'}:
                member.mode = 0o755
            return member
        with tarfile.open(archive, 'x:gz') as stream:
            stream.add(payload, arcname=name, filter=permissions)
        artifacts.append(archive)
    else:
        app = output / 'application' / 'Game Immersion Toolkit.app'
        macos = app / 'Contents/MacOS'
        macos.parent.mkdir(parents=True)
        shutil.copytree(payload, macos, symlinks=True)
        (macos / 'ProxyTranscriptRuntime').chmod(0o755)
        info = {'CFBundleName': 'Game Immersion Toolkit', 'CFBundleDisplayName': 'Game Immersion Toolkit',
            'CFBundleIdentifier': 'org.gameimmersiontoolkit.desktop', 'CFBundleExecutable': 'ProxyTranscriptRuntime',
            'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': receipt['version'],
            'CFBundleVersion': receipt['version'], 'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '14.0',
            'NSScreenCaptureUsageDescription': 'Read game subtitles from the display you select.'}
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        archive = output / (name + '.zip')
        zip_tree(app, archive)
        artifacts.append(archive)
        if dmg:
            # The Applications shortcut is part of the disk image only, never
            # part of the validated runtime tree or a writable state root.
            (app.parent / 'Applications').symlink_to('/Applications', target_is_directory=True)
            disk = output / (name + '.dmg')
            subprocess.run(['hdiutil', 'create', '-volname', 'Game Immersion Toolkit', '-srcfolder', str(app.parent),
                '-format', 'UDZO', str(disk)], check=True)
            artifacts.append(disk)
    summary = {'schema': 'proxy-desktop-distribution-v1', 'target': target, 'version': receipt['version'],
        'source_commit': receipt['source_commit'], 'runtime_build_id': receipt['build_id'],
        'runtime_receipt_sha256': digest(receipt_path), 'release_eligible': eligible and not candidate,
        'candidate': candidate, 'signing': 'unsigned', 'native_acceptance': receipt.get('native_acceptance', 'unavailable'),
        'artifacts': [{'path': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in artifacts]}
    summary_path = output / 'DESKTOP-PROVENANCE.json'
    summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    artifacts.append(summary_path)
    (output / 'SHA256SUMS').write_text(''.join(digest(path) + '  ' + path.name + '\n' for path in artifacts), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--provenance', required=True, type=Path)
    parser.add_argument('--target', required=True, choices=sorted(TARGETS))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--candidate', action='store_true')
    parser.add_argument('--iscc', type=Path)
    parser.add_argument('--dmg', action='store_true')
    args = parser.parse_args()
    try:
        result = package(args.runtime_root, args.provenance, args.target, args.output,
            candidate=args.candidate, iscc=args.iscc, dmg=args.dmg)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Desktop packaging failed: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
