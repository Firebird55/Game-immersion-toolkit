"""Real shared service/transport bootstrap; no game library readiness claim."""
import time
import hashlib
import io
import json
import sys
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from backend.game_data import GameDataService
from backend.game_data_protocol import GameDataError, GameDataPlan
from backend import nte_game_data_snapshot as snapshot
from backend.nte_game_data import NteGameDataProvider, create_provider
from backend.publisher_crypto import DesktopPublisherCrypto, MAX_BYTES, SOURCE_SHA256
from backend.atomic_files import write_bytes
from backend.tests.fixtures.nte_updater_inputs import release_responses
from backend.tests.test_nte_game_data_snapshot import fixture as text_snapshot
from backend.tests.test_nte_updater_source import Originals
from backend.tests.test_publisher_transport import Response
from backend import nte_updater_baseline as baseline, nte_updater_source as updater_source
from backend.tests.test_nte_original_updater import authored_sdk
from types import SimpleNamespace


REQUEST = {'region': 'global', 'source_locale': 'ja', 'target_locales': ['en'], 'content_mode': 'text'}


@pytest.mark.parametrize('stage', ['archive-index-ranges', 'original-indices', 'global-import-metadata', 'process-metadata', 'dialogue-package-ranges', 'initial-descriptions', 'process-authoring', 'authoring-import-ranges', 'authored-subtitle-ranges', 'normalize-text', 'audio-member-ranges', 'process-audio-bindings', 'materialize-audio', 'finalize-audio'])
def test_nonwindows_download_rejects_before_desktop_imports_even_for_a_foreign_stage(monkeypatch, stage):
    import backend
    for name in ('nte_game_data_runtime', 'nte_game_data_content', 'nte_game_data_ranges', 'nte_game_data_iostore', 'nte_game_data_prepare', 'nte_game_data_packages', 'nte_game_data_initial', 'nte_game_data_authoring', 'nte_game_data_imports', 'nte_game_data_text', 'nte_game_data_audio'):
        monkeypatch.delattr(backend, name, raising=False)
        monkeypatch.setitem(sys.modules, 'backend.'+name, None)
    ctx = SimpleNamespace(check=lambda: None)
    provider = NteGameDataProvider(platform='android')
    with pytest.raises(GameDataError) as rejected:
        provider.download(SimpleNamespace(stage=stage), ctx)
    assert rejected.value.code == 'nte_reader_unavailable'


def originals(monkeypatch):
    """A genuinely frozen authored historical pair, independent of later current."""
    original = Originals()
    fixed = updater_source.plan(fetch=original.fetch)
    monkeypatch.setattr(baseline, 'inputs', lambda: fixed)
    digests = {}
    for item in fixed.artifacts:
        with ZipFile(io.BytesIO(original.bodies[item.url])) as archive:
            digests[item.role] = hashlib.sha256(archive.read(item.member)).hexdigest()
    monkeypatch.setattr(baseline, 'MEMBER_SHA256', digests)
    return original


def opener(original, calls):
    def open_(request, **kwargs):
        url = request.full_url; calls.append(url)
        data = (original.version_body if url.endswith('/Version.ini') else
                ElementTree.tostring(original.root)
                if url == original.manifest_url else original.bodies[url])
        return Response(data, url=url)
    return open_


def row(service):
    return next(value for value in service.snapshot()['games'] if value['id'] == 'nte')


def finish(service):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        value = row(service)
        if value['job'] and value['job']['status'] not in {'queued', 'running'}:
            return value
        time.sleep(.01)
    raise AssertionError('NTE bootstrap stage did not finish')


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_shared_service_plans_exact_bootstrap_then_returns_a_nonready_stage(tmp_path, mode, monkeypatch):
    original = originals(monkeypatch); calls = []; activations = []
    provider = NteGameDataProvider(platform='windows', opener=opener(original, calls))
    service = GameDataService(tmp_path, {'nte': provider}, on_activate=lambda *_: activations.append(True))
    request = {**REQUEST, 'content_mode': mode}
    try:
        plan = service.plan('nte', request)['game']
        assert len(calls) == 2 and not any(url.endswith('.zip') for url in calls)
        expected = sum(len(raw) for raw in original.bodies.values()) + sum(
            len(original.version_body) if url.endswith('/Version.ini') else len(ElementTree.tostring(original.root))
            for url in calls)
        assert plan['download_bytes'] == expected and plan['can_download']
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        result = finish(service)
        assert result['job']['status'] == 'needs_plan' and result['job']['downloaded_bytes'] == expected
        assert result['state'] != 'ready' and not activations and not (tmp_path/'nte/current.json').exists()
        assert result['installed_bytes'] > 0 and (tmp_path/'nte/stage.json').is_file()
        next_plan = service.plan('nte', request)['game']
        assert not next_plan['can_download'] and next_plan['download_bytes'] is None
        assert 'game-content' in next_plan['message'].lower()
        assert len([url for url in calls if url.endswith('.zip')]) == 2
    finally:
        service.close()


