"""Publisher acquisition for the original TextMap/container preparation route.

Whole original packages and executables are authenticated as data. The fixed
software describes the design-catalog root and naming format; current official
indices choose package identities. No client code or Unity runtime is executed.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import tempfile

from . import genshin_blb as blb, genshin_blb_parameters as codec, genshin_hotfix as hotfix
from . import sophon_assets as sophon
from .game_tools import _atomic_file
from .genshin_native_x64 import Image
from .genshin_official_text import OriginalTables
from .genshin_original_containers import DataObjects, DesignCatalog
from .genshin_original_textmap import NativeTextMapParameters, discover_native_parameters
from .hoyo_publisher_voice import descriptor
from .prebuilt_readers import _no_links


INDEX_PACKAGE = 'blocks/00/31049741.blk'
INDEX_OBJECT = '0000006f'
MAX_NATIVE = 768 * 1024**2


class CodecRejected(ValueError):
    """Only original container rejection can request refreshed codec data."""


def check(value):
    if not value:
        raise ValueError('The selected official Genshin text generation is unavailable or inconsistent.')


def digest(path, algorithm='sha256'):
    result = hashlib.new(algorithm)
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024**2):
            result.update(block)
    return result.hexdigest()


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Source:
    def __init__(self, directory, build, helper, parameters, parameter_receipt):
        self.directory = Path(directory).absolute(); _no_links(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.publisher = self.directory.parent / 'sophon'
        self.build, self.helper = build, helper
        self.parameters, self.parameter_receipt = parameters, parameter_receipt
        self.stamp = descriptor(build)[0]
        self.package_receipts = {}
        check('hotfix' in build)
        raw = hotfix.index(self.publisher, build, 'design')
        check(isinstance(raw, bytes) and 0 < len(raw) <= 64 * 1024**2)
        self.index_sha256 = hashlib.sha256(raw).hexdigest()
        self.index_md5 = hashlib.md5(raw).hexdigest()
        self.packages = {}
        for line in raw.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            name, size, md5 = row['remoteName'], row['fileSize'], row['md5']
            check(isinstance(name, str) and re.fullmatch(r'blocks/[0-9]{2,10}/[0-9]{1,10}\.blk', name)
                  and name not in self.packages and type(size) is int and 0 < size <= 8 * 1024**3
                  and isinstance(md5, str) and re.fullmatch('[a-f0-9]{32}', md5))
            self.packages[name] = {'name': name, 'bytes': size, 'md5': md5}
        check(INDEX_PACKAGE in self.packages)
        root = self.objects(INDEX_PACKAGE)
        check(set(root.names) == {INDEX_OBJECT})
        self.catalog = DesignCatalog(root.named(INDEX_OBJECT))
        descriptions, self.native_receipt = self.native_parameters()
        self.tables = OriginalTables(self.catalog, lambda location: self.objects(location.package), descriptions)

    def objects(self, name):
        check(name in self.packages)
        row = self.packages[name]
        check(row['bytes'] <= blb.MAX_PACKAGE)
        url = hotfix.roots(self.build)['design'] + 'AssetBundles/' + name
        asset = hotfix.AudioFile(name, row['bytes'], row['md5'], url)
        # The ordinary acquisition validates the complete original package's
        # publisher size/MD5 before returning even this small requested range.
        asset.read(self.publisher, 0, min(32, row['bytes']))
        original = self.publisher / 'genshin-packages' / row['md5']
        check(original.stat().st_size == row['bytes'] and digest(original, 'md5') == row['md5'])
        owner = {'package': row, 'helper_identity': self.helper.identity,
                 'codec_sha256': self.parameter_receipt['parameters_sha256']}
        stem = identity(owner)
        home = self.directory / 'bodies'; home.mkdir(exist_ok=True)
        body, metadata = home / stem, home / (stem + '.json')
        _no_links(body); _no_links(metadata)
        valid = False
        try:
            receipt = json.loads(metadata.read_bytes())
            valid = (receipt['owner'] == owner and receipt['bytes'] == body.stat().st_size
                     and 0 < receipt['bytes'] <= blb.MAX_BODY and digest(body) == receipt['sha256'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if not valid:
            with tempfile.TemporaryDirectory(prefix='original-text-', dir=self.directory) as value:
                work = Path(value); decoded, pending = work / 'decoded', work / 'body'
                try:
                    self.helper.decode(original, self.parameters, decoded, work=work)
                    blb.unpack(decoded, pending)
                    # Validate the serialized container and map before caching it.
                    def read(offset, size):
                        with pending.open('rb') as stream:
                            stream.seek(offset); return stream.read(size)
                    DataObjects(pending.stat().st_size, read)
                except ValueError as error:
                    raise CodecRejected('The controlled codec could not decode this original publisher container.') from error
                receipt = {'owner': owner, 'bytes': pending.stat().st_size, 'sha256': digest(pending)}
                pending.replace(body)
                _atomic_file(metadata, json.dumps(receipt, sort_keys=True).encode())
        self.package_receipts[name] = {'publisher_md5': row['md5'], 'publisher_bytes': row['bytes'],
                                       'decoded_sha256': receipt['sha256'], 'decoded_bytes': receipt['bytes']}
        def read(offset, size):
            with body.open('rb') as stream:
                stream.seek(offset); return stream.read(size)
        return DataObjects(body.stat().st_size, read)

    def native_parameters(self):
        channel = self.build['channel']
        check(channel in {'genshin-global', 'genshin-cn'})
        name = 'GenshinImpact.exe' if channel == 'genshin-global' else 'YuanShen.exe'
        files = sophon.manifest(self.publisher, channel, tuple(self.build['manifests']['game']), ('.exe',))
        check(name in files)
        asset = files[name]
        check(type(asset.size) is int and 512 <= asset.size <= MAX_NATIVE and re.fullmatch('[a-f0-9]{32}', asset.digest))
        path = self.directory / ('native-' + asset.digest); _no_links(path)
        if not path.is_file() or path.stat().st_size != asset.size or digest(path, 'md5') != asset.digest:
            with tempfile.TemporaryDirectory(prefix='original-native-', dir=self.directory) as value:
                pending = Path(value) / 'native'
                with pending.open('xb') as stream:
                    for offset in range(0, asset.size, 8 * 1024**2):
                        raw = asset.read(self.publisher, offset, min(8 * 1024**2, asset.size - offset))
                        stream.write(raw)
                check(pending.stat().st_size == asset.size and digest(pending, 'md5') == asset.digest)
                pending.replace(path)
        native_sha256 = digest(path)
        owner = {'name': name, 'publisher_md5': asset.digest, 'bytes': asset.size, 'sha256': native_sha256,
                 'template_reader_sha256': digest(Path(__file__).with_name('genshin_original_textmap.py'))}
        profile = self.directory / ('native-profile-' + identity(owner) + '.private-json')
        _no_links(profile)
        descriptions = None
        try:
            saved = json.loads(profile.read_bytes())
            check(saved['owner'] == owner and 1 <= len(saved['descriptions']) <= 128)
            descriptions = tuple(NativeTextMapParameters(**row) for row in saved['descriptions'])
            check(len({row.fingerprint() for row in descriptions}) == 1)
        except (OSError, ValueError, KeyError, TypeError):
            descriptions = None
        if descriptions is None:
            descriptions = discover_native_parameters(Image(path.read_bytes()))
            _atomic_file(profile, json.dumps({'owner': owner, 'descriptions': [asdict(row) for row in descriptions]}, sort_keys=True).encode())
        return descriptions, {**owner, 'method_sha256s': sorted({row.method_sha256 for row in descriptions}),
                              'parameters_sha256': descriptions[0].fingerprint(), 'semantic_owner_claim': False}

    def file(self, relative):
        return self.tables.file(relative)

    def receipt(self):
        return {'schema': 'genshin-original-text-source-v1', 'publisher': self.stamp,
                'publisher_descriptor': dict(self.build), 'official_design_index_md5': self.index_md5,
                'official_design_index_sha256': self.index_sha256, 'catalog_sha256': self.catalog.sha256,
                'codec_description': self.parameter_receipt, 'helper_identity': self.helper.identity,
                'format_software': {name: digest(Path(__file__).with_name(name + '.py')) for name in
                    ('genshin_original_containers', 'genshin_official_text', 'genshin_official_source')},
                'native': self.native_receipt, 'locales': self.tables.receipts,
                'packages': dict(self.package_receipts)}


def prepare(directory, build):
    directory = Path(directory).absolute(); _no_links(directory); directory.mkdir(parents=True, exist_ok=True)
    helper = blb.helper(directory / 'helper')
    parameters, receipt = codec.load(directory / 'codec')
    try:
        return Source(directory, build, helper, parameters, receipt)
    except CodecRejected:
        # One controlled immutable community refresh is allowed. It supplies
        # data only; the same original official packages must still validate.
        parameters, fresh = codec.load(directory / 'codec', refresh=True)
        check(fresh['sha256'] != receipt['sha256'])
        return Source(directory, build, helper, parameters, fresh)
