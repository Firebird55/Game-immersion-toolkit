"""BUILD HOST ONLY: exact source preparation in unpublished private quarantine.

Never imported by the runtime. No publisher constants are printed, uploaded or
copied to a runtime resource tree. Preparing/building is not a rights approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.runtime_bundle import relative_resource


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Private helper paths cannot use links/reparse points.')


def acquire(url, target, expected):
    regular(target)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'ToolkitR19-build-host'}), timeout=90) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise ValueError('Build input exceeds its bound.')
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Pinned build input checksum mismatch.')
        target.write_bytes(data)
    if not target.is_file() or digest(target) != expected:
        raise ValueError('Existing build input differs; nothing was overwritten.')
    return target


def archive_members(path):
    with zipfile.ZipFile(path) as archive:
        seen = set()
        for item in archive.infolist():
            name = relative_resource(item.filename.rstrip('/'))
            if name.casefold() in seen or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Build archive contains aliases or links.')
            seen.add(name.casefold())
            if not item.is_dir():
                yield name, item, archive


def prepare(kind, evidence, *, source=ROOT):
    if kind not in {'endfield', 'pragmata'}:
        raise ValueError('Unknown private helper kind.')
    pins = json.loads((source / 'packaging/game-readers/blocked-inputs.json').read_text())
    regular(evidence.absolute())
    target = evidence / kind
    if target.exists():
        raise ValueError('Choose a fresh private helper evidence directory.')
    target.mkdir(parents=True)
    inputs = {}
    if kind == 'endfield':
        manifest = json.loads((source / pins[kind]['sources_manifest']).read_text())
        for name, expected in manifest['files'].items():
            relative_resource(name)
            destination = target / 'source' / name.removeprefix('AnimeStudio.Endfield/')
            path = acquire('https://raw.githubusercontent.com/' + manifest['repository'] + '/' + manifest['revision'] + '/' + name,
                           destination, expected)
            inputs['upstream/' + name] = digest(path)
        notice = acquire(pins[kind]['license_source'], target / 'upstream-LICENSE.txt', pins[kind]['license_sha256'])
        inputs['notices/upstream-LICENSE.txt'] = digest(notice)
    elif kind == 'pragmata':
        from backend.ree_extractor import patch_source, SOURCE_SHA256
        from backend.game_tools import REE_SHA
        pin = pins[kind]
        if SOURCE_SHA256 != pin['source_sha256'] or REE_SHA != pin['runtime_sha256']:
            raise ValueError('Blocked helper pins differ from the established adapter.')
        cache = evidence / 'downloads'
        sources = acquire(pin['source'], cache / 'ree-source.zip', pin['source_sha256'])
        runtime = acquire(pin['runtime'], cache / 'ree-runtime.zip', pin['runtime_sha256'])
        prefix = 'REE.PAK.Tool-' + pin['revision'] + '/REE.Unpacker/REE.Unpacker/'
        count = 0
        for name, member, archive in archive_members(sources):
            if name == 'REE.PAK.Tool-' + pin['revision'] + '/README.md':
                data = archive.read(member); (target / 'upstream-README.md').write_bytes(data)
                inputs['notices/upstream-README.md'] = hashlib.sha256(data).hexdigest()
            if not name.startswith(prefix) or not name.endswith('.cs'):
                continue
            if member.file_size > 1024 * 1024:
                raise ValueError('Selected source exceeds its bound.')
            relative = name[len(prefix):]; relative_resource(relative)
            data = archive.read(member)
            inputs['upstream/' + relative] = hashlib.sha256(data).hexdigest()
            destination = target / 'source' / relative; destination.parent.mkdir(parents=True, exist_ok=True)
            emitted = patch_source('/' + relative, data.decode('utf-8-sig').replace('\r\n', '\n'))
            if relative.endswith('/PakList.cs'):
                old = 'private static String m_Path = Utils.iGetApplicationPath() + @"\\Projects\\";'
                if emitted.count(old) != 1:
                    raise ValueError('The private project-list adapter no longer matches.')
                emitted = emitted.replace(old, 'private static String m_Path = Path.GetFullPath(Environment.GetEnvironmentVariable("PROXY_TRANSCRIPT_REE_PROJECTS") ?? (Utils.iGetApplicationPath() + @"\\Projects\\")).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;')
            if relative == 'Program.cs':
                old = 'if (!File.Exists("Zstandard.Net.dll") || !File.Exists("libzstd.dll"))'
                if emitted.count(old) != 1:
                    raise ValueError('The app-local dependency adapter no longer matches.')
                emitted = emitted.replace(old, 'if (!File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Zstandard.Net.dll")) || !File.Exists(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "libzstd.dll")))')
            destination.write_text(emitted, encoding='utf-8')
            count += 1
        if count != pin['source_count'] or not (target / 'upstream-README.md').is_file():
            raise ValueError('Selected selective-reader source/notice closure is incomplete.')
        for name, member, archive in archive_members(runtime):
            if name in {'Zstandard.Net.dll', 'System.Buffers.dll', 'libzstd.dll', 'REE.Unpacker.exe.config'}:
                data = archive.read(member); (target / name).write_bytes(data)
                inputs['runtime/' + name] = hashlib.sha256(data).hexdigest()
        if not all((target / name).is_file() for name in ('Zstandard.Net.dll', 'System.Buffers.dll', 'libzstd.dll', 'REE.Unpacker.exe.config')):
            raise ValueError('Selective reader native/reference inputs are incomplete.')
        inputs['archives/ree-source.zip'] = digest(sources)
        inputs['archives/ree-runtime.zip'] = digest(runtime)
    else:
        raise ValueError('Unknown private helper kind.')
    sources = {path.relative_to(target / 'source').as_posix(): digest(path)
               for path in sorted((target / 'source').rglob('*')) if path.is_file()}
    value = {'schema': 'proxy-blocked-helper-preparation-v1', 'kind': kind, 'status': 'blocked',
        'runtime_collection_allowed': False, 'runtime_entrypoints': [], 'source_inputs': inputs,
        'prepared_sources': sources, 'gate': pins[kind]['gate'], 'r19_complete': False}
    (target / 'prepared-inputs.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=('endfield', 'pragmata'), required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.kind, args.evidence)
    print('Private source inputs prepared; runtime collection and game acceptance remain blocked.')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Source constants and private paths must never enter public job logs.
        print('Private helper preparation failed; no runtime artifact was approved.', file=sys.stderr)
        raise SystemExit(2)
