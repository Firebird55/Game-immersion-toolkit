"""Publisher-authenticated audio ranges, acquired only by explicit plans.

SDK ranges are authenticated by their complete original transport chunks.
Updater ranges require the entire advertised file hash. Both costs include
co-resident bytes; synthetic access windows never become download estimates.
"""
from bisect import bisect_right
import re

from . import sophon_assets as sophon, zzz_hotfix as hotfix
from .game_data_protocol import GameDataError
from .publisher_transport import PublisherTransport
from .zzz_dialogue_records import VOICE_FOLDERS
from .zzz_game_data import _safe, _valid_file
from .zzz_pc_sources import Sources, OriginalFile


class MissingAudio(Exception):
    """A local read needs a new explicit source range plan."""
    def __init__(self, ranges):
        self.ranges = tuple(ranges)
        super().__init__('Original audio ranges need a consented download')


class AudioSources(Sources):
    def __init__(self, ctx, build, locale, *, transport_factory=PublisherTransport, verification=None):
        if ctx.request.content_mode != 'text-audio':
            raise GameDataError('zzz_audio_not_requested', 'Select text and audio before accessing original voice sources.')
        if build.get('channel') != 'zzz-' + ctx.request.region:
            raise GameDataError('zzz_audio_region_changed', 'Choose the matching original ZZZ regional source.', 409)
        if locale not in sophon.VOICE_FIELDS:
            raise GameDataError('zzz_audio_locale', 'Choose an official ZZZ dub.')
        super().__init__(ctx, build, transport_factory=transport_factory)
        self.locale = locale
        self._audio_chunks = set() if verification is None else verification.setdefault('chunks', set())
        if verification is not None:self._verified = verification.setdefault('files', {})
        self._game_files = None

    @property
    def voice_spec(self):
        return tuple(self.build['manifests'][sophon.VOICE_FIELDS[self.locale]])

    def inputs_available(self):
        spec = self.voice_spec
        return (_valid_file(self.bootstrap_cache / 'manifests' / spec[4], spec[4], spec[3])
                and self.available(self.index_file('audio'))
                and all(self._chunk_available(row[4], row[1]) for asset in self._markers().values() for row in asset.chunks))

    def _game(self):
        if self._game_files is None:
            spec = tuple(self.build['manifests']['game'])
            _safe(self.bootstrap_cache / 'manifests' / spec[4])
            def no_fetch(*args, **kwargs):
                raise GameDataError('zzz_audio_source_changed', 'The original game manifest changed. Check its size again.', 409)
            self._game_files = sophon.manifest(self.bootstrap_cache, self.build['channel'], spec, ('.pck', 'revision'), fetch=no_fetch)
        return self._game_files

    def _markers(self):
        game = self._game();result = {}
        for name in ('audio_revision', 'data_revision', 'res_revision', 'silence_revision'):
            asset = game.get(hotfix.BASE + name)
            if asset is None or not 0 < asset.size <= 32:
                raise GameDataError('zzz_audio_base_identity', 'The original launcher base identity is unavailable.', 409)
            result[name] = asset
        return result

    def _base_matches(self):
        expected = self.build['hotfix']['base_revision'].split('_', 1)[0].encode('ascii')
        def no_fetch(*args, **kwargs):
            raise GameDataError('zzz_audio_source_changed', 'The local launcher identity changed. Check its size again.', 409)
        return all(asset.read(self.bootstrap_cache, 0, asset.size, fetch=no_fetch) == expected for asset in self._markers().values())

    def quote_inputs(self):
        spec = self.voice_spec
        if not 0 < spec[2] <= sophon.MAX_MANIFEST or not 0 < spec[3] <= sophon.MAX_MANIFEST:
            raise GameDataError('zzz_audio_manifest_bounds', 'The original dub manifest exceeds its supported bounds.')
        _, network, disk = self.quote([self.index_file('audio')])
        if not _valid_file(self.bootstrap_cache / 'manifests' / spec[4], spec[4], spec[3]):
            network += spec[2];disk += spec[3] * 2
        chunks = {}
        for asset in self._markers().values():
            for row in asset.chunks:
                previous = chunks.get(row[4])
                if previous is not None and previous[1] != row[1]:
                    raise GameDataError('zzz_audio_base_identity', 'Original launcher identity chunk sizes disagree.')
                if previous is None or row[2] > previous[2]:chunks[row[4]] = row
        missing = [row for row in chunks.values() if not self._chunk_available(row[4], row[1])]
        network += sum(row[2] for row in missing)
        disk += sum(row[1] for row in missing) + max((row[1] for row in missing), default=0)
        return network, disk

    def download_inputs(self):
        spec = self.voice_spec
        transport = self.transport_factory(self.ctx, hosts={self.host})
        def fetch(url, *, limit):
            if url != spec[0] + '/' + spec[1]:
                raise GameDataError('zzz_audio_source_changed', 'Check the selected ZZZ dub source again.', 409)
            return transport.fetch_bytes(url, limit=limit, kind='audio')[0]
        _safe(self.bootstrap_cache / 'manifests' / spec[4])
        sophon.manifest(self.bootstrap_cache, self.build['channel'], spec, ('.pck',), fetch=fetch)
        self.download([self.index_file('audio')], kind='audio')
        for asset in self._markers().values():
            for _, expanded, compressed, identity, digest in asset.chunks:
                self.ctx.check();_safe(self.bootstrap_cache / 'chunks' / digest)
                sophon._verified(self.bootstrap_cache / 'chunks', asset.prefix + '/' + identity,
                    compressed, expanded, digest, sophon.MAX_CHUNK,
                    fetch=lambda url, *, limit: transport.fetch_bytes(url, limit=limit, kind='audio')[0])

    def assets(self):
        if not self.inputs_available():
            raise GameDataError('zzz_audio_inputs_missing', 'Check the original ZZZ audio indexes before continuing.', 409)
        def no_fetch(*args, **kwargs):
            raise GameDataError('zzz_audio_source_changed', 'The cached ZZZ manifest changed. Check its size again.', 409)
        voice = sophon.manifest(self.bootstrap_cache, self.build['channel'], self.voice_spec, ('.pck',), fetch=no_fetch)
        game = self._game()
        matching_base = self._base_matches()
        index = self.index_file('audio')
        # An index is metadata, never a range-read audio container.
        raw = Sources.read(self, index, 0, index.size)
        pattern = r'Audio/Windows/Full/(?:' + re.escape(VOICE_FOLDERS[self.locale]) + r'/)?[A-Za-z0-9_.-]+\.pck'
        files = {}
        for row in hotfix.inventory_rows(raw):
            if not re.fullmatch(pattern, row['remoteName']):continue
            # During a publisher rollout, HYP can still advertise another base.
            # The updater's own immutable base URL/checksum then owns the bytes.
            sdk = None if row['isPatch'] or not matching_base else voice.get(hotfix.BASE + row['remoteName']) or game.get(hotfix.BASE + row['remoteName'])
            if sdk and sdk.size != row['fileSize']:sdk = None
            if sdk:
                asset = OriginalFile(sdk.name, sdk.size, int(row['md5']), '', sdk)
            else:
                source = hotfix.resource(self.build, row)
                asset = OriginalFile(source.name, source.size, source.digest, source.url)
            if asset.name in files:
                raise GameDataError('zzz_audio_source_changed', 'Original ZZZ audio owners are ambiguous.')
            files[asset.name] = asset
        if not files:raise GameDataError('zzz_audio_missing', 'The selected original ZZZ voice packages are unavailable.')
        return files

    def _ranges(self, files, ranges):
        selected = {}
        for index, row in enumerate(ranges):
            if index % 256 == 0:self.ctx.check()
            if not isinstance(row, dict) or row.get('name') not in files:
                raise GameDataError('zzz_audio_range_owner', 'The original ZZZ audio range has no selected owner.')
            asset = files[row['name']]
            start, size = row.get('offset'), row.get('size')
            if (type(start) is not int or type(size) is not int or not 0 < size <= 64 * 1024**2
                    or not 0 <= start <= asset.size - size):
                raise GameDataError('zzz_audio_range_owner', 'The original ZZZ audio range leaves its owner.')
            selected[asset.name, start, size] = (asset, start, size)
        return [selected[key] for key in sorted(selected)]

    def _chunks(self, asset, start, size):
        chunks = asset.base.chunks
        first = max(0, bisect_right(chunks, start, key=lambda chunk: chunk[0]) - 1)
        last = bisect_right(chunks, start + size - 1, lo=first, key=lambda chunk: chunk[0])
        return chunks[first:last]

    def _chunk_available(self, digest, size):
        path = _safe(self.bootstrap_cache / 'chunks' / digest)
        try:
            stamp = hotfix._stamp(path.stat())
            key = digest, size, stamp
            if key in self._audio_chunks:return True
            if _valid_file(path, digest, size):
                self._audio_chunks.add(key)
                return True
        except OSError:pass
        return False

    def quote_ranges(self, files, ranges, *, scratch_bytes=0):
        selected = self._ranges(files, ranges)
        patches, chunks = self._range_sources(selected)
        _, network, disk = self.quote(patches)
        missing = [row for digest, row in chunks.items() if not self._chunk_available(digest, row[0])]
        network += sum(row[1] for row in missing)
        disk += sum(row[0] for row in missing) + max((row[0] for row in missing), default=0) + scratch_bytes
        return network, disk

    def ranges_available(self, files, ranges):
        return self.quote_ranges(files, ranges)[0] == 0

    def _range_sources(self, selected):
        patches = {asset.name: asset for asset, _, _ in selected if not asset.base}
        chunks = self.chunks((asset, chunk) for asset, start, size in selected if asset.base
                             for chunk in self._chunks(asset, start, size))
        return patches.values(), chunks

    def download_ranges(self, files, ranges):
        patches, chunks = self._range_sources(self._ranges(files, ranges))
        self._download_batch(patches, chunks, kind='audio')

    def read(self, asset, start, size):
        row = {'name': asset.name, 'offset': start, 'size': size}
        self._ranges({asset.name: asset}, [row])
        self.ctx.check()
        if not asset.base:
            if not self.available(asset):raise MissingAudio([row])
            return super().read(asset, start, size)
        if any(not self._chunk_available(chunk[4], chunk[1]) for chunk in self._chunks(asset, start, size)):
            raise MissingAudio([row])
        def no_fetch(*args, **kwargs):
            raise GameDataError('zzz_audio_source_changed', 'The local original ZZZ recording changed. Check its size again.', 409)
        return asset.base.read(self.bootstrap_cache, start, size, fetch=no_fetch)
