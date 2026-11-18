"""Authored APK/network fixtures protect the real consent and integrity seam.

No original game, account, device or network resource is used. Existing format
tests protect decoder details; these checks protect plan/download/retention and
the distinction between a native bootstrap stage and a prepared game library.
"""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from backend import infinitynikki_game_data as source
from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage, SnapshotSource
from backend.publisher_transport import PublisherTransport
from backend.tests.test_infinity_nikki_pak_material import fixture as native_fixture
from backend.tests import test_publisher_apk_zip as apk_authored
from backend.tests.test_publisher_transport import Response


@pytest.fixture(scope='module')
def apk_fixture():
    apk_authored.ApkMetadataTests.setUpClass()
    return apk_authored.ApkMetadataTests().fixture


class Fixture:
    def __init__(self, tmp_path, apk_fixture, *, mode='text', bad_native=False, region='cn'):
        self.root = tmp_path
        native, _ = native_fixture(failure='unbound-producer' if bad_native else None)
        self.native = native
        self.apk = apk_fixture(names=[(source.NATIVE_MEMBER, native, 8),
            ('assets/ignored-media.dat', b'authored unused packaged media' * 20, 0)])
        self.url = 'https://' + source.APK_HOST + '/x6cn/adapk/current-authored.apk'
        self.tag = '"authored-generation-one"'
        page = {'props': {'pageProps': {'pageData': {'page': {'android': [
            {'__type': 'text', 'value': self.url}]}}}}}
        self.home = ('<script id="__NEXT_DATA__" type="application/json">' + json.dumps(page) + '</script>').encode()
        self.calls, self.kinds = [], []
        self.fail, self.corrupt, self.cancel_whole = False, False, False
        self.request = GameDataRequest(region, 'en', ('ja',), mode)
        self.service = GameDataService(tmp_path, {})
        self.ctx = self.context('plan')
        self.provider = source.create_provider('windows', transport_factory=self.transport)

    def context(self, phase, *, budget=None):
        self.ctx = _Context(self.service, self.root, 'local', 'infinitynikki', self.request,
                            self.root / 'pending', phase, budget=budget)
        return self.ctx

    def transport(self, ctx, *, hosts):
        fixture = self
        assert ctx is self.ctx and set(hosts) <= {'infinitynikki.nuanpaper.com', source.APK_HOST}
        class Transport(PublisherTransport):
            def fetch_bytes(self, *args, **kwargs):
                fixture.kinds.append(kwargs['kind'])
                return super().fetch_bytes(*args, **kwargs)
            def consume_stream(self, *args, **kwargs):
                fixture.kinds.append(kwargs['kind'])
                return super().consume_stream(*args, **kwargs)
        return Transport(ctx, hosts=hosts, opener=self.open)

    def open(self, request, **_kwargs):
        url, original_range = request.full_url, request.get_header('Range')
        self.calls.append((url, original_range))
        if url == source.HOMEPAGE:
            return Response(self.home, headers={'Content-Length': str(len(self.home))}, url=url)
        assert url == self.url
        data = self.apk
        if self.corrupt and original_range is None:
            data = data[:100] + bytes([data[100] ^ 1]) + data[101:]
        headers = {'ETag': self.tag, 'Content-Length': str(len(data))}
        if original_range is not None:
            start, end = map(int, original_range[6:].split('-'))
            headers['Content-Range'] = f'bytes {start}-{end}/{len(data)}'
            data = data[start:end + 1]
            headers['Content-Length'] = str(len(data))
            return Response(data, status=206, headers=headers, url=url)
        if self.fail:
            return Response(data[:-1], headers=headers, url=url)
        fixture = self
        class Carrier(Response):
            def read(self, size=-1):
                result = super().read(size)
                if fixture.cancel_whole:
                    fixture.ctx.cancel.set()
                return result
        return Carrier(data, headers=headers, url=url)

    def download(self, plan):
        return self.provider.download(plan, self.context('download', budget=plan.download_bytes))


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_native_plan_quotes_whole_carrier_and_never_activates_dialogue(tmp_path, apk_fixture, mode):
    fixture = Fixture(tmp_path, apk_fixture, mode=mode)
    plan = fixture.provider.plan(fixture.request, fixture.ctx)
    assert plan.download_bytes == len(fixture.apk) and plan.required_disk_bytes >= len(fixture.native)
    assert plan.runtime_available and plan.stage == 'native-bootstrap' and plan.source_proof is None
    assert 'unused packaged media' in plan.message and 'no optional voice pack' in plan.message
    assert not any(url == fixture.url and span is None for url, span in fixture.calls)
    result = fixture.download(plan)
    assert isinstance(result, PreparationStage) and not isinstance(result, SnapshotSource)
    assert result.restore_handle['request']['content_mode'] == mode
    assert result.restore_handle['stage'] == 'content-reader'
    modules = list(fixture.ctx.cache_directory.rglob('*.so'))
    assert len(modules) == 1 and modules[0].read_bytes() == fixture.native
    assert not list(fixture.ctx.cache_directory.rglob('native.packed'))
    assert not list(fixture.ctx.cache_directory.rglob('ignored-media.dat'))
    receipt = source._read(fixture.ctx, result.restore_handle['receipt_sha256'])
    assert receipt['verified']['whole_apk_v2_integrity_verified']
    assert receipt['global_android_client_accepted'] is False
    assert receipt['publisher_certificate_independently_pinned'] is False
    assert receipt['native_consumer_checked'] is True
    assert 'parameter' not in receipt and 'seed' not in receipt
    assert 'audio' not in fixture.kinds
    before = len(fixture.calls)
    with pytest.raises(GameDataError) as failure:
        fixture.provider.restore(result.restore_handle, fixture.context('restore'))
    assert failure.value.code == 'publisher_content_reader_unresolved'
    assert len(fixture.calls) == before


