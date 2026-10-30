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
import sys

TARGETS = ('windows-x64', 'linux-x64', 'macos-arm64')
REPOSITORY = 'Firebird55/Game-immersion-toolkit'


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


def assemble(source, native, output, commit, version):
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
    for target in TARGETS:
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
    # Validate everything before creating output. Copying uses fixed verified
    # basenames; recompute after copying to detect a changing input.
    output.mkdir(parents=True)
    for name, path, expected in sorted(assets.values()):
        destination = output / name
        shutil.copyfile(path, destination)
        if digest(destination) != expected:
            raise ValueError('A release input changed during assembly.')
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
    args = parser.parse_args()
    try:
        count = assemble(args.source_release, args.native_root, args.output, args.commit, args.version)
    except (OSError, ValueError) as error:
        print('Release assembly failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    print(f'Verified {count} source and native release assets for {args.version}.')
