"""Source-stage safety with owned publisher metadata and accounted transport."""
from types import SimpleNamespace

import pytest

from backend.game_data_protocol import GameDataError, MAX_METADATA_BYTES, SnapshotSource
from backend.reverse1999_provider import Reverse1999Provider
from backend.tests.test_reverse1999_release import fixture


def request(mode='text', region='global'):
    return SimpleNamespace(region=region, source_locale='ja', target_locales=('zh-Hans', 'en'), content_mode=mode)


class Context:
    def __init__(self, selection):
        self.request, self.received, self.stopped = selection, 0, False

    def check(self):
        if self.stopped:
            raise GameDataError('preparation_cancelled', 'Preparation stopped.', 409)

    def remaining_bytes(self, *, kind):
        assert kind == 'metadata'
        return MAX_METADATA_BYTES - self.received


def provider():
    source, calls = fixture()

    def fetch(ctx, url, *, body, limit):
        assert 'optionalres' not in url and not url.endswith(('.zip', '.7z', '.exe'))
        raw = source(url, body=body)
        assert len(raw) <= limit
        ctx.received += len(raw)
        return raw

    return Reverse1999Provider(metadata_fetch=fetch), calls


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
def test_real_discovery_stage_keeps_selected_sizes_unknown_and_never_acquires_assets(mode):
    adapter, calls = provider(); selection = request(mode); ctx = Context(selection)
    plan = adapter.plan(selection, ctx)
    assert len(calls) == 4 and 0 < ctx.received < MAX_METADATA_BYTES
    assert plan.download_bytes is None and plan.required_disk_bytes is None
    assert plan.runtime_available is False and plan.source_proof is None
    assert plan.handle['content_mode'] == mode and plan.handle['request']['content_mode'] == mode
    assert plan.handle['publisher_inventory']['download_bytes'] == 160  # full client, private evidence only
    assert plan.handle['selection_bytes'] == {'text': None, 'shared': None, 'audio': 0 if mode == 'text' else None}
    assert mode in plan.revision
    with pytest.raises(GameDataError, match='cannot be prepared'):
        adapter.download(plan, ctx)
    with pytest.raises(GameDataError, match='not a prepared game'):
        adapter.restore(plan.handle, ctx)
    assert len(calls) == 4  # no discovery/download/voice side effects from activation attempts


def test_region_and_unconfigured_transport_do_not_cross_fetch_global_data():
    adapter, calls = provider(); selection = request(region='cn')
    plan = adapter.plan(selection, Context(selection))
    assert calls == [] and plan.runtime_available is False and 'publisher_inventory' not in plan.handle
    assert Reverse1999Provider().plan(request(), Context(request())).runtime_available is False


def test_text_and_audio_selection_is_part_of_plan_identity_and_old_handle_requires_repair():
    adapter, _ = provider(); text = request(); plan = adapter.plan(text, Context(text))
    with pytest.raises(GameDataError) as changed:
        adapter.download(plan, Context(request('text-audio')))
    assert changed.value.code == 'game_data_plan_changed'
    old = dict(plan.handle); old.pop('content_mode')
    with pytest.raises(GameDataError) as missing:
        adapter.restore(old, Context(text))
    assert missing.value.code == 'repair_needed'


def test_missing_content_mode_and_cancelled_or_exhausted_plan_never_access_network():
    adapter, calls = provider(); selection = request(); del selection.content_mode
    with pytest.raises(GameDataError) as old:
        adapter.plan(selection, Context(selection))
    assert old.value.code == 'repair_needed'
    ctx = Context(request()); ctx.stopped = True
    with pytest.raises(GameDataError):
        adapter.plan(ctx.request, ctx)
    ctx = Context(request()); ctx.received = MAX_METADATA_BYTES
    with pytest.raises(GameDataError) as budget:
        adapter.plan(ctx.request, ctx)
    assert budget.value.code == 'transfer_budget_exceeded' and not calls


def test_optional_voice_service_is_not_a_dependency_of_text_preparation(monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError('Text-only source planning queried voices')
    monkeypatch.setattr('backend.reverse1999_release.optional_voices', unexpected)
    adapter, _ = provider(); selection = request('text')
    plan = adapter.plan(selection, Context(selection))
    assert not isinstance(plan, SnapshotSource) and plan.handle['selection_bytes']['audio'] == 0


def test_source_outage_never_returns_an_old_or_ready_plan():
    def unavailable(*_args, **_kwargs):
        raise ValueError('Owned invalid source response')
    adapter = Reverse1999Provider(metadata_fetch=unavailable); selection = request()
    with pytest.raises(GameDataError) as error:
        adapter.plan(selection, Context(selection))
    assert error.value.code == 'reverse1999_source_unavailable' and error.value.status == 503
