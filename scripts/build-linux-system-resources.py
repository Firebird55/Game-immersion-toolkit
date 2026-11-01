"""Retain exact authenticated Ubuntu libraries, source packages and full terms.

Run before native construction. The optional --sync-build-host is only for an
ephemeral CI runner: explicitly upgrade selected library owners to versions in
the authenticated Ubuntu indexes. It never runs in an installed application.
The default mode makes no operating-system package changes.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
from backend.runtime_payload import no_links
import linux_system as supplier


def acquire(url, cache, *, expected=None, size=None):
    """Fetch only Ubuntu HTTPS, bounded, retryable and addressed by exact hash."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc not in {'archive.ubuntu.com', 'security.ubuntu.com'}
            or parsed.query or parsed.fragment or not parsed.path.startswith('/ubuntu/')):
        raise ValueError('Ubuntu supplier URL is outside the reviewed archive hosts.')
    name = expected or supplier.sha(url.encode())
    destination = cache / name
    no_links(destination)
    if expected and destination.is_file():
        return supplier.checked(destination, expected, size)
    limit = size if size is not None else 4 * 1024 * 1024
    if not 0 < limit <= supplier.MAX_ARCHIVE:
        raise ValueError('Ubuntu download exceeds its bounded archive size.')
    for attempt in range(3):
        with tempfile.NamedTemporaryFile(prefix=name + '.', suffix='.download', dir=cache, delete=False) as owned:
            temporary = Path(owned.name)
        try:
            with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as stream:
                target = urllib.parse.urlsplit(response.url)
                if target.scheme != 'https' or target.netloc not in {'archive.ubuntu.com', 'security.ubuntu.com'}:
                    raise ValueError('Ubuntu download redirected outside the reviewed hosts.')
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > limit:
                        raise ValueError('Ubuntu download exceeded its authenticated size.')
                    stream.write(block)
            if expected:
                supplier.checked(temporary, expected, size)
            os.replace(temporary, destination)
            return destination
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
        finally:
            temporary.unlink(missing_ok=True)
    raise AssertionError('Bounded Ubuntu acquisition exhausted.')


def save(source, root, name):
    destination = root / supplier.relative(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def collect_metadata(root, cache, policy):
    key = policy['keyring']
    save(acquire(key['url'], cache, expected=key['sha256'], size=key['bytes']), root, 'archive-keyring.gpg')
    indexes = []
    for suite in policy['suites']:
        url = policy['archive_url'] + 'dists/' + suite + '/'
        release_path = save(acquire(url + 'InRelease', cache), root, 'metadata/' + suite + '/InRelease')
        release = supplier.verify_release(release_path, root / 'archive-keyring.gpg', policy, suite)
        entries = supplier.checksums(release['SHA256'])
        for component in policy['components']:
            for kind in ('binary-' + policy['architecture'] + '/Packages', 'source/Sources'):
                prefix = component + '/' + kind
                name = next((prefix + ext for ext in ('.xz', '.gz') if prefix + ext in entries), None)
                if name is None:
                    raise ValueError('Ubuntu release lacks a required authenticated index.')
                item = entries[name]
                # By-hash avoids a mirror's index changing after InRelease was
                # read. Its contents still have to match the signed checksum.
                directory = name.rsplit('/', 1)[0]
                indexes.append((url + directory + '/by-hash/SHA256/' + item['sha256'],
                                'metadata/' + suite + '/' + name, item))
    def one(item):
        url, name, evidence = item
        save(acquire(url, cache, expected=evidence['sha256'], size=evidence['bytes']), root, name)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(one, indexes))


def command(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, encoding='utf-8', timeout=60).stdout


