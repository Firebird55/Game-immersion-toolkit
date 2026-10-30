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

from backend.runtime_payload import TARGETS, PackageError, digest, no_links, executable_target, validate


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
            elif path.is_dir():
                archive.write(path, path.relative_to(root.parent).as_posix() + '/')


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
    shutil.copyfile(receipt_path, payload / 'PROVENANCE.json')
    artifacts = []
    # One closed runtime tree is also the update transport on every platform.
    # Build this before adding platform-specific installation wrappers.
    update_archive = output / (name + '-runtime.zip')
    zip_tree(payload, update_archive)
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
    artifacts.append(update_archive)
    summary = {'schema': 'proxy-desktop-distribution-v1', 'target': target, 'version': receipt['version'],
        'repository': 'Firebird55/Game-immersion-toolkit', 'tag': 'v' + receipt['version'],
        'storage_epoch': receipt.get('storage_epoch', 1), 'host_protocol': receipt.get('host_protocol', 1),
        'update_artifact': update_archive.name,
        'source_commit': receipt['source_commit'], 'runtime_build_id': receipt['build_id'],
        'runtime_receipt_sha256': digest(receipt_path), 'release_eligible': eligible and not candidate,
        'candidate': candidate, 'signing': 'unsigned', 'native_acceptance': receipt.get('native_acceptance', 'unavailable'),
        'artifacts': [{'path': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)} for path in artifacts]}
    summary_path = output / ('DESKTOP-PROVENANCE-' + target + '.json')
    summary_path.write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    # Existing construction reports use this local alias; release assets use
    # the target-specific name so parallel targets cannot overwrite receipts.
    shutil.copyfile(summary_path, output / 'DESKTOP-PROVENANCE.json')
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
