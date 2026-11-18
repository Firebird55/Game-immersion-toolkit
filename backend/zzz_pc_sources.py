"""Explicit original-file transport for consented ZZZ PC content stages.

Updater files require their entire advertised checksum, even for a small scene
range. Plans therefore charge whole selected containers; no archive/read call
may silently transfer bytes. Original data is never executable input.
"""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlsplit
from urllib.error import URLError

from . import hoyo_dispatch_metadata as metadata, hoyo_zzz_bootstrap as bootstrap, zzz_hotfix as hotfix, sophon_assets as sophon
from .game_data_protocol import GameDataError
from .publisher_transport import PublisherTransport
from .xxhash64 import xxhash64
from .zzz_game_data import _safe


class NeedsFiles(Exception):
    def __init__(self, files):
        self.files = tuple(files)
        super().__init__('Original source inputs need an explicit download plan')


@dataclass(frozen=True)
class OriginalFile:
    name: str
    size: int
    digest: int
    url: str
    base: object | None = field(default=None, repr=False)

    def json(self):
        return {'name': self.name, 'size': self.size, 'xxh64': str(self.digest),
                'transport': 'sophon' if self.base else 'updater',
                'url': self.url, 'file_md5': self.base.digest if self.base else None}


class Sources:
    def __init__(self, ctx, build, *, transport_factory=PublisherTransport):
        self.ctx, self.build, self.transport_factory = ctx, build, transport_factory
        self.cache = _safe(Path(ctx.cache_directory) / 'zzz-content' / ctx.request.region)
        self.host = hotfix.EDITIONS[build['channel']]['host']
        self._verified = {}
        self.bootstrap_cache = _safe(Path(ctx.cache_directory) / 'zzz-original' / ctx.request.region)
        self._base = None

    def path(self, asset):
        return _safe(self.cache / 'files' / f'{asset.digest:016x}-{asset.size}')

    def available(self, asset):
        self.ctx.check()
        path = self.path(asset)
        try:
            if not path.is_file() or path.stat().st_size != asset.size:
                return False
            stamp = hotfix._stamp(path.stat())
            key = str(path), asset.size, asset.digest, stamp, asset.base.digest if asset.base else None
            if key not in self._verified:
                verified = hotfix._check_file(path, asset.size, asset.digest, stamp)
                if asset.base:
                    with path.open('rb') as handle:
                        if hashlib.file_digest(handle, 'md5').hexdigest() != asset.base.digest:
                            return False
                self._verified[key] = verified
            return True
        except (OSError, ValueError):
            return False

    def read(self, asset, offset, count):
        self.ctx.check()
        if not (type(offset) is int and type(count) is int and 0 < count <= 64 * 1024**2
                and 0 <= offset <= asset.size - count):
            raise GameDataError('zzz_original_range', 'The original ZZZ scene range is invalid.')
        if not self.available(asset):
            raise NeedsFiles([asset])
        path = self.path(asset)
        stamp = hotfix._stamp(path.stat())
        stamp, blocks = self._verified[(str(path), asset.size, asset.digest, stamp, asset.base.digest if asset.base else None)]
        return hotfix._read_range(path, asset.size, offset, count, stamp, blocks)

    def download(self, assets, *, kind='asset'):
        transport = self.transport_factory(self.ctx, hosts={self.host})
        for asset in self.unique(assets):
            self.ctx.check()
            if self.available(asset):
                continue
            pending = _safe(self.cache / 'pending' / uuid.uuid4().hex)
            try:
                if asset.base:
                    pending.parent.mkdir(parents=True, exist_ok=True)
                    file_hash, count = hashlib.md5(), 0
                    def fetch(url, *, limit):
                        return transport.fetch_bytes(url, limit=limit, kind=kind)[0]
                    with pending.open('xb') as output:
                        for offset, size, compressed, identity, digest in asset.base.chunks:
                            self.ctx.check()
                            _safe(self.bootstrap_cache / 'chunks' / digest)
                            raw = sophon._verified(self.bootstrap_cache / 'chunks',
                                asset.base.prefix + '/' + identity, compressed, size, digest, sophon.MAX_CHUNK, fetch=fetch)
                            if offset != count:
                                raise GameDataError('zzz_original_range', 'The original ZZZ container layout changed.')
                            output.write(raw); file_hash.update(raw); count += len(raw)
                    if count != asset.size or file_hash.hexdigest() != asset.base.digest:
                        raise GameDataError('publisher_checksum_mismatch', 'The original ZZZ base file failed its checksum.')
                else:
                    transport.download_to(asset.url, pending, limit=asset.size, expected_size=asset.size, kind=kind)
                stamp, blocks = hotfix._check_file(pending, asset.size, asset.digest)
                destination = self.path(asset)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self.ctx.check()
                pending.replace(destination)
                stamp = hotfix._stamp(destination.stat())
                self._verified[(str(destination), asset.size, asset.digest, stamp, asset.base.digest if asset.base else None)] = (stamp, blocks)
            finally:
                if pending.exists():pending.unlink()

    @staticmethod
    def unique(assets):
        result = {}
        for asset in assets:
            key = asset.name, asset.digest, asset.size
            if key in result and result[key].json() != asset.json():
                # Identical original bytes may have multiple authored names.
                # Pick a stable original URL; never deduplicate different sizes.
                raise GameDataError('zzz_source_identity_changed', 'Original ZZZ sources have conflicting ownership.')
            else:result[key] = asset
        return tuple(result[key] for key in sorted(result))

    def quote(self, assets, *, scratch_bytes=0):
        selected = self.unique(assets)
        missing = [asset for asset in selected if not self.available(asset)]
        chunks = {}
        for asset in missing:
            if not asset.base:continue
            for _, size, compressed, identity, digest in asset.base.chunks:
                path = _safe(self.bootstrap_cache / 'chunks' / digest)
                good = False
                if path.is_file() and path.stat().st_size == size:
                    with path.open('rb') as handle:good = hashlib.file_digest(handle, 'md5').hexdigest() == digest
                if not good:
                    if digest in chunks and chunks[digest][0] != size:
                        raise GameDataError('zzz_source_identity_changed', 'Original ZZZ chunk sizes disagree.')
                    chunks[digest] = (size, max(compressed, chunks.get(digest, (0, 0))[1]))
        network = sum(asset.size for asset in missing if not asset.base) + sum(row[1] for row in chunks.values())
        disk = sum(asset.size for asset in missing) + sum(row[0] for row in chunks.values())
        disk += max([0, *(asset.size for asset in missing), *(row[0] for row in chunks.values())]) + scratch_bytes + 1024**2
        return [asset.json() for asset in selected], network, disk

    def index_file(self, name):
        root, filename = hotfix.INDEXES[name]
        spec = self.build['hotfix']['indexes'][name]
        hotfix.check(spec['name'] == filename)
        url = self.build['hotfix']['roots'][root] + filename
        return OriginalFile(filename, spec['size'], int(spec['hash']), url)

    def indexes(self, names):
        assets = [self.index_file(name) for name in names]
        missing = [asset for asset in assets if not self.available(asset)]
        if sum(asset.size for asset in self.unique(missing)) > self.ctx.remaining_bytes(kind='metadata'):
            raise NeedsFiles(missing)
        self.download(missing, kind='metadata')
        return {name: hotfix.inventory_rows(self.read(asset, 0, asset.size)) for name, asset in zip(names, assets)}

    def asset(self, row):
        if not row['isPatch']:
            if self._base is None:
                def no_fetch(*a, **k):raise GameDataError('zzz_manifest_changed', 'Check the original ZZZ source manifest again.', 409)
                spec = tuple(self.build['manifests']['game'])
                _safe(self.bootstrap_cache / 'manifests' / spec[4])
                self._base = sophon.manifest(self.bootstrap_cache, self.build['channel'], spec, ('.blk',), fetch=no_fetch)
            original = self._base.get(hotfix.BASE + row['remoteName'])
            if original:
                hotfix.check(original.size == row['fileSize'])
                return OriginalFile(original.name, original.size, int(row['md5']), '', original)
        original = hotfix.resource(self.build, row)
        return OriginalFile(original.name, original.size, original.digest, original.url)


