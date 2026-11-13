"""Read only the pinned historical Genshin metadata trees from their GitHub mirror."""
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


def fetch_trees(catalog):
    git = shutil.which('git')
    if not git:
        raise ValueError('The historical metadata mirror requires Git.')
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
        def run(*args, input=None):
            return subprocess.run([git, '-C', str(directory), *args], input=input, env=env,
                                  capture_output=True, timeout=240, check=True).stdout
        run('init', '--bare', '--quiet')
        run('remote', 'add', 'origin', 'https://github.com/DimbreathBot/AnimeGameData.git')
        run('config', 'remote.origin.promisor', 'true')
        run('config', 'remote.origin.partialclonefilter', 'blob:none')
        run('fetch', '--no-tags', '--depth=1', '--filter=blob:none', 'origin', catalog.revision)
        trees = ('BinOutput/Talk', 'BinOutput/Voice')
        files = run('ls-tree', '-r', '-z', catalog.revision, '--', *trees).split(b'\0')
        objects = set()
        members = {tree: [] for tree in trees}
        for row in filter(None, files):
            match = re.fullmatch(rb'100644 blob ([a-f0-9]{40})\t(BinOutput/(?:Talk|Voice))/([A-Za-z0-9_./-]+\.json)', row)
            if not match:
                raise ValueError('Unexpected file in archived Genshin dialogue trees.')
            objects.add(match[1])
            members[match[2].decode()].append((match[1], match[3].decode()))
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
                    path = catalog.root / (tree.replace('/', '-') + '.tar.gz')
                    _atomic_file(path, data)
                    _atomic_file(path.with_name(path.name + '.sha256'), hashlib.sha256(data).hexdigest().encode())
            finally:
                reader.stdin.close()
