"""Compare released Windows package inventories without a game installation."""
import argparse
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from xml.etree import ElementTree
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import endfield_release, sophon_assets
from backend.game_tools import _atomic_file, download

KURO = 'https://prod-alicdn-gamestarter.kurogame.com/launcher/game/G153/50004_obOHXFrFanqsaIEOmuKroCcbZkQRBC7c/index.json'
NTE = {'nte-global': 'ntecdn1.perfectworld.com', 'nte-cn': 'yhcdn1.wmupd.com'}
LIMIT = 16 * 1024**2


def kuro_bytes(url):
    data = download(url, limit=LIMIT)
    if data.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as packed:
            data = packed.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('Kuro launcher index exceeds its size limit.')
    return data


def wuwa():
    root = json.loads(kuro_bytes(KURO))['default']
    config = root['config']
    path, version = config['indexFile'], config['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not re.fullmatch(
            r'launcher/game/G153/50004/' + re.escape(version) + r'/[A-Za-z0-9]+/resource/50004/'
            + re.escape(version) + r'/indexFile\.json', path):
        raise ValueError('Unrecognized Global Kuro launcher index.')
    for candidate in root['cdnList']:
        cdn = urlsplit(candidate['url'])
        if (cdn.scheme == 'https' and re.fullmatch(r'[a-z0-9-]+\.aki-game\.net', cdn.netloc)
                and cdn.path in ('', '/') and not cdn.query and not cdn.fragment):
            url = 'https://' + cdn.netloc + '/' + path
            data = kuro_bytes(url)
            if hashlib.md5(data).hexdigest() != config['indexFileMd5']:
                raise ValueError('Kuro launcher manifest checksum mismatch.')
            break
    else:
        raise ValueError('No recognized Kuro publisher CDN.')
    files = {}
    for row in json.loads(data)['resource']:
        name = row['dest']
        if name.startswith('Client/Content/Paks/') and name.lower().endswith('.pak'):
            if name in files or not re.fullmatch('[0-9a-f]{32}', row['md5']) or type(row['size']) is not int or row['size'] <= 0:
                raise ValueError('Invalid or duplicate Kuro package.')
            files[name] = [row['size'], row['md5']]
    if not files:
        raise ValueError('The Kuro launcher has no base game PAKs.')
    return version, 'Global launcher base PAKs', files


def nte(region):
    host = NTE[region]
    branch = 'publish_PC'
    visited = set()
    while branch not in visited and len(visited) < 12:
        visited.add(branch)
        root = 'https://' + host + '/clientRes/' + branch + '/Version/Windows'
        cfg = ElementTree.fromstring(download(root + '/config.xml', limit=256 * 1024))
        next_branch = cfg.findtext('ResConfig')
        if next_branch:
            next_branch = json.loads(base64.b64decode(next_branch, validate=True)).get('branchName')
        if not next_branch or next_branch == branch:
            version = cfg.findtext('ResVersion', '')
            if not re.fullmatch(r'\d+\.\d+\.\d+', version):
                raise ValueError('Invalid NTE release version.')
            raw = download(root + '/version/' + version + '/ResList.bin.zip', limit=LIMIT)
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = [entry for entry in archive.infolist() if entry.filename == 'ResList.bin']
                if len(entries) != 1 or not 0 < entries[0].file_size <= LIMIT:
                    raise ValueError('Missing or ambiguous NTE resource list.')
                contents = archive.read(entries[0])
            files = {'ResList.bin': [len(contents), hashlib.sha256(contents).hexdigest()]}
            for item in cfg.findall('BaseVerson/Res'):
                tag, revision, size = item.get('Tag', ''), item.get('version', ''), item.get('ResSize', '')
                if (not re.fullmatch(r'[a-zA-Z0-9_]+', tag) or not re.fullmatch(r'\d+\.\d+\.\d+', revision)
                        or not size.isdecimal() or tag in files):
                    raise ValueError('Invalid or duplicate NTE resource section.')
                files[tag] = [int(size), revision]
            return branch + '/' + version, 'Regional resource list and declared base sections', files
        if not re.fullmatch(r'PC_[0-9]+', next_branch):
            raise ValueError('Unsupported NTE release branch.')
        branch = next_branch
    raise ValueError('NTE region returned an incomplete release chain.')


def collect(channel, cache):
    if channel == 'wuwa-global':
        version, scope, files = wuwa()
    elif channel in NTE:
        version, scope, files = nte(channel)
    elif channel == 'endfield-global':
        _, raw = endfield_release.discover()
        build = json.loads(raw)
        version, scope = build['version'], 'Global initial and main resource indexes'
        files = {k: [v['version'], v['sha256']] for k, v in build['layers'].items()}
    else:
        build = sophon_assets.release(channel)
        version, scope, files = build['version'], 'Released launcher dub PCKs and game manifest', {}
        game = build['manifests']['game']
        files['game/manifest'] = [game[3], game[4]]
        for field in sorted(set(sophon_assets.VOICE_FIELDS.values())):
            packages = sophon_assets.manifest(cache, channel, tuple(build['manifests'][field]), ('.pck',))
            if not packages:
                raise ValueError('Missing released voice packages for ' + field)
            files.update({field + '/' + name: [asset.size, asset.digest] for name, asset in packages.items()})
    return {'format': 1, 'channel': channel, 'scope': scope, 'version': version, 'files': files}


def differences(before, after):
    if any(before.get(k) != after[k] for k in ('format', 'channel', 'scope')):
        raise ValueError('Cannot compare different regions or inventory formats.')
    old, new = before['files'], after['files']
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': sorted(k for k in old.keys() & new.keys() if old[k] != new[k])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('channel', choices=[*sophon_assets.CHANNELS, 'endfield-global', 'wuwa-global', *NTE])
    parser.add_argument('--cache', type=Path, required=True, help='Private directory for launcher manifests')
    parser.add_argument('--previous', type=Path, help='Compare against a previously saved inventory')
    parser.add_argument('--output', type=Path, required=True, help='Write a verified inventory for later comparison')
    args = parser.parse_args()
    before = json.loads(args.previous.read_bytes()) if args.previous else None
    after = collect(args.channel, args.cache.resolve())
    result = {key: value for key, value in after.items() if key != 'files'}
    result['entries'] = len(after['files'])
    if before is not None:
        result.update(differences(before, after))
    _atomic_file(args.output, json.dumps(after, sort_keys=True).encode())
    print(json.dumps(result, indent=2))
