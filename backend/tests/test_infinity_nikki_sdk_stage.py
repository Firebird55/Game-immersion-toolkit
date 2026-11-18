"""Ordinary native-stage -> original launcher-stage fixtures, no real source I/O.

The authored PE has a scoped signature fixture. Actual shared WinTrust checks
and separately recorded original-source replay establish different evidence.
"""
from dataclasses import replace
import hashlib
import json
import struct

import pytest

from backend import infinity_nikki_sdk_stage as sdk
from backend import infinitynikki_game_data as source
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage, SnapshotSource
from backend.publisher_transport import PublisherTransport
from backend.tests.test_infinitynikki_game_data import Fixture as Native, apk_fixture
from backend.tests.test_infinity_nikki_bootstrap import resource_fixture, nsis_fixture, deflate, frame
from backend.tests.test_publisher_transport import Response


class Fixture(Native):
    def __init__(self, root, apk, monkeypatch, *, mode='text'):
        super().__init__(root, apk, mode=mode)
        member, _, _ = resource_fixture()
        self.member = member+b'authored inert PE padding'*30
        compressed = deflate(self.member)
        self.member_block = struct.pack('<I', len(compressed)|0x80000000)+compressed
        data = bytearray(128*1024)
        data[:2] = b'MZ'
        struct.pack_into('<I', data, 60, 64)
        data[64:68] = b'PE\0\0'
        struct.pack_into('<H', data, 70, 1)
        struct.pack_into('<H', data, 84, 2)
        struct.pack_into('<H', data, 88, 0x10b)
        struct.pack_into('<II', data, 90+16, 64*1024-512, 512)
        header = nsis_fixture(('xstarter.exe',))
        packed = deflate(header)
        data[65536:65568] = frame(header, packed, True)
        data[65568:65568+len(packed)] = packed
        self.member_offset = 65568+len(packed)+1000
        data[self.member_offset:self.member_offset+len(self.member_block)] = self.member_block
        self.sdk_data = bytes(data)
        self.sdk_url = 'https://x6oversea-game-package.infoldgames.com/xstarter/402/authored-current.exe'
        self.sdk_etag = '"authored-sdk-one"'
        self.sdk_fail = self.sdk_corrupt = self.sdk_cancel = self.bad_signature = False
        def verify(path):
            raw = path.read_bytes()
            if self.bad_signature or raw != self.member:
                raise ValueError('Authored signature does not match this source.')
            return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                'publisher': 'Suzhou Nikki Co.,Ltd.', 'verification': 'Windows offline Authenticode',
                'online_revocation_freshness': False}
        monkeypatch.setattr(sdk, '_verify', verify)
        monkeypatch.setattr(sdk, '_runtime', lambda platform: platform in {'windows', 'desktop'})

    def transport(self, ctx, *, hosts):
        assert ctx is self.ctx
        assert set(hosts) <= {source.APK_HOST, 'infinitynikki.nuanpaper.com',
                             'infinitynikki.infoldgames.com', 'x6oversea-game-package.infoldgames.com'}
        owner = self
        class Transport(PublisherTransport):
            def fetch_bytes(self, *args, **kwargs):
                owner.kinds.append(kwargs['kind'])
                return super().fetch_bytes(*args, **kwargs)
            def consume_stream(self, *args, **kwargs):
                owner.kinds.append(kwargs['kind'])
                return super().consume_stream(*args, **kwargs)
        return Transport(ctx, hosts=hosts, opener=self.open)

    def open(self, request, **options):
        url = request.full_url
        if url == 'https://infinitynikki.infoldgames.com/en/home':
            self.calls.append((url, None))
            page = {'props': {'pageProps': {'pageData': {'page': {'windowsUrl': [
                {'__type': 'text', 'value': self.sdk_url}]}}}}}
            raw = ('<script id="__NEXT_DATA__" type="application/json">'+json.dumps(page)+'</script>').encode()
            return Response(raw, headers={'Content-Length': str(len(raw))}, url=url)
        if url != self.sdk_url:
            return super().open(request, **options)
        span = request.get_header('Range')
        self.calls.append((url, span))
        assert span is not None, 'The complete installer is outside this source plan.'
        start, end = map(int, span.removeprefix('bytes=').split('-'))
        data = self.sdk_data[start:end+1]
        full = start == self.member_offset and len(data) == len(self.member_block)
        if full and self.sdk_fail:
            data = data[:-1]
        if full and self.sdk_corrupt:
            data = data[:8]+bytes([data[8]^1])+data[9:]
        headers = {'Content-Length': str(end+1-start), 'ETag': self.sdk_etag,
                   'Content-Range': f'bytes {start}-{end}/{len(self.sdk_data)}'}
        owner = self
        class Stream(Response):
            def read(self, size=-1):
                raw = super().read(size)
                if full and owner.sdk_cancel:
                    owner.ctx.cancel.set()
                return raw
        return Stream(data, status=206, headers=headers, url=url)

    def native_stage(self):
        return self.download(self.provider.plan(self.request, self.ctx)).restore_handle

    def launcher_plan(self):
        previous = self.native_stage()
        self.context('plan').stage_handle = previous
        return self.provider.plan(self.request, self.ctx)


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_ordinary_provider_quotes_selected_original_then_retains_verified_source_and_an_explicit_next_gate(tmp_path, apk_fixture, monkeypatch, mode):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch, mode=mode)
    plan = fixture.launcher_plan()
    assert plan.stage == 'global-launcher-bootstrap' and plan.runtime_available
    assert plan.download_bytes == len(fixture.member_block)+4
    assert plan.download_is_upper_bound and plan.required_disk_bytes > len(fixture.member)
    body_range = f'bytes={fixture.member_offset}-{fixture.member_offset+len(fixture.member_block)-1}'
    assert (fixture.sdk_url, body_range) not in fixture.calls
    result = fixture.download(plan)
    assert isinstance(result, PreparationStage) and not isinstance(result, SnapshotSource)
    assert result.restore_handle['stage'] == 'global-sdk-source'
    assert result.restore_handle['request']['content_mode'] == mode
    assert fixture.ctx.stage_handle is None
    assert (fixture.sdk_url, body_range) in fixture.calls
    assert 'audio' not in fixture.kinds
    pe = list(fixture.ctx.cache_directory.rglob('*.pe'))
    assert len(pe) == 1 and pe[0].read_bytes() == fixture.member
    assert not list(fixture.ctx.cache_directory.rglob('pending-*'))
    fixture.context('plan').stage_handle = result.restore_handle
    before = len(fixture.calls)
    gate = fixture.provider.plan(fixture.request, fixture.ctx)
    assert gate.stage == 'global-sdk-source' and gate.download_bytes == 0 and not gate.runtime_available
    assert gate.source_proof is None and len(fixture.calls) == before
    with pytest.raises(GameDataError) as failure:
        fixture.download(gate)
    assert failure.value.code == 'publisher_sdk_reader_unresolved' and len(fixture.calls) == before
    with pytest.raises(GameDataError) as failure:
        fixture.provider.restore(result.restore_handle, fixture.context('restore'))
    assert failure.value.code == 'publisher_sdk_reader_unresolved' and len(fixture.calls) == before