def test_source_change_after_planning_never_publishes_a_ready_library(tmp_path, monkeypatch):
    original = originals(monkeypatch); calls = []; activations = []
    provider = NteGameDataProvider(platform='android', opener=opener(original, calls))
    service = GameDataService(tmp_path, {'nte': provider}, on_activate=lambda *_: activations.append(True))
    try:
        plan = service.plan('nte', REQUEST)['game']
        original.version_body = original.version_body.replace(b'1.2.3.4', b'1.2.3.5')
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        result = finish(service)
        assert result['job']['status'] == 'failed' and result['state'] != 'ready' and not activations
        assert not (tmp_path/'nte/current.json').exists() and not (tmp_path/'nte/stage.json').exists()
    finally:
        service.close()


def test_owner_switch_stops_before_any_sdk_payload(tmp_path, monkeypatch):
    original = originals(monkeypatch); calls = []; owner = ['first']
    provider = NteGameDataProvider(platform='windows', opener=opener(original, calls))
    service = GameDataService(tmp_path, {'nte': provider}, owner_guard=lambda: owner[0])
    try:
        plan = service.plan('nte', REQUEST, expected_owner='first')['game']
        owner[0] = 'second'
        with pytest.raises(GameDataError):
            service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']}, expected_owner='first')
        assert not any(url.endswith('.zip') for url in calls)
    finally:
        service.close()


def test_canonical_factory_preserves_mainland_and_native_reader_gates(tmp_path):
    provider = create_provider(platform='android', native=None)
    assert isinstance(provider, NteGameDataProvider)
    service = GameDataService(tmp_path, {'nte': provider})
    try:
        plan = service.plan('nte', {**REQUEST, 'region': 'cn'})['game']
        assert plan['download_bytes'] is None and not plan['can_download']
        assert not (tmp_path/'nte/current.json').exists()
    finally:
        service.close()


def test_rotated_current_sdk_plans_and_keeps_the_independent_frozen_historical_pair(tmp_path, monkeypatch):
    old = originals(monkeypatch)
    current = Originals('1.2.3.5', authored_sdk().replace(b'fixture!', b'changed!'))
    current.bodies.update(old.bodies)
    calls = []
    service = GameDataService(tmp_path, {'nte': NteGameDataProvider(platform='windows', opener=opener(current, calls))})
    try:
        plan = service.plan('nte', REQUEST)['game']
        assert not any(url.endswith('.zip') for url in calls)
        metadata = len(current.version_body) + len(ElementTree.tostring(current.root))
        assert plan['download_bytes'] == sum(len(raw) for raw in current.bodies.values()) + metadata
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        completed = finish(service)
        assert completed['job']['status'] == 'needs_plan' and completed['state'] != 'ready'
        assert len([url for url in calls if url.endswith('.zip')]) == 4
        cache = tmp_path/'nte/cache/tools/nte-publisher/format'
        old_key, _ = baseline.parameters(cache)
        selected = updater_source.plan(fetch=current.fetch)
        assert updater_source.resolve_retained(selected, cache).key != old_key
        assert not (tmp_path/'nte/current.json').exists()
    finally:
        service.close()


def test_frozen_original_member_sha_is_checked_before_native_parameter_parsing(tmp_path, monkeypatch):
    original = originals(monkeypatch)
    updater_source.resolve(baseline.inputs(), tmp_path, fetch=original.fetch)
    monkeypatch.setitem(baseline.MEMBER_SHA256, 'sdk', '0'*64)
    monkeypatch.setattr(updater_source, 'resolve_retained', lambda *_: pytest.fail('Parsed a foreign frozen SDK'))
    with pytest.raises(ValueError):
        baseline.parameters(tmp_path)


def test_conflicting_historical_download_address_is_a_typed_blocker_before_transfer(tmp_path, monkeypatch):
    originals(monkeypatch)
    current = Originals(sdk=authored_sdk().replace(b'fixture!', b'changed!'))
    calls = []
    service = GameDataService(tmp_path, {'nte': NteGameDataProvider(platform='windows', opener=opener(current, calls))})
    try:
        with pytest.raises(GameDataError) as rejected:
            service.plan('nte', REQUEST)
        assert rejected.value.code == 'historical_source_changed'
        assert not any(url.endswith('.zip') for url in calls)
        assert not (tmp_path/'nte/current.json').exists()
    finally:
        service.close()


