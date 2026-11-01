"""Build the GPL ZZZ decompressor from pinned preferred sources and Emscripten.

Build hosts need the project's Python and the verified app-local Node runtime.
Installed users need neither a compiler nor npm. The build emits an embedded-WASM
ES module, complete source archives, notices, and its exact recipe. It does not
assert that the npm supplier's undocumented build has been reproduced.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'packaging/zzz-reader/ooz-build.json'
SCHEMA = 'toolkit-ooz-source-build-v1'
MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024 * 1024
OWNED = {'recipe/build-ooz-runtime.py': Path(__file__),
         'recipe/ooz-build.json': POLICY, 'recipe/LICENSE': ROOT / 'LICENSE'}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Build paths cannot traverse links or reparse points.')


def relative(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '\\' in name or any(p in {'.', '..'} or ':' in p for p in path.parts):
        raise ValueError('Unsafe archive or inventory path.')
    if path.as_posix() != name:
        raise ValueError('Noncanonical archive or inventory path.')
    return path


def host_target():
    system = {'win32': 'windows', 'darwin': 'macos', 'linux': 'linux'}.get(sys.platform)
    machine = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(platform.machine().lower())
    return f'{system}-{machine}'


def read_policy():
    value = json.loads(POLICY.read_text(encoding='utf-8'))
    if value.get('schema') != 'toolkit-ooz-build-policy-v1':
        raise ValueError('Unknown ooz build policy.')
    return value


def acquire(pin, cache):
    filename = str(relative(pin['archive']))
    if '/' in filename:
        raise ValueError('Supplier cache names must be filenames.')
    path = cache / filename
    no_links(path)
    if path.exists():
        if path.stat().st_size > MAX_ARCHIVE or digest(path) != pin['sha256']:
            raise ValueError('Cached compiler or source archive differs from its pin.')
        return path
    for attempt in range(3):
        temporary = cache / (filename + '.partial-' + uuid.uuid4().hex)
        try:
            request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('xb') as output:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > MAX_ARCHIVE:
                        raise ValueError('Supplier archive exceeds its size limit.')
                    output.write(block)
            if digest(temporary) != pin['sha256']:
                raise ValueError('Downloaded compiler or source archive differs from its pin.')
            temporary.replace(path)
            return path
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (OSError, urllib.error.URLError, http.client.IncompleteRead):
            if attempt == 2:
                raise
        finally:
            temporary.unlink(missing_ok=True)
        time.sleep(2 ** attempt)


def extract(archive, destination):
    """Preflight every member; Python's data filter also checks link targets."""
    no_links(destination)
    destination.mkdir()
    seen, size = set(), 0
    def check(name, length):
        nonlocal size
        relative(name.rstrip('/'))
        if name.rstrip('/') in seen:
            raise ValueError('Duplicate compiler archive member.')
        seen.add(name.rstrip('/'))
        size += length
        if length < 0 or size > MAX_EXPANDED or len(seen) > 200000:
            raise ValueError('Expanded compiler archive exceeds its limit.')
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for item in source.infolist():
                # ZipInfo normalizes Windows separators in filename; validate
                # the stored name so another host cannot change its meaning.
                check(item.orig_filename, item.file_size)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISDIR(mode) or stat.S_ISREG(mode))):
                    raise ValueError('Compiler ZIP contains a nonregular member.')
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            for item in source.getmembers():
                check(item.name, item.size)
                if not (item.isdir() or item.isfile() or item.issym() or item.islnk()):
                    raise ValueError('Compiler tar contains a special member.')
            source.extractall(destination, filter='data')


def source_member(archive, name):
    with tarfile.open(archive) as source:
        member = source.getmember(name)
        if not member.isfile() or member.size > 16 * 1024 * 1024:
            raise ValueError('Expected a bounded regular source member.')
        return source.extractfile(member).read()


