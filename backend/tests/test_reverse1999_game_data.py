"""Real shared transport against owned HTTP publisher-response fixtures."""
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import threading
from urllib.error import HTTPError

import pytest

from backend.game_data_protocol import GameDataError, MAX_METADATA_BYTES
from backend.game_data import GameDataService
from backend.publisher_transport import PublisherTransport
from backend.reverse1999_game_data import create_provider, Reverse1999GameDataProvider, METADATA_HOSTS
from backend.reverse1999_release import DOWNLOAD_HOSTS
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


def fixture_transport(*, backup=False):
    source, _ = fixture()
    opens = []

    def opener(req, *, timeout):
        opens.append(req)
        assert timeout == 30 and req.headers['Accept-encoding'] == 'identity'
        assert 'optional' not in req.full_url and not req.full_url.endswith(('.zip', '.exe'))
        if req.full_url.endswith('.7z'):
            assert req.headers['Range'] == 'bytes=0-31'
            response = Response(req.full_url, bytes(32))
            response.status = 206
            response.headers['Content-Range'] = 'bytes 0-31/64'
            return response
        if backup and req.full_url.startswith('https://hotupdate-hw.sl916.com'):
            raise HTTPError(req.full_url, 503, 'Owned unavailable publisher', {}, None)
        body = None if req.data is None else json.loads(req.data)
        assert req.method == ('GET' if body is None else 'POST')
        return Response(req.full_url, source(req.full_url, body=body))

    def transport(ctx, *, hosts):
        assert hosts in {METADATA_HOSTS, DOWNLOAD_HOSTS}
        return PublisherTransport(ctx, hosts=hosts, opener=opener)

    return transport, opens


def adapter(*, backup=False):
    transport, opens = fixture_transport(backup=backup)
    return Reverse1999GameDataProvider(platform='windows', transport_factory=transport), opens


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_platform_factory_transport_accounts_only_bounded_metadata_and_never_activates(mode):
    provider, opens = adapter(); selection = request(mode); ctx = Context(selection)
    plan = provider.plan(selection, ctx)
    assert len(opens) == 5 and ctx.consumed > 0
    assert not plan.runtime_available and plan.source_proof is None
    assert plan.download_bytes is None and plan.required_disk_bytes is None
    assert plan.handle['content_mode'] == mode
    assert plan.handle['selection_bytes']['audio'] == (0 if mode == 'text' else None)


def test_original_publisher_backup_uses_typed_transport_network_failure_only():
    provider, opens = adapter(backup=True); selection = request(); plan = provider.plan(selection, Context(selection))
    assert len(opens) == 6 and plan.handle['publisher_inventory']['version'] == '3.9.0'
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


@pytest.mark.parametrize('unavailable', ['backend.reverse1999_archive', '_lzma'])
def test_packaged_android_registry_retains_discovery_without_archive_codec(unavailable):
    # A fresh interpreter prevents another test's desktop imports from
    # satisfying the closed package's missing module.
    program = """
import sys

blocked = sys.argv[1]
archive = 'backend.reverse1999_archive'
attempted = []

class ClosedModules:
    def find_spec(self, fullname, path, target=None):
        if fullname in {archive, 'lzma', '_lzma', 'backend.prepared_library'}:
            attempted.append(fullname)
        if fullname in {blocked, 'backend.prepared_library'}:
            raise ModuleNotFoundError(fullname, name=fullname)

sys.meta_path.insert(0, ClosedModules())
from backend import game_data_providers as registry
registry.PROVIDER_MODULES = {'reverse1999': registry.PROVIDER_MODULES['reverse1999']}
provider = registry.create_game_data_providers(platform='android')['reverse1999']
assert archive not in attempted and 'backend.prepared_library' not in attempted

from backend.tests.test_reverse1999_game_data import Context, fixture_transport, request
if blocked == '_lzma':
    assert 'lzma' not in sys.modules and '_lzma' not in sys.modules
attempted.clear()
provider.transport_factory, opens = fixture_transport()
selection = request('text-audio')
plan = provider.plan(selection, Context(selection))
assert attempted == ([archive] if blocked == archive else [archive, 'lzma', '_lzma']), attempted
assert len(opens) == 4 and all(not req.full_url.endswith('.7z') for req in opens)
assert plan.stage == 'publisher-discovery' and not plan.runtime_available
assert plan.download_bytes is None and plan.required_disk_bytes is None
assert plan.handle['publisher_inventory']['version'] == '3.9.0'
"""
    result = subprocess.run([sys.executable, '-B', '-c', program, unavailable],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


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
        assert not activated and len(opens) == 5 and not list(tmp_path.rglob('textmap.json'))
    finally:
        service.close()