@pytest.mark.parametrize('change', ['download_bytes', 'required_disk_bytes', 'revision', 'source_proof', 'request', 'artifact'])
def test_modified_consent_or_metadata_refuses_before_member_transfer(tmp_path, apk_fixture, monkeypatch, change):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch)
    plan = fixture.launcher_plan()
    before = len(fixture.calls)
    if change == 'request':
        fixture.request = GameDataRequest('global', 'ja', (), 'text')
    elif change == 'artifact':
        path = sdk._path(fixture.ctx, plan.handle['receipt_sha256'])
        path.write_bytes(path.read_bytes()+b' ')
    else:
        replacement = {'download_bytes': plan.download_bytes+1, 'required_disk_bytes': plan.required_disk_bytes+1,
                       'revision': 'different', 'source_proof': object()}[change]
        plan = replace(plan, **{change: replacement})
    with pytest.raises(GameDataError):
        fixture.download(plan)
    assert len(fixture.calls) == before
    assert not list(fixture.ctx.cache_directory.rglob('*.pe'))


@pytest.mark.parametrize('failure', ['etag', 'truncated', 'corrupt', 'cancelled', 'signature'])
def test_changed_failed_or_cancelled_source_preserves_existing_data(tmp_path, apk_fixture, monkeypatch, failure):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch)
    plan = fixture.launcher_plan()
    old = tmp_path/'existing-language-and-recordings.dat'
    old.write_bytes(b'authored previous data')
    if failure == 'etag': fixture.sdk_etag = '"another-source-generation"'
    if failure == 'truncated': fixture.sdk_fail = True
    if failure == 'corrupt': fixture.sdk_corrupt = True
    if failure == 'cancelled': fixture.sdk_cancel = True
    if failure == 'signature': fixture.bad_signature = True
    with pytest.raises(GameDataError):
        fixture.download(plan)
    assert old.read_bytes() == b'authored previous data'
    assert not list(fixture.ctx.cache_directory.rglob('*.pe'))
    assert not list(fixture.ctx.cache_directory.rglob('pending-*'))