def verify_compiler_sources(compiler, archive, pin):
    """Bind the shipped JS/C runtime sources to the retained preferred source."""
    checked = 0
    with tarfile.open(archive) as source:
        for item in source:
            if not item.isfile() or not item.name.startswith(pin['prefix']):
                continue
            name = item.name.removeprefix(pin['prefix'])
            # Release archives omit source-control and editor metadata. None of
            # these files contributes to the generated JS or linked C runtime.
            if PurePosixPath(name).name in {'.gitignore', '.clang-format', '.clang-tidy'}:
                continue
            if name.startswith(('src/', 'system/')) or name in ('emcc.py', 'em++.py', 'LICENSE', 'emscripten-version.txt'):
                path = compiler / 'emscripten' / str(relative(name))
                no_links(path)
                if digest(path) != hashlib.sha256(source.extractfile(item).read()).hexdigest():
                    raise ValueError('Compiler runtime source differs from the retained source revision.')
                checked += 1
    if checked < 100:
        raise ValueError('Compiler runtime source correspondence is incomplete.')


def text_input(path):
    return path.read_text(encoding='utf-8').replace('\r\n', '\n').encode('utf-8')


def inventory(root):
    no_links(root)
    result, directories = {}, set()
    folded = set()
    for path in sorted(root.rglob('*')):
        no_links(path)
        if path.is_dir():
            directories.add(path.relative_to(root).as_posix())
            continue
        if not path.is_file():
            raise ValueError('Build output must contain only regular files.')
        name = path.relative_to(root).as_posix()
        if name.casefold() in folded:
            raise ValueError('Aliased build output.')
        folded.add(name.casefold())
        if name == 'ooz-build.json':
            continue
        result[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    needed = {parent.as_posix() for name in result for parent in PurePosixPath(name).parents if parent.as_posix() != '.'}
    if directories - needed:
        raise ValueError('Build output contains an unlisted empty directory.')
    return result


def expected_files(pins):
    expected = {pins['output']['path']: pins['output']['sha256']}
    for source in ('source', 'emscripten_source'):
        expected['sources/' + pins[source]['archive']] = pins[source]['sha256']
    expected.update({item['path']: item['sha256'] for item in pins['notices']})
    expected.update({name: hashlib.sha256(text_input(path)).hexdigest() for name, path in OWNED.items()})
    return expected


def verify_build(root):
    """Validate independent fixed hashes, not a receipt's self-asserted approval."""
    root = Path(root).absolute()
    no_links(root)
    path = root / 'ooz-build.json'
    no_links(path)
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('Build receipt exceeds its limit.')
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(receipt, dict):
        raise ValueError('Build receipt must be an object.')
    pins = read_policy()
    target = receipt.get('target')
    if (receipt.get('schema') != SCHEMA or target not in pins['toolchain']['archives']
            or receipt.get('source') != pins['source'] or receipt.get('emscripten_source') != pins['emscripten_source']
            or receipt.get('toolchain') != {'version': pins['toolchain']['version'],
                'release_revision': pins['toolchain']['release_revision'], **pins['toolchain']['archives'][target]}
            or receipt.get('node') != {'version': pins['node']['version'],
                'sha256': pins['node']['executable_sha256'][target]}
            or receipt.get('sources') != pins['sources'] or receipt.get('arguments') != pins['arguments']):
        raise ValueError('Build receipt does not match the fixed source and toolchain recipe.')
    files = inventory(root)
    if receipt.get('files') != files or {name: item['sha256'] for name, item in files.items()} != expected_files(pins):
        raise ValueError('Built decoder, retained sources, notices or recipe differ from their exact pins.')
    if files[pins['output']['path']]['bytes'] != pins['output']['bytes']:
        raise ValueError('Built decoder size differs from its fixed output.')
    return receipt


def run(args, cwd, env, log):
    with log.open('ab') as output:
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=600)
    if result.returncode:
        raise RuntimeError('Pinned ooz build failed; inspect its private build log.')


