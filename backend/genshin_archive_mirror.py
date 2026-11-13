"""Read pinned Genshin authoring records and release titles from their public Git mirror."""
import hashlib
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from .game_tools import _atomic_file

MIRROR = 'https://github.com/DimbreathBot/AnimeGameData.git'

def _git_environment():
    git = shutil.which('git')
    if not git:
        raise ValueError('The Genshin metadata mirror requires Git.')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    return git, env


def release_titles():
    git, env = _git_environment()
    with tempfile.TemporaryDirectory() as directory:
        def run(*args):
            return subprocess.run([git, '-C', directory, *args], env=env, capture_output=True,
                                  timeout=60, check=True).stdout
        run('init', '--bare', '--quiet')
        run('fetch', '--no-tags', '--depth=250', '--filter=tree:0', MIRROR, 'refs/heads/main')
        commits = {}
        for line in run('log', '--format=%H %s', 'FETCH_HEAD').decode('utf-8').splitlines():
            match = re.fullmatch(r'([0-9a-f]{40}) ((?:OS|CN)RELWin[0-9.]+_R[0-9]+_S[0-9]+_D[0-9]+)', line)
            if match:
                commits.setdefault(match[2], set()).add(match[1])
        return {title: next(iter(ids)) for title, ids in commits.items() if len(ids) == 1}


def fetch_trees(catalog, subtitle_codes=(), *, trees=()):
    if subtitle_codes:
        if trees or any(not re.fullmatch('[A-Z]{2,3}', code) for code in subtitle_codes):
            raise ValueError('Invalid Genshin subtitle language.')
        trees = tuple('Subtitle/' + code for code in subtitle_codes)
    trees = trees or ('BinOutput/Talk', 'BinOutput/Voice')
    if any(not re.fullmatch(r'BinOutput/(?:Talk|Voice|Avatar)|(?:Subtitle|Readable)/[A-Z]{2,3}', tree) for tree in trees):
        raise ValueError('Unsupported Genshin authoring directory.')
    git, env = _git_environment()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        def run(*args, input=None):
            return subprocess.run([git, '-C', str(directory), *args], input=input, env=env,
                                  capture_output=True, timeout=240, check=True).stdout
        run('init', '--bare', '--quiet')
        run('remote', 'add', 'origin', MIRROR)
        run('config', 'remote.origin.promisor', 'true')
        run('config', 'remote.origin.partialclonefilter', 'blob:none')
        run('fetch', '--no-tags', '--depth=1', '--filter=blob:none', 'origin', catalog.revision)
        files = run('ls-tree', '-r', '-z', catalog.revision, '--', *trees).split(b'\0')
        objects = set()
        members = {tree: [] for tree in trees}
        for row in filter(None, files):
            if b'\tSubtitle/' in row and row.endswith(b'.txt'):
                continue
            match = re.fullmatch(rb'100644 blob ([a-f0-9]{40})\t([^/\t]+/[^/\t]+)/([A-Za-z0-9_./-]+)', row)
            if not match:
                raise ValueError('Unexpected file in archived Genshin dialogue trees.')
            tree, relative = match[2].decode(), match[3].decode()
            suffix = '.srt' if tree.startswith('Subtitle/') else '.txt' if tree.startswith('Readable/') else '.json'
            if tree not in members or '..' in relative.split('/') or not relative.endswith(suffix):
                raise ValueError('Unexpected Genshin metadata asset path.')
            objects.add(match[1])
            members[tree].append((match[1], relative))
        if not 0 < len(objects) < 100_000:
            raise ValueError('Unexpected Genshin dialogue archive size.')
        run('fetch', '--no-tags', '--no-write-fetch-head', '--no-recurse-submodules', '--filter=blob:none',
            'origin', '--stdin', input=b'\n'.join(sorted(objects)) + b'\n')
        env['GIT_NO_LAZY_FETCH'] = '1'
        with subprocess.Popen([git, '-C', str(directory), 'cat-file', '--batch'], env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as reader:
            try:
                for tree, entries in members.items():
                    total = 0
                    output = io.BytesIO()
                    with tarfile.open(fileobj=output, mode='w:gz', compresslevel=3) as archive:
                        for ident, relative in entries:
                            reader.stdin.write(ident + b'\n')
                            reader.stdin.flush()
                            key, kind, raw_size = reader.stdout.readline(128).split()
                            size = int(raw_size)
                            total += size
                            if key != ident or kind != b'blob' or not 0 <= size <= 128 * 1024**2 or total > 512 * 1024**2:
                                raise ValueError('Unsupported archived Genshin dialogue object.')
                            content = reader.stdout.read(size)
                            if len(content) != size or reader.stdout.read(1) != b'\n':
                                raise ValueError('Incomplete archived Genshin dialogue object.')
                            member = tarfile.TarInfo('GameData/' + tree + '/' + relative)
                            member.size = size
                            archive.addfile(member, io.BytesIO(content))
                    data = output.getvalue()
                    path = catalog.root / (tree.replace('/', '-') + ('.tar.gz' if tree.startswith('BinOutput/') else '-text.tar.gz'))
                    _atomic_file(path, data)
                    _atomic_file(path.with_name(path.name + '.sha256'), hashlib.sha256(data).hexdigest().encode())
            finally:
                reader.stdin.close()