def discover(ctx, build, bootstrap_cache, *, transport_factory=PublisherTransport, crypto=None):
    """Current official discovery with caller-owned byte/host/cancellation gates."""
    config = bootstrap.official(build, ctx.request.region, bootstrap_cache,
        fetch=lambda *a, **k: (_ for _ in ()).throw(GameDataError('zzz_bootstrap_changed', 'Check the original ZZZ bootstrap source again.', 409)))
    fields = metadata.OfficialFields()
    values = {name: fields.text(config[name]) for name in ('GameDispatchChannelName', 'ProtoDispatchKey')}
    values.update(endpoints=[fields.text(value) for value in config['GameDispatchArrayURL']],
                  bootstrap_provenance=metadata.provenance(config), gateway_keys=config['_official_gateway_keys'])
    def request(url, headers, maximum):
        parsed = urlsplit(url)
        hotfix._endpoint(url.split('?', 1)[0], gateway=parsed.path == '/query_gateway', channel=build['channel'])
        transport = transport_factory(ctx, hosts={parsed.hostname})
        try:return transport.fetch_bytes(url, limit=maximum, kind='metadata', headers=headers)[0]
        except GameDataError as error:
            if error.code == 'metadata_download_interrupted':raise URLError('Official ZZZ endpoint unavailable') from error
            raise
    reply, proof = hotfix._negotiate(values, build, request=request, crypto=crypto, cancelled=ctx.check)
    current = hotfix.configuration(build, reply, proof)
    sources = Sources(ctx, current, transport_factory=transport_factory)
    asset = sources.index_file('base')
    if asset.size > 256:raise GameDataError('zzz_base_revision', 'The original ZZZ base revision metadata changed.')
    sources.download([asset], kind='metadata')
    base = sources.read(asset, 0, asset.size).decode('ascii')
    hotfix.check(re.fullmatch('[1-9][0-9]*_[0-9a-f]{6,64}', base))
    return current | {'hotfix': current['hotfix'] | {'base_revision': base}}
