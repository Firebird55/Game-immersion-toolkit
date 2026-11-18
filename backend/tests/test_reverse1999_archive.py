"""Authored Global 7z bootstrap data over the real scoped publisher transport."""
from contextlib import closing
from dataclasses import replace
from hashlib import md5, sha256
from io import BytesIO
import json
import lzma
import struct
import time
import zlib

import pytest

from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataError
from backend.publisher_transport import PublisherTransport
from backend.reverse1999_archive import BOOTSTRAP, RetainedRange, quote_bootstrap, verify_bootstrap
from backend.reverse1999_game_data import Reverse1999GameDataProvider
from backend.reverse1999_release import Archive
from backend.tests.test_game_data import Provider as AuthoredReadyProvider
from backend.tests.test_publisher_transport import Response
from backend.tests.test_reverse1999_bootstrap import fixture as unity_fixture
from backend.tests.test_reverse1999_provider import request
from backend.tests.test_reverse1999_release import encoded, fixture as launcher_fixture


def integer(value):
    for extra in range(8):
        if value < 1 << (7 + 7 * extra):
            lead = (256 - (256 >> extra)) | (value >> (extra * 8))
            return bytes((lead,)) + (value % (1 << (extra * 8))).to_bytes(extra, 'little')
    return b'\xff' + value.to_bytes(8, 'little')


def crc(value):
    return struct.pack('<I', zlib.crc32(value))


def stream_info(position, packed, unpacked, coder, footer):
    return (b'\x06' + integer(position) + b'\x01\x09' + integer(packed)
            + b'\x00\x07\x0b\x01\x00\x01' + coder + b'\x0c' + integer(unpacked) + footer)