@pytest.mark.parametrize('change', ['request', 'download_bytes', 'required_disk_bytes', 'revision',
                                   'stage', 'runtime_available', 'source_proof', 'artifact'])
def test_stale_or_modified_consent_stops_before_whole_transfer(tmp_path, apk_fixture, change):
    fixture = Fixture(tmp_path, apk_fixture)
    plan = fixture.provider.plan(fixture.request, fixture.ctx)
    if change == 'request':
        fixture.request = GameDataRequest('cn', 'en', ('ja',), 'text-audio')
    elif change == 'artifact':
        path = source._path(fixture.ctx, plan.handle['receipt_sha256'] + '.json')
        path.write_bytes(path.read_bytes() + b' ')
    else:
        replacements = {'download_bytes': plan.download_bytes + 1, 'required_disk_bytes': plan.required_disk_bytes + 1,
            'revision': 'different', 'stage': 'content', 'runtime_available': False, 'source_proof': object()}
        plan = replace(plan, **{change: replacements[change]})
    with pytest.raises(GameDataError):
        fixture.download(plan)
    assert not any(url == fixture.url and span is None for url, span in fixture.calls)
    assert not list(fixture.ctx.cache_directory.rglob('*.so'))


@pytest.mark.parametrize('failure', ['etag', 'corrupt', 'truncated', 'cancelled', 'consumer'])
def test_failed_source_or_cancelled_bootstrap_keeps_previous_data(tmp_path, apk_fixture, failure):
    fixture = Fixture(tmp_path, apk_fixture, bad_native=failure == 'consumer')
    plan = fixture.provider.plan(fixture.request, fixture.ctx)
    previous = tmp_path / 'existing-language-and-recordings.dat'
    previous.write_bytes(b'authored previous user data')
    if failure == 'etag': fixture.tag = '"different-generation"'
    if failure == 'corrupt': fixture.corrupt = True
    if failure == 'truncated': fixture.fail = True
    if failure == 'cancelled': fixture.cancel_whole = True
    with pytest.raises(GameDataError) as caught:
        fixture.download(plan)
    assert previous.read_bytes() == b'authored previous user data'
    assert not list(fixture.ctx.cache_directory.rglob('*.so'))
    assert not list(fixture.ctx.cache_directory.rglob('pending-*'))
    assert 'format changed' not in str(caught.value).lower()


def test_metadata_pointer_and_native_owner_are_not_guessed(tmp_path, apk_fixture):
    fixture = Fixture(tmp_path, apk_fixture)
    for page in (b'<a href="' + fixture.url.encode() + b'">unrelated</a>',
                 fixture.home.replace(source.APK_HOST.encode(), b'foreign.invalid'),
                 fixture.home.replace(b'"android"', b'"windowsUrl"')):
        fixture.home = page
        fixture.calls.clear()
        with pytest.raises(GameDataError): fixture.provider.plan(fixture.request, fixture.context('plan'))
        assert fixture.calls == [(source.HOMEPAGE, None)]
    fixture = Fixture(tmp_path, apk_fixture)
    fixture.apk = apk_fixture(names=[('lib/arm64-v8a/libUnrelated.so', fixture.native, 8)])
    with pytest.raises(GameDataError): fixture.provider.plan(fixture.request, fixture.context('plan'))
    assert not any(url == fixture.url and span is None for url, span in fixture.calls)


