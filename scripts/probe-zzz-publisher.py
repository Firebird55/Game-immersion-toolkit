"""Fetch an authored Global ZZZ subtitle and its original released recordings."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import sophon_assets as sophon
from backend import game_tools
from backend.voice_assets import external_table, voice_hash

CHANNEL = 'zzz-global'
BASE = 'ZenlessZoneZero_Data/StreamingAssets/'
DUBS = {'en': ('En', 'English(EN)'), 'ja': ('Jp', 'Japanese(JP)'),
        'ko': ('Kr', 'Korean(KR)'), 'zh-Hans': ('Cn', 'Chinese(PRC)')}


def manifest_json(files, cache, name):
    asset = files[BASE + name]
    return json.loads(asset.read(cache, 0, asset.size))['files']


def materialize(work, cache, files, rows, pattern):
    names = []
    for row in rows:
        name = row['remoteName']
        if not re.fullmatch(pattern, name):
            raise ValueError('Unsupported released design or resource path.')
        asset = files[BASE + name]
        if row['fileSize'] != asset.size:
            raise ValueError('Released resource size does not match the launcher manifest.')
        target = work / (name.replace('/', '-'))
        if target.name in names:
            raise ValueError('Duplicate released ZZZ design asset.')
        target.write_bytes(asset.read(cache, 0, asset.size))
        names.append(target.name)
    return names


def stage_scenes(work, cache, files, ranges):
    grouped = defaultdict(list)
    for row in ranges:
        name = row['block']
        if not re.fullmatch(r'Blocks/\d+\.blk', name):
            raise ValueError('Invalid scene block identity.')
        grouped[name].append((row['offset'], row['size']))

    def stage(item):
        name, ranges = item
        asset = files[BASE + name]

        @lru_cache(maxsize=3)
        def chunk(position, length):
            return asset.read(cache, position, length)

        out = work / (name.split('/')[-1] + '.scenes')
        with out.open('xb') as handle:
            for start, length in sorted(ranges):
                if not 0 < length <= 64 * 1024**2 or not 0 <= start <= asset.size - length:
                    raise ValueError('Scene exceeds its released package.')
                end = start + length
                handle.write(struct.pack('<I', length))
                begin = handle.tell()
                for offset, size, *_ in asset.chunks:
                    if offset >= end:
                        break
                    if offset + size > start:
                        handle.write(chunk(offset, size)[max(0, start - offset):min(size, end - offset)])
                if handle.tell() - begin != length:
                    raise ValueError('Incomplete staged scene.')
        return out.name

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(stage, sorted(grouped.items())))


def source_paths(source, version):
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', source) or '..' in source:
        raise ValueError('Unsupported or conditional ZZZ voice source.')
    if '/' in source:
        return {source}
    if not source.lower().startswith('galgame_'):
        raise ValueError('This source needs a different verified voice path family.')
    # Index membership decides among candidates, including unversioned launch files.
    major, minor, _ = map(int, version.split('.'))
    versions = [f'Ver{i}_{j}/' for i in range(1, major + 1)
                for j in range(1 + minor if i == major else 10)]
    speakers = {s for s in source.split('_')[1:] if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9]+', s)}
    return {f'VO_GalGame/{v}VO_{s}/{source}' for v in ['', *versions] for s in speakers}


def recording(cache, build, locale, paths):
    folder, namespace = DUBS[locale]
    candidates = {voice_hash(f'{namespace}/ex/{path}.wem') for path in paths}
    files = sophon.manifest(cache, CHANNEL, tuple(build['manifests'][sophon.VOICE_FIELDS[locale]]), ('.pck',))
    prefix = BASE + 'Audio/Windows/Full/' + folder + '/'
    packages = [asset for name, asset in files.items() if name.startswith(prefix) and '/' not in name[len(prefix):]]

    def matching(asset):
        entries = external_table(asset.name, asset.size, lambda start, count: asset.read(cache, start, count))
        return [(asset, row) for row in entries if row.file_id in candidates]

    with ThreadPoolExecutor(max_workers=6) as pool:
        hits = [hit for rows in pool.map(matching, packages) for hit in rows]
    if len(hits) != 1:
        raise ValueError(f'{locale} has {len(hits)} original matches for the authored source.')
    asset, row = hits[0]
    data = asset.read(cache, row.offset, row.size)
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE' or struct.unpack_from('<I', data, 4)[0] + 8 != len(data):
        raise ValueError('Incomplete released WEM.')
    return data, {'package': asset.name, 'file_id': f'{row.file_id:016x}', 'sha256': hashlib.sha256(data).hexdigest()}


def fetch(args):
    work_base = args.cache.resolve()
    work_base.mkdir(parents=True, exist_ok=True)
    reader = args.reader.resolve(strict=True) if args.reader else None
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Choose a new output directory.')
    if not re.fullmatch('[A-Za-z0-9_-]{1,240}', args.text_id):
        raise ValueError('Expected an authored subtitle ID.')
    build = sophon.release(CHANNEL)
    files = sophon.manifest(work_base, CHANNEL, tuple(build['manifests']['game']), ('/data_version', '/res_version', '.blk'))
    with TemporaryDirectory(dir=work_base) as temp:
        work = Path(temp)
        if reader is None:
            source = work_base / 'reader' / game_tools.READER_SHA / 'galgame-perform.ts'
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != game_tools.READER_SHA:
                raw = game_tools.download(game_tools.READER_BASE + 'galgame-perform.ts', limit=4 * 1024**2)
                if hashlib.sha256(raw).hexdigest() != game_tools.READER_SHA:
                    raise ValueError('ZZZ source reader checksum mismatch.')
                game_tools._atomic_file(source.with_name('LICENSE'), game_tools.download(game_tools.READER_BASE + 'LICENSE', limit=128 * 1024))
                game_tools._atomic_file(source, raw)
            subprocess.run([args.node, str(ROOT / 'scripts/zzz-publisher-dialogue.mjs'), 'compile',
                            str(work), str(source)], check=True, timeout=60)
            reader = work / 'galgame-perform.mjs'

        def query(mode, **values):
            (work / (mode + '-input.json')).write_text(json.dumps({'id': args.text_id, **values}), encoding='utf-8')
            subprocess.run([args.node, str(ROOT / 'scripts/zzz-publisher-dialogue.mjs'), mode,
                            str(work), str(reader)], timeout=600, check=True)
            return json.loads((work / (mode + '-output.json')).read_bytes())

        designs = manifest_json(files, work_base, 'data_version')
        catalogs = [r for r in manifest_json(files, work_base, 'res_version') if not r.get('tags')
                    and re.fullmatch(r'Blocks/\d+\.blk', r['remoteName'])]
        plan = query('plan', design=materialize(work, work_base, files, designs, r'Blocks/Data/\d+\.blk'),
                     catalogs=materialize(work, work_base, files, catalogs, r'Blocks/\d+\.blk'))
        blocks = stage_scenes(work, work_base, files, plan['ranges'])
        source = query('bindings', blocks=blocks)['source']
        paths = source_paths(source, build['version'])
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=output.parent) as staging:
            result = Path(staging) / 'result'
            result.mkdir()
            info = {'version': build['version'], 'build': build['build'], 'text_id': args.text_id, 'source': source,
                    'texts': {k: v for k, v in plan['texts'].items() if v.strip()}, 'dubs': {}}
            for locale in dict.fromkeys(args.dub or DUBS):
                data, info['dubs'][locale] = recording(work_base, build, locale, paths)
                (result / (locale + '.wem')).write_bytes(data)
            (result / 'subtitle.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
            if sophon.release(CHANNEL) != build:
                raise ValueError('The launcher release changed during extraction. Retry the query.')
            result.rename(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('text_id')
    parser.add_argument('--reader', type=Path, help='Use an existing compiled galgame-perform.mjs (default: prepare the pinned reader)')
    parser.add_argument('--node', default='node', help='Node executable for that reader')
    parser.add_argument('--cache', type=Path, required=True, help='Private cache for verified publisher chunks')
    parser.add_argument('--output', type=Path, required=True, help='New private directory for local subtitles and WEMs')
    parser.add_argument('--dub', choices=DUBS, action='append', help='Repeat to select dubs (default: all four)')
    fetch(parser.parse_args())
