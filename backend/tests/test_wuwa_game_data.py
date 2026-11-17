"""Shared-budget bootstrap staging never pretends to be a prepared library."""
from email.message import Message
import io
import json
from pathlib import Path
import threading
import time

import pytest

from backend import wuwa_game_data as provider
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage
from backend.publisher_transport import PublisherTransport
from backend.tests.test_wuthering_native_bootstrap import source, signed_game, signing_key, URL


contexts = []


def Context(root, mode='text'):
    from backend.game_data import GameDataService, _Context
    service = GameDataService(root, {})
    contexts.append(service)
    return _Context(service, root, 'local', 'wuwa',
        GameDataRequest('global', 'ja', ('en', 'zh-Hans'), mode), root / 'generation', 'plan')


@pytest.fixture(autouse=True)
def close_contexts():
    yield
    while contexts:
        contexts.pop().close()


class Response(io.BytesIO):
    def __init__(self, data, url, status=200, headers=None, *, on_read=lambda: None):
        super().__init__(data)
        self.url, self.status, self.headers, self.on_read = url, status, Message(), on_read
        for key, value in (headers or {}).items(): self.headers[key] = value
    def geturl(self): return self.url
    def read(self, count):
        value = super().read(min(count, 173))
        self.on_read()
        return value


@pytest.fixture
def original(tmp_path, monkeypatch, signing_key):
    _ref, module = source(tmp_path)
    apk = signed_game(module, signing_key)
    calls, controls = [], {'corrupt': False, 'cancel': None, 'offline': False}
    def open_(request, **kwargs):
        if controls['offline']: pytest.fail('This operation must remain offline')
        url = request.full_url
        calls.append(request)
        if url.startswith(provider._source().CATALOGUE + '?_t='):
            raw = json.dumps({'primary': URL, 'version': '1.0.0'}).encode()
            return Response(raw, url, headers={'Content-Length': str(len(raw))})
        assert url == URL
        carrier = controls.get('carrier') or apk
        headers = {'ETag': '"original"'}
        if request.get_header('Range'):
            start, end = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            headers.update({'Content-Range': f'bytes {start}-{end}/{len(carrier)}', 'Content-Length': str(end-start+1)})
            return Response(carrier[start:end+1], url, 206, headers)
        raw = bytearray(carrier)
        if controls['corrupt']: raw[-23] ^= 1
        headers['Content-Length'] = str(len(raw))
        def on_read():
            if controls['cancel'] is not None: controls['cancel'].cancel.set()
        return Response(bytes(raw), url, headers=headers, on_read=on_read)
    controls['transport_factory'] = lambda ctx, **kwargs: PublisherTransport(ctx, opener=open_, **kwargs)
    monkeypatch.setattr(provider, 'PublisherTransport', controls['transport_factory'])
    # This lane must not touch legacy seeds, protected ownership, or processes.
    from backend import wuthering_metadata
    monkeypatch.setattr(wuthering_metadata, '_read', lambda *a: pytest.fail('No protected bootstrap input'))
    # Host-only simulation supplies the maintained desktop reference explicitly;
    # actual Android capability/absence is exercised separately.
    from backend.publisher_crypto import DesktopPublisherCrypto
    controls['maintained_crypto'] = provider.WutheringGameDataProvider._crypto
    monkeypatch.setattr(provider.WutheringGameDataProvider, '_crypto', lambda self: DesktopPublisherCrypto())
    return module, apk, calls, controls


@pytest.mark.parametrize('platform', ['desktop', 'android'])
@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_real_shared_transport_full_integrity_stage_then_honest_format_gate(tmp_path, original, platform, mode):
    module, apk, calls, controls = original
    ctx = Context(tmp_path, mode)
    adapter = provider.create_provider(platform, object())
    plan = adapter.plan(ctx.request, ctx)
    assert plan.download_bytes == len(apk) and plan.required_disk_bytes >= len(module)
    assert plan.stage == 'bootstrap' and plan.runtime_available and plan.source_proof is None
    assert all(request.get_header('Range') or request.full_url.startswith(provider._source().CATALOGUE) for request in calls)
    assert 'packaged media' in plan.message and 'optional voice pack' in plan.message
    ctx.phase, ctx.consumed, ctx.budget = 'download', 0, plan.download_bytes
    stage = adapter.download(plan, ctx)
    assert isinstance(stage, PreparationStage) and ctx.consumed == len(apk)
    path = provider._source()._module(ctx.cache_directory, stage.restore_handle['source'])
    assert path.read_bytes() == module
    assert not list(ctx.cache_directory.rglob('*.deflate')) and not list(ctx.cache_directory.rglob('*.apk'))
    controls['offline'] = True
    ctx.phase, ctx.stage_handle = 'plan', stage.restore_handle
    gate = adapter.plan(ctx.request, ctx)
    assert gate.stage == 'manifest-format' and not gate.runtime_available and gate.source_proof is None
    with pytest.raises(GameDataError) as failure: adapter.restore(stage.restore_handle, ctx)
    assert failure.value.code == 'publisher_format_key_unresolved'