def test_android_retained_bootstrap_keeps_the_native_gate_without_importing_windows_modules(tmp_path, monkeypatch):
    original = originals(monkeypatch)
    cache = tmp_path/'nte/cache/tools/nte-publisher/format'
    updater_source.resolve(baseline.inputs(), cache, fetch=original.fetch)
    monkeypatch.setitem(sys.modules, 'backend.nte_game_data_runtime', None)
    calls = []
    service = GameDataService(tmp_path, {'nte': NteGameDataProvider(platform='android', opener=opener(original, calls))})
    try:
        plan = service.plan('nte', REQUEST)['game']
        assert not plan['can_download'] and plan['download_bytes'] is None
        assert 'publisher cryptography' in plan['message'] and not (tmp_path/'nte/current.json').exists()
        assert calls == [updater_source.VERSION_URL, original.manifest_url]
    finally:
        service.close()


@pytest.mark.parametrize('fault,code', [('checksum', 'nte_resource_manifest_invalid'),
    ('launcher changed', 'game_source_changed')])
def test_android_manifest_failure_preserves_the_previous_library_for_offline_restore(tmp_path, monkeypatch, fault, code):
    original = originals(monkeypatch)
    managed = tmp_path/'managed'
    cache = managed/'nte/cache/tools/nte-publisher/format'
    updater_source.resolve(baseline.inputs(), cache, fetch=original.fetch)
    payload, inputs, previous = text_snapshot(tmp_path/'prior')
    request = previous.request.json()
    saved_revision = 'authored-retained-nte'

    class PreviousProducer(NteGameDataProvider):
        def plan(self, request, ctx):
            return GameDataPlan(saved_revision, 0, 128*1024, runtime_available=True)

        def download(self, plan, ctx):
            return snapshot.publish(payload, inputs, ctx, write_bytes)

    seed = GameDataService(managed, {'nte': PreviousProducer(platform='android')})
    try:
        quote = seed.plan('nte', request)['game']
        seed.download('nte', {'plan_id': quote['plan_id'], 'revision': quote['revision']})
        assert finish(seed)['job']['status'] == 'complete'
    finally:
        seed.close()
    pointer = managed/'nte/current.json'
    retained = pointer.read_bytes()
    release = release_responses(checksum='0'*32 if fault == 'checksum' else None)
    original.bodies.update(release)
    calls, operations = [], []
    reference = DesktopPublisherCrypto()

    class AuthoredJava:
        def proof(self):
            return json.dumps({'schema': 'toolkit-publisher-crypto-v1', 'abi': 'arm64-v8a',
                'source_sha256': SOURCE_SHA256, 'platform_primitives': 'JCA', 'apk_entry_verified': True,
                'licenses_verified': True, 'system_fallback': False, 'original_client_execution': False,
                'account_keys_reused': False, 'pointer_bits': 64, 'library_sha256': 'a'*64,
                'manifest_sha256': 'b'*64, 'key_bytes': 32, 'nonce_bytes': 12, 'max_bytes': MAX_BYTES})

        def blockCipher(self, algorithm, mode, key, iv, data, decrypt):
            operations.append((algorithm, mode))
            return reference.block_cipher(algorithm, mode, key, data, iv=iv, decrypt=decrypt)

    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=lambda _: AuthoredJava))
    native = SimpleNamespace(publisherCrypto=AuthoredJava)
    fetch = opener(original, calls)

    def opened(request, **kwargs):
        url = request.full_url
        if fault == 'launcher changed' and url.endswith('/Version.ini') and calls.count(url) == 2:
            response = fetch(request, **kwargs)
            return Response(response.read().replace(b'1.2.3.4', b'1.2.3.5'), url=url)
        return fetch(request, **kwargs)

    provider = create_provider(platform='android', native=native)
    provider.opener = opened
    activated = []
    service = GameDataService(managed, {'nte': provider}, on_activate=lambda *_: activated.append(True))
    try:
        with pytest.raises(GameDataError) as rejected:
            service.plan('nte', request)
        assert rejected.value.code == code and 'previous library is retained' in rejected.value.message
        assert operations == [('AES', 'CBC')]
        assert set(calls) == {updater_source.VERSION_URL, original.manifest_url, *release}
        assert row(service)['installed_revision'] == saved_revision and row(service)['can_activate']
        assert pointer.read_bytes() == retained and not activated
        assert not (cache/'original-updater/approvals').exists()
    finally:
        service.close()
    def unexpected_transfer(*_args, **_kwargs):
        pytest.fail('Offline restoration reached the publisher')

    reopened = GameDataService(managed, {'nte': NteGameDataProvider(platform='android', opener=unexpected_transfer)})
    try:
        source = reopened.restore('nte')
        assert json.loads(source.snapshot_path.read_bytes())['records'] == payload['records']
        assert pointer.read_bytes() == retained
    finally:
        reopened.close()
