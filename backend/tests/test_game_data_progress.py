"""Actual charged bytes remain visible without provider-specific callbacks."""
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from backend.game_data import GameDataService
from backend.game_data_protocol import GameDataError
from backend.tests.test_game_data import Provider, download, finish, row
from backend.tests.test_publisher_transport import context


def test_phase_updates_cannot_rewind_wire_counter_or_replace_quoted_total(context):
    context.job = {'downloaded_bytes': 0, 'total_bytes': context.budget}
    context.consume_bytes(17)
    assert context.job['downloaded_bytes'] == 17
    context.progress('decode', 0, 0, 'Authored phase with no network work.')
    assert context.job['downloaded_bytes'] == 17
    assert context.job['total_bytes'] == context.budget
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: context.consume_bytes(7), range(100)))
    assert context.job['downloaded_bytes'] == context.consumed == 717


def test_cancel_during_read_retains_received_byte_cost_in_old_job(context):
    context.job = {'downloaded_bytes': 0}
    context.cancel.set()
    with pytest.raises(GameDataError, match='stopped'):
        context.consume_bytes(23)
    assert context.job['downloaded_bytes'] == context.consumed == 23
    with pytest.raises(GameDataError):
        context.consume_bytes(0)
    assert context.job['downloaded_bytes'] == 23


def test_public_progress_updates_during_transfer_and_failure_preserves_old_source(tmp_path):
    entered, release = threading.Event(), threading.Event()
    class Metered(Provider):
        def download(self, plan, ctx):
            if plan.revision == 'authored-two':
                ctx.consume_bytes(1234)
                entered.set()
                assert release.wait(5)
                raise OSError('Authored interrupted transfer')
            return super().download(plan, ctx)
    provider = Metered()
    service = GameDataService(tmp_path, {'zzz': provider})
    try:
        download(service)
        assert finish(service)['state'] == 'ready'
        pointer = (tmp_path / 'zzz/current.json').read_bytes()
        provider.revision = 'authored-two'
        download(service)
        assert entered.wait(3)
        public = row(service)
        assert public['job']['status'] == 'running'
        assert public['job']['downloaded_bytes'] == 1234
        assert public['job']['total_bytes'] == 8192
        assert (tmp_path / 'zzz/current.json').read_bytes() == pointer
        release.set()
        failed = finish(service)
        assert failed['job']['status'] == 'failed'
        assert failed['job']['downloaded_bytes'] == 1234
        assert service.restore('zzz') is not None
        assert (tmp_path / 'zzz/current.json').read_bytes() == pointer
    finally:
        release.set()
        service.close()