@pytest.mark.parametrize('fault', ['corrupt', 'cancel', 'budget'])
def test_full_carrier_failure_keeps_old_data_and_cleans_provisional_member(tmp_path, original, fault):
    _module, _apk, _calls, controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request, ctx)
    marker = ctx.cache_directory / 'retained-index-and-audio'
    marker.write_bytes(b'complete old library')
    ctx.phase, ctx.consumed, ctx.budget = 'download', 0, plan.download_bytes
    if fault == 'corrupt': controls['corrupt'] = True
    elif fault == 'cancel': controls['cancel'] = ctx
    else: ctx.budget -= 1
    with pytest.raises((ValueError, GameDataError)): adapter.download(plan, ctx)
    assert marker.read_bytes() == b'complete old library'
    assert not list(ctx.cache_directory.rglob('module.so'))
    assert not list(ctx.cache_directory.rglob('pending-*'))
    if fault == 'cancel': assert ctx.consumed > 0


def test_corrupt_retained_native_stage_is_not_ready_or_an_automatic_redownload(tmp_path, original):
    _module, _apk, _calls, controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('desktop')
    plan = adapter.plan(ctx.request, ctx)
    ctx.phase, ctx.consumed, ctx.budget = 'download', 0, plan.download_bytes
    stage = adapter.download(plan, ctx)
    path = provider._source()._module(ctx.cache_directory, stage.restore_handle['source'])
    path.write_bytes(b'corrupt')
    ctx.phase, ctx.stage_handle = 'plan', stage.restore_handle
    controls['offline'] = True
    with pytest.raises(GameDataError) as failure: adapter.plan(ctx.request, ctx)
    assert failure.value.code == 'publisher_bootstrap_cache_invalid'


def test_cross_request_stage_cannot_authorize_another_dub_or_region(tmp_path, original):
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request, ctx)
    ctx.request = GameDataRequest('cn', 'en')
    with pytest.raises(GameDataError) as failure: adapter.download(plan, ctx)
    assert failure.value.code == 'invalid_source_handle'


def test_actual_settings_service_stage_restart_gate_and_scoped_delete(tmp_path, original):
    from backend.game_data import GameDataService
    _module, _apk, _calls, controls = original
    adapter = provider.create_provider('android')
    history = tmp_path / 'saved-history.db'
    history.write_bytes(b'user history')
    other = tmp_path / 'nte/cache/other-original'
    other.parent.mkdir(parents=True)
    other.write_bytes(b'other game')
    service = GameDataService(tmp_path, {'wuwa': adapter})
    request = GameDataRequest('global', 'ja', ('en', 'zh-Hans')).json()
    try:
        row = service.plan('wuwa', request)['game']
        assert row['can_download'] and not row['can_activate']
        service.download('wuwa', {'plan_id': row['plan_id'], 'revision': row['revision']})
        deadline = time.monotonic() + 5
        while True:
            row = next(x for x in service.snapshot()['games'] if x['id'] == 'wuwa')
            if row['job'] and row['job']['status'] not in ('queued', 'running'): break
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert row['job']['status'] == 'needs_plan' and not row['can_activate']
        assert not (tmp_path / 'wuwa/current.json').exists()
        assert (tmp_path / 'wuwa/stage.json').is_file()
    finally:
        service.close()
    controls['offline'] = True
    restarted = GameDataService(tmp_path, {'wuwa': adapter})
    try:
        row = restarted.plan('wuwa', request)['game']
        assert not row['can_download'] and not row['can_activate'] and row['installed_bytes'] > 0
        assert provider.FORMAT_MESSAGE in row['message']
        removed = restarted.delete('wuwa', {'revision': row['revision']})
        assert removed['freed_bytes'] > 0 and not (tmp_path / 'wuwa').exists()
        assert history.read_bytes() == b'user history' and other.read_bytes() == b'other game'
    finally:
        restarted.close()


def test_selected_module_limit_is_rejected_before_whole_carrier_acquisition(tmp_path, original):
    import struct
    import zipfile
    _module, apk, calls, controls = original
    raw = bytearray(apk)
    name = b'lib/arm64-v8a/libUE4.so'
    with zipfile.ZipFile(io.BytesIO(apk)) as archive:
        local = archive.getinfo(name.decode()).header_offset
    central = raw.rfind(name) - 46
    assert raw[central:central+4] == b'PK\x01\x02'
    # Signed metadata remains unchanged. Reject unsupported declared module
    # size during planning, before whole-carrier integrity/body acquisition.
    struct.pack_into('<I', raw, local + 22, provider._source().MAX_MODULE + 1)
    struct.pack_into('<I', raw, central + 24, provider._source().MAX_MODULE + 1)
    controls['carrier'] = bytes(raw)
    ctx = Context(tmp_path)
    with pytest.raises(ValueError): provider.create_provider('android').plan(ctx.request, ctx)
    assert all(request.get_header('Range') or request.full_url.startswith(provider._source().CATALOGUE) for request in calls)
    assert not list(ctx.cache_directory.rglob('*.json'))