def build_environment(config):
    # Fixed explicit compiler and Node paths; no injected headers, npm loaders,
    # SDK overrides, HOME configuration, or developer compiler on PATH.
    env = {name: value for name, value in os.environ.items()
           if name.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir'}}
    env.update(PATH='', EM_CONFIG=str(config), PYTHONUTF8='1', SOURCE_DATE_EPOCH='0')
    return env


def probe(node, source, env, work, log):
    # A six-byte authored Kraken fill quantum expands to 4096 bytes. This
    # exercises compressed framing/expansion without game or supplier fixtures.
    script = work / 'probe.mjs'
    script.write_text("import assert from 'node:assert/strict';\n"
        f"const {{decompress,decompressUnsafe}}=await import({json.dumps((source / 'index.js').as_uri())});\n"
        "const packed=Uint8Array.from([0x8c,0x06,0x07,0xff,0xff,0x41]);\n"
        "assert.deepEqual(decompress(packed,4096),new Uint8Array(4096).fill(65));\n"
        "assert.deepEqual(decompressUnsafe(packed,262144),new Uint8Array(262144).fill(65));\n"
        "assert.throws(()=>decompress(Uint8Array.from([255,255,255,255,255,255]),16));\n",
        encoding='utf-8')
    run([node, script], work, env, log)


def build(output, work, cache, node):
    output, work, cache, node = [Path(p).absolute() for p in (output, work, cache, node)]
    for path in (output, work, cache, node):
        no_links(path)
    if output.exists() or work.exists():
        raise ValueError('Choose fresh build and output directories.')
    roots = (output, work, cache)
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i+1:]):
        raise ValueError('Build, output and cache directories must be separate.')
    pins, target = read_policy(), host_target()
    if target not in pins['toolchain']['archives'] or digest(node) != pins['node']['executable_sha256'][target]:
        raise ValueError('Use the pinned app-local Node executable on a supported build host.')
    work.mkdir(parents=True)
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name('.ooz-build-' + uuid.uuid4().hex)
    stage.mkdir()
    source_archive = acquire(pins['source'], cache)
    emscripten_archive = acquire(pins['emscripten_source'], cache)
    compiler_archive = acquire(pins['toolchain']['archives'][target], cache)
    extract(source_archive, work / 'source')
    extract(compiler_archive, work / 'compiler')
    source = work / 'source' / pins['source']['prefix'].rstrip('/')
    compiler = work / 'compiler/install'
    verify_compiler_sources(compiler, emscripten_archive, pins['emscripten_source'])
    config = work / 'emscripten-config'
    config.write_text(f'LLVM_ROOT = {str(compiler / "bin")!r}\nBINARYEN_ROOT = {str(compiler)!r}\nNODE_JS = [{str(node)!r}]\n', encoding='utf-8')
    env = build_environment(config)
    (source / 'build').mkdir()
    log = work / 'build.log'
    command = [sys.executable, compiler / 'emscripten/em++.py', *pins['sources'], *pins['arguments'], '-o', 'build/ooz.js']
    run(command, source, env, log)
    compiled = source / 'build/ooz.js'
    if digest(compiled) != pins['output']['sha256'] or compiled.stat().st_size != pins['output']['bytes']:
        raise ValueError('This compiler produced a different decoder; review the output before changing its pin.')
    probe(node, source, env, work, log)
    archives = {pins['source']['archive']: source_archive, pins['emscripten_source']['archive']: emscripten_archive}
    (stage / 'build').mkdir()
    shutil.copyfile(compiled, stage / pins['output']['path'])
    (stage / 'sources').mkdir()
    for name, archive in archives.items():
        shutil.copyfile(archive, stage / 'sources' / name)
    for notice in pins['notices']:
        data = source_member(archives[notice['archive']], notice['member'])
        if hashlib.sha256(data).hexdigest() != notice['sha256']:
            raise ValueError('Retained full notice differs from its pin.')
        destination = stage / notice['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    for name, path in OWNED.items():
        destination = stage / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(text_input(path))
    receipt = {'schema': SCHEMA, 'target': target, 'source': pins['source'], 'emscripten_source': pins['emscripten_source'],
        'toolchain': {'version': pins['toolchain']['version'], 'release_revision': pins['toolchain']['release_revision'],
                      **pins['toolchain']['archives'][target]},
        'node': {'version': pins['node']['version'], 'sha256': pins['node']['executable_sha256'][target]},
        'sources': pins['sources'], 'arguments': pins['arguments'], 'files': inventory(stage)}
    (stage / 'ooz-build.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    verify_build(stage)
    stage.rename(output)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'work', 'cache', 'node'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.output, args.work, args.cache, args.node)
    print(json.dumps({'schema': SCHEMA, 'target': result['target'], 'output_sha256': result['files']['build/ooz.js']['sha256']}))


if __name__ == '__main__':
    main()