def installed(policy):
    if sys.platform != 'linux' or platform.machine() not in {'x86_64', 'AMD64'}:
        raise ValueError('Ubuntu system collection requires the native Linux x64 build runner.')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu' or release.get('VERSION_CODENAME', '').strip('"') != policy['codename']:
        raise ValueError('Ubuntu build runner differs from the reviewed distribution.')
    paths = {}
    for line in command(['/sbin/ldconfig', '-p']).splitlines():
        match = re.fullmatch(r'\s*(\S+) \(([^)]+)\) => (/.+)', line)
        if match and match[1] in policy['libraries'] and 'x86-64' in match[2]:
            path = Path(match[3]).resolve(strict=True)
            if not any(path.is_relative_to(base) for base in (Path('/usr/lib'), Path('/lib'))):
                raise ValueError('Selected Ubuntu library is outside system library roots.')
            paths[match[1]] = path
    if not paths:
        raise ValueError('Ubuntu library discovery found no selected dependencies.')
    owners = {}
    for soname, path in paths.items():
        alternatives = [str(path)]
        if str(path).startswith('/usr/lib/'):
            alternatives.append(str(path).removeprefix('/usr'))
        names = set()
        for spelling in alternatives:
            result = subprocess.run(['dpkg-query', '-S', spelling], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    owner, separator, member = line.partition(': ')
                    if separator and member == spelling:
                        names.add(owner)
        if len(names) != 1:
            raise ValueError('Selected Ubuntu library has no unique installed package owner: ' + soname)
        owners[soname] = (names.pop(), path)
    names = {owner for owner, _ in owners.values()} | {'base-files'}
    records = {}
    for name in names:
        package, version, architecture = command(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${Architecture}', name]).split('\t')
        if not supplier.IDENTITY.fullmatch(package) or architecture not in {policy['architecture'], 'all'}:
            raise ValueError('Unexpected Ubuntu installed package identity.')
        records[package] = {'package': package, 'version': version}
    observations = [{'soname': soname, 'package': owner.split(':', 1)[0], 'sha256': supplier.digest(path)}
                    for soname, (owner, path) in sorted(owners.items())]
    return records, observations


def synchronize(records, binaries):
    """Explicit build-only synchronization to already authenticated versions."""
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('--sync-build-host is restricted to the ephemeral GitHub Actions build runner.')
    targets = []
    for name, installed_record in sorted(records.items()):
        versions = [version for package, version in binaries if package == name]
        if not versions:
            raise ValueError('Installed Ubuntu package has no authenticated available version: ' + name)
        best = versions[0]
        for version in versions[1:]:
            if subprocess.run(['dpkg', '--compare-versions', version, 'gt', best]).returncode == 0:
                best = version
        if subprocess.run(['dpkg', '--compare-versions', installed_record['version'], 'gt', best]).returncode == 0:
            raise ValueError('Build-host package is newer than authenticated Ubuntu metadata: ' + name)
        if best != installed_record['version']:
            targets.append(name + '=' + best)
    if targets:
        # No shell interpolation or unbounded package expression. apt validates
        # its own signatures too; collection subsequently verifies actual bytes
        # against the exact archives authorized above.
        print('Synchronizing selected Ubuntu build packages: ' + ', '.join(targets), flush=True)
        subprocess.run(['sudo', '-n', 'apt-get', 'install', '-y', '--only-upgrade', '--no-install-recommends',
                        *targets], check=True, timeout=900)


def build(output, cache, policy, *, sync_build_host=False):
    no_links(output)
    no_links(cache)
    if output.exists():
        raise ValueError('Choose a fresh Ubuntu resource output directory.')
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    records, observations = installed(policy)
    with tempfile.TemporaryDirectory(prefix='ubuntu-resources-', dir=output.parent) as directory:
        staging = Path(directory)
        root = staging / supplier.PREFIX
        root.mkdir(parents=True)
        print('Authenticating Ubuntu binary and source indexes.', flush=True)
        collect_metadata(root, cache, policy)
        binaries, sources = supplier.metadata(root, policy, set(records))
        if sync_build_host:
            synchronize(records, binaries)
            records, observations = installed(policy)
            binaries, sources = supplier.metadata(root, policy, set(records))
        downloads, source_records = {}, {}
        for name, item in sorted(records.items()):
            binary = binaries.get((name, item['version']))
            if binary is None:
                raise ValueError('Installed package version is absent from authenticated indexes; synchronize the ephemeral build host: ' + name + '=' + item['version'])
            source = supplier.source_identity(binary)
            if source[0] not in policy['source_packages'] or source not in sources:
                raise ValueError('Full corresponding Ubuntu source version is unavailable or unreviewed: ' + source[0] + '=' + source[1])
            filename = supplier.relative(binary['Filename'])
            downloads['binary/' + filename] = (filename, binary['SHA256'], int(binary['Size']))
            source_records[source] = sources[source]
        for source in source_records.values():
            directory_name = supplier.relative(source['Directory'])
            for name, item in supplier.checksums(source['Checksums-Sha256']).items():
                if '/' in name:
                    raise ValueError('Unexpected Ubuntu source archive basename.')
                path = directory_name + '/' + name
                downloads['source/' + path] = (path, item['sha256'], item['bytes'])
        print(f'Retaining {len(records)} exact binary packages and {len(source_records)} complete source packages.', flush=True)
        def one(item):
            name, (path, expected, size) = item
            url = policy['archive_url'] + urllib.parse.quote(path, safe='/+~.-')
            save(acquire(url, cache, expected=expected, size=size), root, name)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(one, downloads.items()))
        receipt = {'schema': 'toolkit-ubuntu-system-collection-v1', 'policy_sha256': supplier.policy_digest(policy),
                   'packages': sorted(records.values(), key=lambda x: x['package']), 'observed_libraries': observations}
        (root / 'collection.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        print('Verifying binary members, source correspondence and complete license text.', flush=True)
        evidence = supplier.verify_closure(root, policy, retain_notices=True)
        for item in observations:
            origins = evidence['origins'].get(item['sha256'], [])
            if not any(origin['package'] == item['package'] for origin in origins):
                raise ValueError('Installed Ubuntu library differs from its exact signed binary package: ' + item['soname'])
        for name in supplier.OWNED:
            save(ROOT / name, root, 'recipe/' + name)
        (root / 'README.txt').write_text(
            'Unmodified Ubuntu shared-library supplier evidence.\n'
            'metadata contains archive-signed InRelease and SHA256-bound Packages/Sources indexes.\n'
            'binary contains the exact original Debian packages. source retains every file in each\n'
            'matching source record, including original source, Debian patches and build recipes.\n'
            'notices contains full authenticated package copyright and common license texts;\n'
            'NOTICE-INDEX.json maps each notice to its supplier archive member.\n'
            'Shared libraries remain dynamically replaceable. Reverse engineering to debug\n'
            'modifications of LGPL libraries is not restricted by this application.\n'
            'This evidence is reviewed against actual final ELF bytes; it is not a blanket approval.\n', encoding='utf-8')
        manifest = {'schema': 'toolkit-native-resources-v1', 'version': policy['version'],
            'source_inputs': {name: supplier.digest(ROOT / name) for name in supplier.OWNED},
            'rights_review': 'pending-exact-output',
            'files': [{'path': path.relative_to(staging).as_posix(), 'sha256': supplier.digest(path), 'bytes': path.stat().st_size}
                      for path in sorted(staging.rglob('*')) if path.is_file()]}
        (staging / 'resource-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        staging.rename(output)
    return {key: value for key, value in evidence.items() if key != 'origins'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', required=True, type=Path)
    parser.add_argument('--sync-build-host', action='store_true')
    args = parser.parse_args()
    try:
        value = build(args.output.absolute(), args.cache.absolute(), json.loads((ROOT / supplier.POLICY).read_bytes()),
                      sync_build_host=args.sync_build_host)
        print(json.dumps(value))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Ubuntu source collection failed: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
