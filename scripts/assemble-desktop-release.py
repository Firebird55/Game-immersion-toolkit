"""Verify and combine checked source and native assets before publication.

Receipts and checksum files are separate for each runner until this boundary.
No incomplete target or unchecked file can enter the combined release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

TARGETS = ('windows-x64', 'linux-x64', 'macos-arm64')
REPOSITORY = 'Firebird55/Game-immersion-toolkit'
ANDROID_APPLICATION = 'io.github.firebird55.gameimmersiontoolkit'
ANDROID_ACCEPTANCE = frozenset({
    'direct_publisher_preparation', 'game_data_update_recovery', 'offline_audio_restart',
    'upgrade_retention', 'ios_sender_capture',
})


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def plain_file(path):
    if not path.is_file() or any(p.is_symlink() or
            (p.exists() and getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
            for p in (path, *path.parents)):
        raise ValueError('Release inputs must be regular files without linked parents.')
    return path


def checked_assets(root):
    sums = plain_file(root / 'SHA256SUMS')
    if sums.stat().st_size > 1024 * 1024:
        raise ValueError('Checksum inventory is too large.')
    result = {}
    for line in sums.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  ([A-Za-z0-9][A-Za-z0-9._-]*)', line)
        if not match:
            raise ValueError('Invalid release checksum record.')
        expected, name = match.groups()
        if name == 'SHA256SUMS' or name.casefold() in result:
            raise ValueError('Duplicate or recursive checksum record.')
        path = plain_file(root / name)
        if digest(path) != expected:
            raise ValueError('Release asset checksum mismatch: ' + name)
        result[name.casefold()] = (name, path, expected)
    if not result:
        raise ValueError('Empty release checksum inventory.')
    return result


def read_receipt(assets, name):
    entry = assets.get(name.casefold())
    if not entry or entry[0] != name or entry[1].stat().st_size > 1024 * 1024:
        raise ValueError('Missing or oversized release provenance: ' + name)
    return json.loads(entry[1].read_text(encoding='utf-8'))


def _json_file(path):
    path = plain_file(path)
    if not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError('Missing or oversized Android release evidence.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError('Invalid Android release evidence.')
    return value


def _verify_apk(apk, code, version, certificate, sdk_commands):
    java, apksigner_jar, aapt2 = sdk_commands
    signature = subprocess.run([java, '-jar', apksigner_jar, 'verify', '--print-certs', apk],
        check=True, capture_output=True, text=True, timeout=120).stdout
    certificates = re.findall(r'^Signer #[0-9]+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$',
                              signature, re.MULTILINE)
    if [value.lower() for value in certificates] != [certificate]:
        raise ValueError('Android signing identity differs.')
    badging = subprocess.run([aapt2, 'dump', 'badging', apk],
        check=True, capture_output=True, text=True, timeout=60).stdout
    fields = re.findall(r"^package: name='([^']+)' versionCode='([0-9]+)' versionName='([^']+)'",
                        badging, re.MULTILINE)
    if fields != [(ANDROID_APPLICATION, str(code), version)] or re.search(r'^application-debuggable', badging, re.MULTILINE):
        raise ValueError('Android release identity or debuggable state differs.')


def _android_assets(root, commit, version, certificate, sdk_commands, *, owner_gameplay_pending=False):
    apk = plain_file(root / 'GameImmersionToolkit-android-release.apk')
    provenance_path = plain_file(root / 'ANDROID-PROVENANCE.json')
    provenance = _json_file(provenance_path)
    apk_hash = digest(apk)
    code = provenance.get('version_code')
    if (not re.fullmatch(r'[a-f0-9]{64}', certificate) or
            provenance.get('schema') != 'toolkit-android-candidate-v1' or
            provenance.get('variant') != 'release' or provenance.get('source_commit') != commit or
            provenance.get('version_name') != version or provenance.get('source_dirty') is not False or
            provenance.get('signing') != 'owner-host-protected-reusable-identity' or
            provenance.get('signing_certificate_sha256') != certificate or
            provenance.get('application_id') != ANDROID_APPLICATION or
            type(code) is not int or not 0 < code <= 2100000000 or provenance.get('apk_sha256') != apk_hash):
        raise ValueError('Android release build provenance differs from the selected tag, APK or signer.')
    evidence = _json_file(root / 'ANDROID-ACCEPTANCE.json')
    accepted = evidence.get('checks')
    if (evidence.get('source_commit') != commit or evidence.get('installed_apk_sha256') != apk_hash or
            evidence.get('abi') != 'arm64-v8a' or type(evidence.get('api')) is not int or evidence['api'] < 34):
        raise ValueError('Android release needs evidence from the exact installed APK.')
    if owner_gameplay_pending:
        if (evidence.get('schema') != 'toolkit-android-physical-install-v1'
                or evidence.get('game') != 'zzz' or evidence.get('version_code') != code
                or not isinstance(accepted, dict) or set(accepted) != {'installed_in_place'}
                or accepted['installed_in_place'] is not True):
            raise ValueError('The ZZZ prerelease needs the verified ARM64 installation.')
    elif (evidence.get('schema') != 'toolkit-android-physical-release-v1' or not isinstance(accepted, dict)
            or set(accepted) != ANDROID_ACCEPTANCE or any(value is not True for value in accepted.values())):
        raise ValueError('Android release needs physical gameplay acceptance.')
    _verify_apk(apk, code, version, certificate, sdk_commands)
    name = 'Game-immersion-toolkit-' + version + '-android.apk'
    # The standalone build and physical reports stay intact. The public receipt
    # includes only fields validated above and can be checked independently.
    public = dict(schema='toolkit-android-distribution-v1', repository=REPOSITORY,
        tag='v' + version, source_commit=commit, version=version, version_code=code,
        application_id=ANDROID_APPLICATION, signing_certificate_sha256=certificate,
        release_eligible=not owner_gameplay_pending,
        physical_device_acceptance='installation-verified' if owner_gameplay_pending else 'approved',
        physical_abi=evidence['abi'], physical_api=evidence['api'], checks=accepted,
        apk=dict(path=name, sha256=apk_hash, bytes=apk.stat().st_size))
    if owner_gameplay_pending:
        public.update(game_scope=['zzz'], gameplay_acceptance='owner-pending')
    return (name, apk, apk_hash), public


def assemble(source, native, output, commit, version, *, android=None, certificate=None, sdk_commands=None,
        owner_gameplay_pending=False):
    if not re.fullmatch(r'[a-f0-9]{40}', commit) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Publication needs an exact commit and numeric version.')
    if output.exists():
        raise ValueError('Choose a new publication output directory.')
    if any(p.is_symlink() or (p.exists() and getattr(p.lstat(), 'st_file_attributes', 0) & 0x400)
            for p in (output, *output.parents)):
        raise ValueError('Publication output cannot traverse linked directories.')
    assets = checked_assets(source)
    receipt = read_receipt(assets, 'PROVENANCE.json')
    if (receipt.get('sourceCommit') != commit or receipt.get('version') != version or
            receipt.get('repository') != REPOSITORY):
        raise ValueError('Source release provenance differs from the selected tag.')
    if {p.name for p in source.iterdir()} != {item[0] for item in assets.values()} | {'SHA256SUMS'}:
        raise ValueError('Source release contains unchecked assets.')
    if android is not None and (not certificate or not sdk_commands or any(not item for item in sdk_commands)):
        raise ValueError('Android publication requires the expected signer and local APK verifiers.')
    if owner_gameplay_pending and android is None:
        raise ValueError('The owner gameplay handoff requires an Android prerelease.')
    targets = TARGETS if android is None else ('windows-x64',)
    for target in targets:
        root = native / ('tested-desktop-' + target)
        target_assets = checked_assets(root)
        name = 'DESKTOP-PROVENANCE-' + target + '.json'
        receipt = read_receipt(target_assets, name)
        if (receipt.get('schema') != 'proxy-desktop-distribution-v1' or receipt.get('target') != target or
                receipt.get('repository') != REPOSITORY or receipt.get('tag') != 'v' + version or
                receipt.get('source_commit') != commit or receipt.get('version') != version):
            raise ValueError('Native release identity differs: ' + target)
        if (receipt.get('release_eligible') is not True or receipt.get('candidate') is not False or
                receipt.get('native_acceptance') != 'approved'):
            raise ValueError('Native release acceptance is incomplete: ' + target)
        # Unsigned releases are permitted; signing is a disclosed property, not
        # a substitute for native acceptance, checksums or dependency notices.
        if receipt.get('signing') not in {'unsigned', 'signed', 'signed-and-notarized'}:
            raise ValueError('Native signing status must be explicit.')
        entries = receipt.get('artifacts')
        if not isinstance(entries, list) or not entries:
            raise ValueError('Missing native artifacts: ' + target)
        prefix = 'Game-immersion-toolkit-' + version + '-' + target
        required = {prefix + '-runtime.zip'}
        required |= {prefix + '.zip', prefix + '-Setup.exe'} if target == 'windows-x64' else (
            {prefix + '.tar.gz'} if target == 'linux-x64' else {prefix + '.zip', prefix + '.dmg'})
        expected = {name}
        for entry in entries:
            asset = entry.get('path') if isinstance(entry, dict) else None
            if not isinstance(asset, str) or asset in expected or not asset.startswith(prefix):
                raise ValueError('Invalid or duplicate native artifact record.')
            checked = target_assets.get(asset.casefold())
            if (not checked or checked[0] != asset or checked[2] != entry.get('sha256') or
                    type(entry.get('bytes')) is not int or checked[1].stat().st_size != entry['bytes']):
                raise ValueError('Native artifact differs from its receipt.')
            expected.add(asset)
        if not required.issubset(expected) or receipt.get('update_artifact') != prefix + '-runtime.zip':
            raise ValueError('A required installer or update archive is missing: ' + target)
        if {item[0] for item in target_assets.values()} != expected or {p.name for p in root.iterdir()} != expected | {'SHA256SUMS'}:
            raise ValueError('Native release contains unchecked assets.')
        if set(assets) & set(target_assets):
            raise ValueError('Release targets contain colliding asset names.')
        assets.update(target_assets)
    public_android = None
    if android is not None:
        artifact, public_android = _android_assets(android, commit, version, certificate, sdk_commands,
            owner_gameplay_pending=owner_gameplay_pending)
        if {artifact[0].casefold(), 'android-provenance.json'} & set(assets):
            raise ValueError('Release targets contain colliding asset names.')
        assets[artifact[0].casefold()] = artifact
    # Validate everything before creating output. Copying uses fixed verified
    # basenames; recompute after copying to detect a changing input.
    output.mkdir(parents=True)
    for name, path, expected in sorted(assets.values()):
        destination = output / name
        shutil.copyfile(path, destination)
        if digest(destination) != expected:
            raise ValueError('A release input changed during assembly.')
    if public_android is not None:
        name = 'ANDROID-PROVENANCE.json'
        path = output / name
        path.write_text(json.dumps(public_android, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        assets[name.casefold()] = (name, path, digest(path))
    (output / 'SHA256SUMS').write_text(''.join(expected + '  ' + name + '\n'
        for name, _, expected in sorted(assets.values())), encoding='utf-8')
    return len(assets)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-release', type=Path, required=True)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--android', type=Path)
    parser.add_argument('--android-certificate')
    parser.add_argument('--java', type=Path)
    parser.add_argument('--apksigner-jar', type=Path)
    parser.add_argument('--aapt2', type=Path)
    parser.add_argument('--android-owner-gameplay-pending', action='store_true')
    args = parser.parse_args()
    try:
        count = assemble(args.source_release, args.native_root, args.output, args.commit, args.version,
            android=args.android, certificate=args.android_certificate,
            sdk_commands=(args.java, args.apksigner_jar, args.aapt2),
            owner_gameplay_pending=args.android_owner_gameplay_pending)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Release assembly failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    print(f'Verified {count} release assets for {args.version}.')
