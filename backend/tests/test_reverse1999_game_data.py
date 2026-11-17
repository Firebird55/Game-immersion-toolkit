"""Real shared transport against owned HTTP publisher-response fixtures."""
from email.message import Message
from io import BytesIO
import json
import threading
from urllib.error import HTTPError

import pytest

from backend.game_data_protocol import GameDataError, MAX_METADATA_BYTES
from backend.game_data import GameDataService
from backend.publisher_transport import PublisherTransport
from backend.reverse1999_game_data import create_provider, Reverse1999GameDataProvider, METADATA_HOSTS
from backend.tests.test_reverse1999_provider import request
from backend.tests.test_reverse1999_release import fixture


class Context:
    def __init__(self, selection):
        self.request, self.consumed, self.stopped = selection, 0, False
        self.transfer_lock = threading.RLock()

    def check(self):
        if self.stopped:
            raise GameDataError('preparation_cancelled', 'Preparation stopped.', 409)

    def consume_bytes(self, count, *, kind):
        assert kind == 'metadata'
        if self.consumed + count > MAX_METADATA_BYTES:
            raise GameDataError('transfer_budget_exceeded', 'Metadata allowance was exceeded.')
        self.consumed += count

    def remaining_bytes(self, *, kind):
        assert kind == 'metadata'
        return MAX_METADATA_BYTES - self.consumed


class Response(BytesIO):
    status = 200

    def __init__(self, url, data):
        super().__init__(data)
        self.url = url
        self.headers = Message()
        self.headers['Content-Length'] = str(len(data))

    def geturl(self):
        return self.url


def adapter(*, backup=False):
    source, calls = fixture()
    opens = []

    def opener(req, *, timeout):
        opens.append(req)
        assert timeout == 30 and req.headers['Accept-encoding'] == 'identity'
        assert 'optional' not in req.full_url and not req.full_url.endswith(('.zip', '.7z', '.exe'))
        if backup and req.full_url.startswith('https://hotupdate-hw.sl916.com'):
            raise HTTPError(req.full_url, 503, 'Owned unavailable publisher', {}, None)
        body = None if req.data is None else json.loads(req.data)
        assert req.method == ('GET' if body is None else 'POST')
        return Response(req.full_url, source(req.full_url, body=body))

    def transport(ctx, *, hosts):
        assert hosts == METADATA_HOSTS
        return PublisherTransport(ctx, hosts=hosts, opener=opener)

    return Reverse1999GameDataProvider(platform='android', transport_factory=transport), opens


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_platform_factory_transport_accounts_only_bounded_metadata_and_never_activates(mode):
    provider, opens = adapter(); selection = request(mode); ctx = Context(selection)
    plan = provider.plan(selection, ctx)
    assert len(opens) == 4 and ctx.consumed > 0
    assert not plan.runtime_available and plan.source_proof is None
    assert plan.download_bytes is None and plan.required_disk_bytes is None
    assert plan.handle['content_mode'] == mode
    assert plan.handle['selection_bytes']['audio'] == (0 if mode == 'text' else None)


def test_original_publisher_backup_uses_typed_transport_network_failure_only():
    provider, opens = adapter(backup=True); selection = request(); plan = provider.plan(selection, Context(selection))
    assert len(opens) == 5 and plan.handle['publisher_inventory']['version'] == '3.9.0'
    assert any('hotupdate-bak-hw.sl916.com' in req.full_url for req in opens)


def test_factory_constructs_all_host_platforms_without_opening_or_using_native_audio():
    class UnusedNative:
        def __getattribute__(self, _name):
            raise AssertionError('Discovery stage accessed native/audio services')
    for platform in ('android', 'windows', 'linux', 'macos'):
        provider = create_provider(platform=platform, native=UnusedNative())
        assert provider.platform == platform and provider.title == 'Reverse: 1999'
    with pytest.raises(GameDataError):
        create_provider(platform='unknown')


def test_cancelled_context_is_refused_before_shared_transport_connection():
    provider, opens = adapter(); selection = request(); ctx = Context(selection); ctx.stopped = True
    with pytest.raises(GameDataError) as error:
        provider.plan(selection, ctx)
    assert error.value.code == 'preparation_cancelled' and not opens


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_real_shared_service_exposes_unknown_selected_size_and_refuses_snapshot_activation(tmp_path, mode):
    provider, opens = adapter(); activated = []
    service = GameDataService(tmp_path, {'reverse1999': provider}, on_activate=lambda *_args: activated.append(True))
    try:
        row = service.plan('reverse1999', request(mode).json())['game']
        assert row['content_mode'] == mode and row['can_plan'] is True and row['can_download'] is False
        assert row['download_bytes'] is None and row['required_disk_bytes'] is None
        assert row['installed_bytes'] == 0 and row['state'] == 'not_downloaded'
        assert 'publisher_inventory' not in row and 'selection_bytes' not in row
        with pytest.raises(GameDataError) as unavailable:
            service.download('reverse1999', {'plan_id': row['plan_id'], 'revision': row['revision']})
        assert unavailable.value.code == 'download_not_available'
        assert not activated and len(opens) == 4 and not list(tmp_path.rglob('textmap.json'))
    finally:
        service.close()
