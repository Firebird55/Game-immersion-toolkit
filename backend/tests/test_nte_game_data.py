"""Real shared service/transport bootstrap; no game library readiness claim."""
import time
from xml.etree import ElementTree

import pytest

from backend.game_data import GameDataService
from backend.game_data_protocol import GameDataError
from backend.nte_game_data import NteGameDataProvider, create_provider
from backend.tests.test_nte_updater_source import Originals
from backend.tests.test_publisher_transport import Response


REQUEST = {'region': 'global', 'source_locale': 'ja', 'target_locales': ['en'], 'content_mode': 'text'}


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
def test_shared_service_plans_exact_bootstrap_then_returns_a_nonready_stage(tmp_path, mode):
    original = Originals(); calls = []; activations = []
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


def test_source_change_after_planning_never_publishes_a_ready_library(tmp_path):
    original = Originals(); calls = []; activations = []
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


def test_owner_switch_stops_before_any_sdk_payload(tmp_path):
    original = Originals(); calls = []; owner = ['first']
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