def test_requote_rediscovers_the_current_publisher_validator(tmp_path, apk_fixture, monkeypatch):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch)
    first = fixture.launcher_plan()
    fixture.sdk_etag = '"another-source-generation"'
    fixture.context('plan').stage_handle = first.handle
    second = fixture.provider.plan(fixture.request, fixture.ctx)
    assert first.handle != second.handle and first.revision != second.revision
    with pytest.raises(GameDataError): fixture.download(first)
    assert isinstance(fixture.download(second), PreparationStage)


def test_android_signature_gate_cannot_fall_back_to_the_pc_verifier(tmp_path, apk_fixture, monkeypatch):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch)
    previous = fixture.native_stage()
    fixture.provider.platform = 'android'
    fixture.context('plan').stage_handle = previous
    plan = fixture.provider.plan(fixture.request, fixture.ctx)
    assert plan.stage == 'global-launcher-bootstrap' and not plan.runtime_available
    before = len(fixture.calls)
    with pytest.raises(GameDataError) as failure:
        fixture.download(plan)
    assert failure.value.code == 'game_runtime_unavailable' and len(fixture.calls) == before


def test_retained_source_tampering_is_detected_without_network(tmp_path, apk_fixture, monkeypatch):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch)
    result = fixture.download(fixture.launcher_plan())
    pe = next(fixture.ctx.cache_directory.rglob('*.pe'))
    pe.write_bytes(pe.read_bytes()+b'damaged')
    before = len(fixture.calls)
    fixture.context('plan').stage_handle = result.restore_handle
    with pytest.raises(GameDataError): fixture.provider.plan(fixture.request, fixture.ctx)
    assert len(fixture.calls) == before


def test_mainland_metadata_is_an_explicit_gate_without_borrowing_global_profiles(tmp_path, apk_fixture, monkeypatch):
    fixture = Fixture(tmp_path, apk_fixture, monkeypatch)
    fixture.request = GameDataRequest('cn', 'en', ('ja',), 'text')
    fixture.context('plan')
    previous = fixture.native_stage()
    before = len(fixture.calls)
    fixture.context('plan').stage_handle = previous
    gate = fixture.provider.plan(fixture.request, fixture.ctx)
    assert gate.stage == 'content-reader' and not gate.runtime_available and gate.download_bytes == 0
    assert 'mainland metadata' in gate.message and len(fixture.calls) == before