def test_quote_restore_never_claims_that_its_original_module_is_verified(tmp_path, original):
    _module, _apk, calls, controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request, ctx)
    count = len(calls)
    controls['offline'] = True
    with pytest.raises(GameDataError) as error:
        adapter.restore(plan.handle, ctx)
    assert error.value.code == 'publisher_bootstrap_incomplete'
    assert 'not been verified' in str(error.value)
    assert provider.FORMAT_MESSAGE not in str(error.value)
    assert len(calls) == count
    assert not list(ctx.cache_directory.rglob('module.so'))



def test_android_explicit_capability_drives_full_pure_bootstrap_without_desktop_fallback(tmp_path, original, monkeypatch):
    """Host simulation of Java boundary, not APK/device capability evidence."""
    import sys
    from types import SimpleNamespace
    from backend import publisher_crypto
    module, apk, _calls, controls = original
    reference = publisher_crypto.DesktopPublisherCrypto()
    operations = []
    class AuthoredNative:
        def proof(self):
            return json.dumps({'schema':'toolkit-publisher-crypto-v1','abi':'arm64-v8a',
                'source_sha256':publisher_crypto.SOURCE_SHA256,'platform_primitives':'JCA',
                'apk_entry_verified':True,'licenses_verified':True,'system_fallback':False,
                'original_client_execution':False,'account_keys_reused':False,'pointer_bits':64,
                'library_sha256':'a'*64,'manifest_sha256':'b'*64})
        def rsaVerifySha256(self, spki, data, signature):
            operations.append('rsa')
            return reference.rsa_verify_sha256(spki,data,signature)
    native = AuthoredNative()
    monkeypatch.setitem(sys.modules,'java',SimpleNamespace(jclass=lambda name:AuthoredNative))
    monkeypatch.setattr(provider.WutheringGameDataProvider,'_crypto',controls['maintained_crypto'])
    monkeypatch.setattr(provider,'PublisherTransport',lambda *a,**k:pytest.fail('Use only the explicitly supplied transport'))
    adapter = provider.create_provider('android',SimpleNamespace(publisherCrypto=lambda:native),
        transport_factory=controls['transport_factory'])
    assert isinstance(adapter._crypto(),publisher_crypto.AndroidPublisherCrypto)
    ctx = Context(tmp_path)
    plan = adapter.plan(ctx.request,ctx)
    assert plan.stage == 'bootstrap' and plan.source_proof is None and plan.download_bytes == len(apk)
    ctx.phase,ctx.consumed,ctx.budget = 'download',0,plan.download_bytes
    stage = adapter.download(plan,ctx)
    assert operations and set(operations) == {'rsa'}
    assert isinstance(stage,PreparationStage)
    assert provider._source()._module(ctx.cache_directory,stage.restore_handle['source']).read_bytes() == module
    controls['offline'] = True
    ctx.stage_handle = stage.restore_handle
    assert adapter.plan(ctx.request,ctx).stage == 'manifest-format'
    with pytest.raises(GameDataError) as error: adapter.restore(stage.restore_handle,ctx)
    assert error.value.code == 'publisher_format_key_unresolved'


def test_cancel_during_local_native_derivation_never_publishes_module_or_stage(tmp_path, original, monkeypatch):
    _module,_apk,_calls,_controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request,ctx)
    ctx.phase,ctx.consumed,ctx.budget = 'download',0,plan.download_bytes
    derive = provider._source().default_output
    calls = []
    def controlled(path, digest, *, check):
        def cancel_during_parse():
            calls.append(True)
            if len(calls) == 4: ctx.cancel.set()
            check()
        return derive(path,digest,check=cancel_during_parse)
    monkeypatch.setattr(provider._source(),'default_output',controlled)
    with pytest.raises(GameDataError) as failure: adapter.download(plan,ctx)
    assert failure.value.code == 'preparation_cancelled'
    assert len(calls) == 4
    assert not list(ctx.cache_directory.rglob('module.so'))
    assert not list(ctx.cache_directory.rglob('pending-*'))



def test_cancelled_offline_retained_bootstrap_preserves_source_and_cancellation_identity(tmp_path, original):
    _module,_apk,_calls,controls = original
    ctx = Context(tmp_path)
    adapter = provider.create_provider('android')
    plan = adapter.plan(ctx.request,ctx)
    ctx.phase,ctx.consumed,ctx.budget = 'download',0,plan.download_bytes
    stage = adapter.download(plan,ctx)
    path = provider._source()._module(ctx.cache_directory,stage.restore_handle['source'])
    before = path.read_bytes(); controls['offline'] = True
    original_check = ctx.check; calls = []
    def during_local_hash():
        calls.append(True)
        if len(calls) == 5: ctx.cancel.set()
        original_check()
    ctx.check = during_local_hash
    with pytest.raises(GameDataError) as failure: adapter.restore(stage.restore_handle,ctx)
    assert failure.value.code == 'preparation_cancelled'
    assert len(calls) == 5 and path.read_bytes() == before