def source(*, packed_header=False, bad_member_crc=False):
    asset = unity_fixture()
    sibling = b'authored preceding unnamed data'
    plain = sibling + asset
    pack = lzma.compress(plain, format=lzma.FORMAT_RAW,
                         filters=[{'id': lzma.FILTER_LZMA2, 'dict_size': 4096}])
    footer = b'\x00\x08\x0d\x02\x09' + integer(len(sibling)) + b'\x0a\x01' + crc(sibling)
    footer += (crc(asset) if not bad_member_crc else bytes(4)) + b'\x00\x00'
    names = b'\0' + ('fixture.txt\0' + BOOTSTRAP + '\0').encode('utf-16-le')
    header = (b'\x01\x04' + stream_info(0, len(pack), len(plain), b'\x21\x21\x01\x00', footer)
              + b'\x05\x02\x19\x01\x00\x11' + integer(len(names)) + names + b'\x19\x00\x00\x00')
    if packed_header:
        encoded_header = lzma.compress(header, format=lzma.FORMAT_RAW,
            filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': 4096, 'lc': 3, 'lp': 0, 'pb': 2}])
        props = b'\x5d' + (4096).to_bytes(4, 'little')
        next_header = b'\x17' + stream_info(len(pack), len(encoded_header), len(header),
            b'\x23\x03\x01\x01\x05' + props, b'\x0a\x01' + crc(header) + b'\x00\x00')
        pack, header = pack + encoded_header, next_header
    fields = struct.pack('<QQI', len(pack), len(header), zlib.crc32(header))
    raw = b'7z\xbc\xaf\x27\x1c\x00\x04' + crc(fields) + fields + pack + header
    digest = md5(raw, usedforsecurity=False).hexdigest()
    revision, version = '111.0.1065', '3.9.0'
    url = (f'https://download.bluepoch.com/en/game/{version}/'
           f'123_gameId_60001_pid_77_res_{revision}_app_{version}_total_{len(plain)}_origin_{len(plain)}'
           f'_size_{len(raw)}_md5_{digest}_0.7z')
    return Archive(url, len(raw), len(plain), digest, 0, revision), raw, asset


def archive_response(req, raw):
    requested = req.headers.get('Range')
    if requested is None:
        return Response(raw, url=req.full_url)
    low, high = map(int, requested.removeprefix('bytes=').split('-'))
    data = raw[low:high + 1]
    return Response(data, status=206, url=req.full_url, headers={
        'Content-Length': str(len(data)), 'Content-Range': f'bytes {low}-{high}/{len(raw)}'})


@pytest.mark.parametrize('packed_header', [False, True])
def test_verified_retained_partitions_fetch_only_missing_bytes(tmp_path, packed_header):
    archive, original, asset = source(packed_header=packed_header)
    quote = quote_bootstrap(lambda start, length: original[start:start + length], archive.size)
    first, last = 45, archive.size - 7
    fetches = []
    with closing(GameDataService(tmp_path, {})) as service:
        ctx = _Context(service, tmp_path, 'local', 'reverse1999', request(), tmp_path, 'download', budget=last - first)

        def opener(req, **_):
            fetches.append(req.headers['Range'])
            return archive_response(req, original)

        transport = PublisherTransport(ctx, hosts={'download.bluepoch.com'}, opener=opener)
        retained = [RetainedRange(last, 7, BytesIO(original[last:]).read),
                    RetainedRange(0, first, BytesIO(original[:first]).read)]
        result = verify_bootstrap(archive, quote, transport, retained=retained)
        assert result.raw_asset == asset and result.member.asset_sha256 == sha256(asset).hexdigest()
        assert result.archive_sha256 == sha256(original).hexdigest() and ctx.consumed == last - first
    assert fetches == [f'bytes={first}-{last - 1}']
    assert not list(tmp_path.rglob('resources.assets'))


@pytest.mark.parametrize('failure', ['archive_checksum', 'member_crc', 'retained_overlap', 'retained_truncated'])
def test_no_bootstrap_returned_on_broken_partition_or_identity(tmp_path, failure):
    archive, original, _ = source(bad_member_crc=failure == 'member_crc')
    quote = quote_bootstrap(lambda start, length: original[start:start + length], archive.size)
    retained = []
    if failure == 'archive_checksum':
        archive = replace(archive, md5='0' * 32)
    if failure == 'retained_overlap':
        retained = [RetainedRange(0, 8, BytesIO(original).read), RetainedRange(7, 8, BytesIO(original[7:]).read)]
    if failure == 'retained_truncated':
        retained = [RetainedRange(0, 8, BytesIO(original[:7]).read)]
    prior = tmp_path / 'previous-verified-bootstrap'
    prior.write_bytes(b'previous data')
    fetched = []
    with closing(GameDataService(tmp_path, {})) as service:
        ctx = _Context(service, tmp_path, 'local', 'reverse1999', request(), tmp_path, 'download', budget=archive.size)

        def opener(req, **_):
            fetched.append(req)
            return archive_response(req, original)

        transport = PublisherTransport(ctx, hosts={'download.bluepoch.com'}, opener=opener)
        with pytest.raises(ValueError):
            verify_bootstrap(archive, quote, transport, retained=retained)
    if failure.startswith('retained_'):
        assert not fetched
    assert prior.read_bytes() == b'previous data' and not list(tmp_path.rglob('resources.assets'))


def provider_for(archive, original, corrupt):
    launcher, _ = launcher_fixture()
    requests = []

    def opener(req, **_):
        requests.append(req)
        if req.full_url == archive.url:
            if corrupt[0] and 'Range' not in req.headers:
                return archive_response(req, original[:-1] + bytes((original[-1] ^ 1,)))
            return archive_response(req, original)
        if req.full_url.endswith('/diff-update/resource'):
            raw = encoded({'targetVersion': '3.9.0', 'fullPackage': {'packageUrls': [archive.url],
                'packageSize': archive.size, 'packageRealSize': archive.expanded_size}})
        else:
            raw = launcher(req.full_url, body=None if req.data is None else json.loads(req.data))
        return Response(raw, url=req.full_url)

    def transport(ctx, *, hosts):
        return PublisherTransport(ctx, hosts=hosts, opener=opener)

    return Reverse1999GameDataProvider(platform='windows', transport_factory=transport), requests


def finish(service):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        row = next(value for value in service.snapshot()['games'] if value['id'] == 'reverse1999')
        if row['job'] and row['job']['status'] not in {'queued', 'running'}:
            return row
        time.sleep(.01)
    raise AssertionError('Authored Global bootstrap did not finish')


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_shared_plan_and_download_publish_only_verified_preparatory_member(tmp_path, mode):
    archive, original, asset = source(packed_header=True)
    corrupt, activated = [False], []
    provider, opens = provider_for(archive, original, corrupt)
    with closing(GameDataService(tmp_path, {'reverse1999': provider}, on_activate=lambda *_: activated.append(True))) as service:
        selection = request(mode).json()
        plan = service.plan('reverse1999', selection)['game']
        assert plan['can_download'] and plan['download_bytes'] == archive.size and plan['state'] == 'not_downloaded'
        assert all(req.full_url != archive.url or 'Range' in req.headers for req in opens)
        service.download('reverse1999', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        result = finish(service)
        assert result['job']['status'] == 'needs_plan' and result['state'] == 'not_downloaded'
        assert not activated and not list(tmp_path.rglob('textmap.json')) and service.restore('reverse1999') is None
        pointer = tmp_path / 'reverse1999' / 'stage.json'
        assert not pointer.with_name('current.json').exists()
        old_pointer = pointer.read_bytes()
        assert json.loads(old_pointer)['ready'] is False
        saved, = tmp_path.rglob('resources.assets')
        assert saved.read_bytes() == asset

        before_recheck = len(opens)
        rechecked = service.plan('reverse1999', selection)['game']
        assert not rechecked['can_download'] and rechecked['download_bytes'] is None
        assert all(req.full_url != archive.url for req in opens[before_recheck:])

        saved.write_bytes(b'authored corrupt local asset')
        corrupt[0] = True
        new = service.plan('reverse1999', selection)['game']
        assert new['can_download']
        saved.write_bytes(asset)
        service.download('reverse1999', {'plan_id': new['plan_id'], 'revision': new['revision']})
        assert finish(service)['job']['status'] == 'failed'
        assert pointer.read_bytes() == old_pointer and saved.read_bytes() == asset
        saved.write_bytes(b'authored corrupt local asset')
        corrupt[0] = False
        repair = service.plan('reverse1999', selection)['game']
        assert repair['can_download']
        service.download('reverse1999', {'plan_id': repair['plan_id'], 'revision': repair['revision']})
        assert finish(service)['job']['status'] == 'needs_plan'
        previous, repaired = json.loads(old_pointer), json.loads(pointer.read_bytes())
        assert repaired['directory'] != previous['directory']
        repaired_member = saved.parent.parent / repaired['directory'] / saved.name
        assert repaired_member.read_bytes() == asset
        assert not activated and not any('optional' in req.full_url or req.full_url.endswith('.zip') for req in opens)


def test_verified_preparatory_stage_preserves_previous_ready_selection(tmp_path):
    class PriorReady(AuthoredReadyProvider):
        def download(self, plan, ctx):
            snapshot = super().download(plan, ctx)
            payload = json.loads(snapshot.snapshot_path.read_text(encoding='utf-8'))
            payload['game'] = ctx.game
            snapshot.snapshot_path.write_text(json.dumps(payload), encoding='utf-8')
            return snapshot

    selection = replace(request('text-audio'), source_locale='en', target_locales=('zh-Hans',)).json()
    ready_provider = PriorReady()
    with closing(GameDataService(tmp_path, {'reverse1999': ready_provider})) as service:
        ready = service.plan('reverse1999', selection)['game']
        service.download('reverse1999', {'plan_id': ready['plan_id'], 'revision': ready['revision']})
        result = finish(service)
        assert result['state'] == 'ready', result['message']

    current = tmp_path / 'reverse1999' / 'current.json'
    old_pointer = current.read_bytes()
    old_snapshot, = tmp_path.rglob('textmap.json')
    old_snapshot_bytes = old_snapshot.read_bytes()

    archive, original, asset = source(packed_header=True)
    provider, opens = provider_for(archive, original, [False])
    activated = []
    with closing(GameDataService(tmp_path, {'reverse1999': provider}, on_activate=lambda *_: activated.append(True))) as service:
        plan = service.plan('reverse1999', selection)['game']
        assert plan['can_download'] and plan['state'] == 'update_available'
        service.download('reverse1999', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        result = finish(service)
        assert result['job']['status'] == 'needs_plan' and result['state'] == 'update_available'
        assert result['installed_revision'] == ready['revision'] and result['installed_request'] == selection
        before_recheck = len(opens)
        rechecked = service.plan('reverse1999', selection)['game']
        assert not rechecked['can_download'] and all(req.full_url != archive.url for req in opens[before_recheck:])

    assert not activated and current.read_bytes() == old_pointer and old_snapshot.read_bytes() == old_snapshot_bytes
    stage = json.loads(current.with_name('stage.json').read_bytes())
    assert stage['ready'] is False
    assert (current.parent / 'cache' / 'sources' / stage['directory'] / 'resources.assets').read_bytes() == asset
    with closing(GameDataService(tmp_path, {'reverse1999': ready_provider})) as service:
        assert service.restore('reverse1999') is not None
