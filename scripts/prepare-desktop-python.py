"""Prepare exact native CPython for desktop builds without global dependencies.

Use a bootstrap Python 3.11+ to run this script. The resulting interpreter owns
all subsequent wheel installation. --github-output emits python, python_prefix,
and python_archive; --github-path adds only its executable/script directories.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
from python_supplier import ARCHIVE_LIMIT, digest, extract, host_target, load_pin, no_links


def acquire(pin, cache):
    no_links(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / pin['archive']
    no_links(path)
    if path.exists():
        if path.stat().st_size != pin['bytes'] or digest(path) != pin['sha256']:
            raise ValueError('Cached Python archive differs from its exact supplier pin.')
        return path
    pending = path.with_name(path.name + '.part')
    no_links(pending)
    request = urllib.request.Request(pin['url'], headers={'User-Agent': 'GameImmersionToolkit-build/1'})
    for attempt in range(3):
        created = False
        try:
            with urllib.request.urlopen(request, timeout=90, context=ssl.create_default_context()) as response:
                if urllib.parse.urlsplit(response.url).scheme != 'https':
                    raise ValueError('Python supplier redirects require HTTPS.')
                with pending.open('xb') as stream:
                    created = True
                    size = 0
                    while data := response.read(1024 * 1024):
                        size += len(data)
                        if size > min(ARCHIVE_LIMIT, pin['bytes']):
                            raise ValueError('Python supplier archive exceeds its pinned size.')
                        stream.write(data)
            if pending.stat().st_size != pin['bytes'] or digest(pending) != pin['sha256']:
                raise ValueError('Downloaded Python archive differs from its exact supplier pin.')
            pending.replace(path)
            return path
        except BaseException as error:
            if created and pending.exists() and not pending.is_symlink():
                pending.unlink()
            transient = isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead))
            if isinstance(error, urllib.error.HTTPError):
                transient = error.code in (408, 429, 500, 502, 503, 504)
            if attempt == 2 or not transient:
                raise
            print(f'Python supplier download interrupted; retry {attempt + 2}/3.', flush=True)
            time.sleep(2 ** (attempt + 1))


def isolated_environment():
    env = dict(os.environ, PYTHONNOUSERSITE='1')
    for name in ('PYTHONPATH', 'PYTHONHOME', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH'):
        env.pop(name, None)
    return env


def prepare(output, cache):
    pin = load_pin()
    no_links(output)
    if output.exists():
        raise ValueError('Choose a fresh Python output directory; existing files are preserved.')
    print('Preparing pinned CPython ' + pin['version'] + ' for ' + pin['target'], flush=True)
    archive = acquire(pin, cache)
    files = extract(archive, output, pin)
    prefix = output / 'python'
    executable = prefix / pin['executable']
    # Execute only after the complete archive and installed payload were checked.
    probe = subprocess.check_output([str(executable), '-I', '-B', '-c',
        'import json,platform,struct,sys; print(json.dumps(dict(version=platform.python_version(),'
        'bits=struct.calcsize("P")*8,prefix=sys.prefix,machine=platform.machine(),platform=sys.platform)))'],
        env=isolated_environment(), text=True, timeout=60)
    observed = json.loads(probe)
    if (observed['version'] != pin['version'] or observed['bits'] != 64
            or Path(observed['prefix']).resolve() != prefix.resolve()
            or observed['platform'] != pin['sys_platform']
            or observed['machine'].lower() not in pin['machine_names']):
        raise ValueError('Prepared interpreter identity differs from its native supplier pin.')
    receipt = {'schema': 'toolkit-prepared-python-v1', 'supplier': pin, 'installed_files': files,
               'python_executable_sha256': digest(executable), 'native_probe': 'passed'}
    (output / 'PYTHON-PROVENANCE.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return {'python': str(executable), 'python_prefix': str(prefix), 'python_archive': str(archive)}


def emit_github(outputs, output_file=None, path_file=None):
    if any('\n' in value or '\r' in value for value in outputs.values()):
        raise ValueError('GitHub build paths cannot contain newlines.')
    if output_file:
        no_links(output_file)
        with output_file.open('a', encoding='utf-8') as stream:
            stream.write(''.join(key + '=' + value + '\n' for key, value in outputs.items()))
    if path_file:
        no_links(path_file)
        paths = [Path(outputs['python']).parent]
        if host_target() == 'windows-x64':
            paths.append(Path(outputs['python_prefix']) / 'Scripts')
        with path_file.open('a', encoding='utf-8') as stream:
            stream.write(''.join(str(path) + '\n' for path in paths))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--github-path', type=Path)
    args = parser.parse_args()
    result = prepare(args.output.absolute(), args.cache.absolute())
    emit_github(result, args.github_output, args.github_path)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