def test_new_original_generation_changes_identity_without_fixed_version_or_key(tmp_path, apk_fixture):
    fixture = Fixture(tmp_path, apk_fixture)
    first = fixture.provider.plan(fixture.request, fixture.ctx)
    fixture.tag = '"authored-generation-two"'
    second = fixture.provider.plan(fixture.request, fixture.context('plan'))
    assert first.revision != second.revision and first.handle != second.handle
    assert isinstance(fixture.download(second), PreparationStage)


def test_absent_android_crypto_stops_before_metadata_and_reports_runtime_gate(tmp_path, apk_fixture):
    fixture = Fixture(tmp_path, apk_fixture)
    provider = source.create_provider('android', native=SimpleNamespace(), transport_factory=fixture.transport)
    with pytest.raises(GameDataError) as failure:
        provider.plan(fixture.request, fixture.ctx)
    assert failure.value.code == 'game_runtime_unavailable' and fixture.calls == []


def test_explicit_android_factory_capability_is_propagated_without_a_default_fallback(tmp_path, apk_fixture, monkeypatch):
    # Host-only contract test. The actual Java manifest/ABI gate and device APK
    # acceptance belong to the shared native runtime's separate acceptance work.
    from backend import publisher_crypto
    fixture = Fixture(tmp_path, apk_fixture)
    supplied, calls = object(), []
    reference = publisher_crypto.DesktopPublisherCrypto()
    class Crypto:
        def rsa_verify_sha256(self, *args):
            calls.append('verify')
            return reference.rsa_verify_sha256(*args)
    crypto = Crypto()
    def factory(*, platform, native):
        assert platform == 'android' and native is supplied
        calls.append('factory')
        return crypto
    monkeypatch.setattr(publisher_crypto, 'create_publisher_crypto', factory)
    fixture.provider = source.create_provider('android', native=SimpleNamespace(publisherCrypto=lambda: supplied),
                                              transport_factory=fixture.transport)
    plan = fixture.provider.plan(fixture.request, fixture.ctx)
    assert isinstance(fixture.download(plan), PreparationStage)
    assert calls == ['factory', 'verify', 'factory', 'verify', 'verify']


def test_factory_and_native_owner_discovery_import_without_crypto_or_desktop_services(tmp_path):
    native, _ = native_fixture()
    path = tmp_path / 'authored-native.dat'
    path.write_bytes(native)
    script = '''
import hashlib, importlib.abc, pathlib, sys
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] == 'Crypto' or fullname in {
            'backend.game_tools', 'backend.game_data', 'backend.local_game',
            'backend.multilingual_index', 'backend.desktop_game_data'}:
            raise ModuleNotFoundError('Forbidden desktop dependency', name=fullname)
sys.meta_path.insert(0, Deny())
from backend.infinitynikki_game_data import create_provider
from backend.infinity_nikki_pak_material import extract_default_pak_material
raw = pathlib.Path(sys.argv[1]).read_bytes()
digest = hashlib.sha256(raw).hexdigest()
assert extract_default_pak_material(raw, expected_native_sha256=digest).source_sha256 == digest
assert callable(create_provider('android').plan)
assert not any(name == 'Crypto' or name.startswith('Crypto.') for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', script, str(path)], cwd=Path(__file__).resolve().parents[2],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors='replace')


def test_bootstrap_handles_cannot_be_reused_for_other_locales_or_corrupt_native(tmp_path, apk_fixture):
    fixture = Fixture(tmp_path, apk_fixture)
    result = fixture.download(fixture.provider.plan(fixture.request, fixture.ctx))
    module = next(fixture.ctx.cache_directory.rglob('*.so'))
    module.write_bytes(b'corrupt' * 100)
    with pytest.raises(GameDataError):
        fixture.provider.restore(result.restore_handle, fixture.context('restore'))
    fixture.request = GameDataRequest('cn', 'ja', ('en',), 'text')
    with pytest.raises(GameDataError):
        fixture.provider.restore(result.restore_handle, fixture.context('restore'))
