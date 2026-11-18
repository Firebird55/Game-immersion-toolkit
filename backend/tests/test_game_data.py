from dataclasses import asdict
import json
import os
import threading
import time

import pytest

from backend.game_data import GameDataService
from backend.game_data_protocol import (GameDataPlan, SnapshotSource, PreparationStage,
    SourceProof, GameDataError, MAX_METADATA_BYTES, VoiceChoiceSet)
from backend.local_game import LocalDialogue

REQUEST = {'region': 'global', 'source_locale': 'en', 'target_locales': ['zh-Hans'], 'content_mode': 'text-audio'}
PROOF = SourceProof('official', 'a' * 64, True)  # Authored receipt, never a publisher claim.


def test_storage_counts_verified_generation_hardlinks_once_but_distinct_copies_separately(tmp_path):
    from backend.game_data import _size
    cache = tmp_path / 'cache'; cache.mkdir()
    original = cache / 'original'; original.write_bytes(b'authored original package')
    old = cache / 'old'; old.mkdir()
    os.link(original, old / 'generation-input')
    assert _size(cache) == original.stat().st_size
    (old / 'distinct-copy').write_bytes(original.read_bytes())
    assert _size(cache) == original.stat().st_size * 2


class Voice:
    def has(self, row): return bool(row.get('audio'))
    def resolve(self, row, destination, *, cancelled):
        raise AssertionError('Capture/restore unexpectedly fetched a voice')


class Provider:
    def __init__(self):
        self.revision, self.downloads = 'authored-one', 0
        self.unknown = self.invalid = self.stage = self.oversize = self.asset_in_plan = False
        self.gate = None
        self.started = threading.Event()

    def plan(self, request, ctx):
        assert ctx.remaining_bytes(kind='metadata') == MAX_METADATA_BYTES
        ctx.consume_bytes(4352, kind='metadata')
        assert ctx.remaining_bytes(kind='metadata') == MAX_METADATA_BYTES - 4352
        if self.oversize: ctx.consume_bytes(MAX_METADATA_BYTES, kind='metadata')
        if self.asset_in_plan: ctx.consume_bytes(0, kind='asset')
        return GameDataPlan(self.revision, None if self.unknown else 8192 if request.content_mode == 'text-audio' else 2048, 16384,
            handle={'revision': self.revision}, runtime_available=True, download_is_upper_bound=True)

    def download(self, plan, ctx):
        self.downloads += 1; self.started.set()
        if self.gate: assert self.gate.wait(5)
        ctx.check(); ctx.consume_bytes(1000)
        ctx.progress('download', 1000, plan.download_bytes, 'Authored transfer.')
        handle = {'revision': plan.revision, 'content_mode': ctx.request.content_mode}
        if self.stage:
            (ctx.directory / 'authored-bootstrap.bin').write_bytes(b'authored bootstrap')
            return PreparationStage(handle, 'Check the remaining download size.')
        text = 'Follow the river beyond the bridge.'
        row = asdict(LocalDialogue('authored:bridge', text, '沿着河流走过桥。',
            audio={'publisher': 'authored', 'file_id': 'original-bridge'}, source_locale='en',
            source_text=text, audio_locale='en', texts={'en': text, 'zh-Hans': '沿着河流走过桥。'}, ocr_texts={}, voice_status='voiced'))
        if ctx.request.content_mode == 'text':
            row.update(source_voice_binding=row['audio'], audio=None, audio_omitted_by_request=True, text_capture_verified=True)
            with pytest.raises(GameDataError): ctx.consume_bytes(0, kind='audio')
        payload = {'format': 2, 'game': 'zzz', 'fingerprint': plan.revision, 'content_mode': ctx.request.content_mode,
            'source_locale': 'ja' if self.invalid else 'en', 'records': [row]}
        (ctx.directory / 'textmap.json').write_text(json.dumps(payload), encoding='utf8')
        return SnapshotSource(ctx.directory / 'textmap.json', handle, PROOF, Voice() if ctx.request.content_mode == 'text-audio' else None)

    def restore(self, handle, ctx):
        # Restore must have no permitted network bytes, including a zero-byte
        # preflight gate: the transport must fail before opening a connection.
        with pytest.raises(GameDataError): ctx.remaining_bytes(kind='metadata')
        return SnapshotSource(ctx.directory / 'textmap.json', handle, PROOF, Voice() if ctx.request.content_mode == 'text-audio' else None)


def row(service):
    return next(value for value in service.snapshot()['games'] if value['id'] == 'zzz')


def finish(service):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        value = row(service)
        if value['job'] and value['job']['status'] not in {'queued', 'running'}:
            return value
        time.sleep(.01)
    raise AssertionError('Authored preparation did not finish')


def download(service):
    value = service.plan('zzz', REQUEST)['game']
    return service.download('zzz', {'plan_id': value['plan_id'], 'revision': value['revision']})


def test_one_download_runs_all_stages_reports_cumulative_size_and_activates_once(tmp_path):
    from dataclasses import replace

    class StagedProvider(Provider):
        def plan(self, request, ctx):
            self.stage = ctx.stage_handle is None
            plan = super().plan(request, ctx)
            return replace(plan, stage='bootstrap') if self.stage else plan

        def download(self, plan, ctx):
            if not self.stage:
                second_stage.set()
                assert finish_stage.wait(5)
            return super().download(plan, ctx)

    second_stage, finish_stage = threading.Event(), threading.Event()
    provider = StagedProvider()
    activations = []
    service = GameDataService(tmp_path, {'zzz': provider}, on_activate=lambda ctx, _: activations.append(ctx.request.json()))
    try:
        first = service.start('zzz', REQUEST)['game']
        assert first['state'] == 'downloading' and first['job']['total_bytes'] is None
        assert second_stage.wait(5)
        active = row(service)
        assert active['job']['id'] == first['job']['id']
        assert active['job']['downloaded_bytes'] == 2 * 4352 + 1000
        assert active['job']['total_bytes'] == 2 * 4352 + 1000 + 8192
        assert active['has_checkpoint'] and not active['can_activate']
        assert not activations
        assert service.start('zzz', REQUEST)['game']['job']['id'] == first['job']['id']
        with pytest.raises(GameDataError, match='current game download'):
            service.start('zzz', {**REQUEST, 'content_mode': 'text'})
        finish_stage.set()
        complete = finish(service)
        assert complete['state'] == 'ready' and complete['job']['status'] == 'complete'
        assert complete['job']['downloaded_bytes'] == complete['job']['total_bytes'] == 2 * (4352 + 1000)
        assert complete['last_download_bytes'] == complete['job']['total_bytes']
        assert complete['installed_request'] == REQUEST
        assert provider.downloads == 2 and activations == [REQUEST]
    finally:
        finish_stage.set()
        service.close()


def test_automatic_download_stops_repeated_or_unavailable_stage(tmp_path):
    provider = Provider(); provider.stage = True
    service = GameDataService(tmp_path, {'zzz': provider})
    try:
        service.start('zzz', REQUEST)
        stalled = finish(service)
        assert stalled['job']['status'] == 'failed' and stalled['has_checkpoint']
        assert 'could not advance' in stalled['message'] and provider.downloads == 1
        provider.unknown = True
        service.start('zzz', REQUEST)
        unavailable = finish(service)
        assert unavailable['job']['status'] == 'failed' and provider.downloads == 1
        assert not unavailable['can_activate']
    finally:
        service.close()


@pytest.mark.parametrize('changed', [
    {'content_mode': 'text-audio'}, {'source_locale': 'ja'},
    {'target_locales': ['ko']}, {'region': 'cn'},
])
def test_same_revision_new_selection_never_borrows_previous_requests_readiness(tmp_path, changed):
    from dataclasses import replace
    provider = Provider(); activations = []
    service = GameDataService(tmp_path, {'zzz': provider}, on_activate=lambda ctx, _source: activations.append(ctx.request.json()))
    text = {**REQUEST, 'content_mode': 'text'}
    try:
        initial = service.plan('zzz', text)['game']
        service.download('zzz', {'plan_id': initial['plan_id'], 'revision': initial['revision']})
        assert finish(service)['state'] == 'ready'
        original_plan = provider.plan
        provider.plan = lambda request, ctx: replace(original_plan(request, ctx), download_bytes=None,
            runtime_available=False, message='Requested selection is not prepared yet.')
        proposed = service.plan('zzz', {**text, **changed})['game']
        assert proposed['revision'] == initial['revision'] == proposed['installed_revision']
        assert proposed['state'] == 'update_available' and not proposed['can_download']
        assert proposed['installed_request'] == text and proposed['job'] is None
        assert proposed['message'] == 'Requested selection is not prepared yet.'
        service.activate('zzz', {'revision': proposed['installed_revision']})
        assert activations == [text, text]  # Still the accepted old text, never the proposed audio/language.
        assert row(service)['state'] == 'update_available'
    finally: service.close()


def test_unknown_size_cannot_transfer_and_all_eight_games_are_reported(tmp_path):
    provider = Provider(); provider.unknown = True
    service = GameDataService(tmp_path, {'zzz': provider})
    try:
        assert len(service.snapshot()['games']) == 8
        value = service.plan('zzz', REQUEST)['game']
        assert value['download_bytes'] is None and not value['can_download']
        with pytest.raises(GameDataError): service.download('zzz', {'plan_id': value['plan_id'], 'revision': value['revision']})
        assert provider.downloads == 0
    finally: service.close()


@pytest.mark.parametrize('game', ['zzz', 'genshin', 'endfield', 'wuwa', 'nte', 'reverse1999', 'infinitynikki'])
def test_starrail_voice_choices_cannot_reach_another_game_provider_or_restore(game, tmp_path):
    from types import SimpleNamespace
    def forbidden(*a): pytest.fail('Foreign voice choices must be rejected before the provider')
    service = GameDataService(tmp_path, {game: SimpleNamespace(plan=forbidden)})
    selected = REQUEST | {'voice_choices': {'choice_set_sha256': 'a'*64,
        'choices': [{'group_key': 'starrail:copyright-avatar:7001', 'alternative': 'copyright-dub'}]}}
    try:
        with pytest.raises(GameDataError) as error: service.plan(game, selected)
        assert error.value.code == 'unsupported_game_voice_choices'
        with pytest.raises(GameDataError):
            service._validate_metadata({'schema': 'game-data-source-v1', 'game': game, 'directory': 'a'*64,
                'ready': False, 'revision': 'authored', 'message': '', 'request': selected, 'handle': {}}, game)
    finally: service.close()


def test_available_choice_metadata_is_public_only_for_starrail_and_does_not_enable_download(tmp_path):
    from types import SimpleNamespace
    available = VoiceChoiceSet('a'*64, 'b'*64, 'c'*64, 'd'*64,
        (('starrail:copyright-avatar:777001', 777001, 'en', 'ja'),))
    def plan(*a): return GameDataPlan('choices', None, None, available_voice_choices=available)
    deleted = []
    service = GameDataService(tmp_path, {'starrail': SimpleNamespace(plan=plan), 'zzz': SimpleNamespace(plan=plan)},
        on_activate=lambda ctx, source: deleted.append((ctx.request.json(), source)))
    try:
        selected = REQUEST | {'voice_choices': {'choice_set_sha256': available.choice_set_sha256,
            'choices': [{'group_key': 'starrail:copyright-avatar:777001', 'alternative': 'copyright-dub'}]}}
        actual = service.plan('starrail', selected)['game']
        assert actual['available_voice_choices'] == available.json() and not actual['can_download']
        for wrong in ({'choice_set_sha256': 'f'*64, 'choices': selected['voice_choices']['choices']},
                      {'choice_set_sha256': available.choice_set_sha256, 'choices': [
                          {'group_key': 'starrail:copyright-avatar:999001', 'alternative': 'selected-dub'}]}):
            with pytest.raises(GameDataError) as error: service.plan('starrail', REQUEST | {'voice_choices': wrong})
            assert error.value.code == 'voice_choices_changed'
        service.delete('starrail', {'revision': actual['revision']})
        assert deleted == [(selected, None)]
        with pytest.raises(GameDataError): service.plan('zzz', REQUEST)
    finally: service.close()


@pytest.mark.parametrize('attribute', ['oversize', 'asset_in_plan'])
def test_planning_refuses_large_metadata_or_any_asset_before_consent(tmp_path, attribute):
    provider = Provider(); setattr(provider, attribute, True)
    service = GameDataService(tmp_path, {'zzz': provider})
    try:
        with pytest.raises(GameDataError): service.plan('zzz', REQUEST)
        assert provider.downloads == 0 and row(service)['state'] == 'not_downloaded'
    finally: service.close()


def test_download_activates_real_validated_index_and_restores_locally(tmp_path):
    provider = Provider(); activations = []
    def activate(ctx, source):
        ctx.check(); assert ctx.index.ready and ctx.index.entry_count == 1
        assert source.voice_source.has(ctx.index._records[0])
        activations.append(ctx.index._records[0]['text_id'])
    service = GameDataService(tmp_path, {'zzz': provider}, on_activate=activate)
    try:
        download(service); value = finish(service)
        assert value['state'] == 'ready' and value['job']['status'] == 'complete', value
        assert activations == ['authored:bridge']
        assert value['installed_bytes'] > 0 and value['download_is_upper_bound']
    finally: service.close()
    reopened = GameDataService(tmp_path, {'zzz': provider}, on_activate=activate)
    try:
        assert reopened.restore('zzz').voice_source.has({'audio': {'file_id': 'authored'}})
        assert activations == ['authored:bridge', 'authored:bridge']
        assert provider.downloads == 1
    finally: reopened.close()


def test_bootstrap_archive_is_not_a_ready_snapshot(tmp_path):
    provider = Provider(); provider.stage = True; activated = []
    service = GameDataService(tmp_path, {'zzz': provider}, on_activate=lambda *args: activated.append(args))
    try:
        download(service); value = finish(service)
        assert value['state'] == 'not_downloaded' and value['job']['status'] == 'needs_plan'
        assert value['installed_bytes'] > 0 and not value['can_download'] and value['can_plan']
        assert activated == [] and service.restore('zzz') is None
    finally: service.close()


def test_failure_retains_previous_snapshot_pointer_and_complete_source_fields(tmp_path):
    provider = Provider(); service = GameDataService(tmp_path, {'zzz': provider})
    try:
        download(service); assert finish(service)['state'] == 'ready'
        before = (tmp_path / 'zzz/current.json').read_bytes()
        provider.revision = 'authored-two'; provider.invalid = True
        download(service); assert finish(service)['job']['status'] == 'failed'
        assert (tmp_path / 'zzz/current.json').read_bytes() == before
        restored = service.restore('zzz')
        assert json.loads(restored.snapshot_path.read_text())['records'][0]['texts'] == {'en': 'Follow the river beyond the bridge.', 'zh-Hans': '沿着河流走过桥。'}
    finally: service.close()


def test_duplicate_download_is_idempotent_and_repeated_current_source_remains_valid(tmp_path):
    provider = Provider(); provider.gate = threading.Event()
    service = GameDataService(tmp_path, {'zzz': provider})
    try:
        value = service.plan('zzz', REQUEST)['game']; request = {'plan_id': value['plan_id'], 'revision': value['revision']}
        first = service.download('zzz', request); assert provider.started.wait(2)
        second = service.download('zzz', request)
        assert first['game']['job']['id'] == second['game']['job']['id']
        provider.gate.set(); assert finish(service)['state'] == 'ready'; assert provider.downloads == 1
        provider.gate = None
        download(service); assert finish(service)['state'] == 'ready'
        assert service.restore('zzz') is not None
    finally: provider.gate.set() if provider.gate else None; service.close()


def test_old_a_b_a_job_cannot_publish_but_profile_data_is_retained(tmp_path):
    current = {'profile': 'a', 'owner': 'a:1'}
    provider = Provider(); provider.gate = threading.Event()
    activated = []
    root = lambda: tmp_path / current['profile'] / 'managed'
    service = GameDataService(root, {'zzz': provider}, owner_guard=lambda: current['owner'], on_activate=lambda *args: activated.append(args))
    try:
        preserved = tmp_path / 'a/history-and-recording'; preserved.parent.mkdir(); preserved.write_bytes(b'authored retained data')
        download(service); assert provider.started.wait(2)
        current.update(profile='b', owner='b:2'); assert row(service)['installed_bytes'] == 0
        current.update(profile='a', owner='a:3'); assert row(service)['job'] is None
        provider.gate.set()
        end = time.monotonic() + 2
        while any(job['status'] in {'queued', 'running'} for job in service.jobs.values()) and time.monotonic() < end: time.sleep(.01)
        assert activated == [] and not (root() / 'zzz/current.json').exists()
        assert preserved.read_bytes() == b'authored retained data'
        provider.gate = None
        download(service); assert finish(service)['state'] == 'ready'
        service.delete('zzz', {'revision': row(service)['revision']})
        assert preserved.read_bytes() == b'authored retained data'
    finally: provider.gate.set() if provider.gate else None; service.close()


def test_expired_or_changed_plan_does_not_fetch_assets(tmp_path):
    current = [0.0]; provider = Provider()
    service = GameDataService(tmp_path, {'zzz': provider}, clock=lambda: current[0])
    try:
        value = service.plan('zzz', REQUEST)['game']
        with pytest.raises(GameDataError): service.download('zzz', {'plan_id': value['plan_id'], 'revision': 'different'})
        current[0] = 901
        with pytest.raises(GameDataError): service.download('zzz', {'plan_id': value['plan_id'], 'revision': value['revision']})
        assert provider.downloads == 0
    finally: service.close()


def test_failed_activation_rolls_back_exact_previous_pointer_and_releases_index(tmp_path):
    provider = Provider(); fail = [False]
    def activate(ctx, source):
        assert ctx.index.ready
        if fail[0]: raise ValueError('authored activation failure')
    service = GameDataService(tmp_path, {'zzz': provider}, on_activate=activate)
    try:
        download(service); assert finish(service)['state'] == 'ready'
        pointer = tmp_path / 'zzz/current.json'; previous = pointer.read_bytes()
        fail[0] = True; provider.revision = 'authored-two'
        download(service); assert finish(service)['job']['status'] == 'failed'
        assert pointer.read_bytes() == previous
        assert all(job['context'].index is None for job in service.jobs.values())
    finally: service.close()


def test_corrupt_metadata_can_be_repaired_by_a_valid_download_without_losing_records(tmp_path):
    provider = Provider(); service = GameDataService(tmp_path / 'managed', {'zzz': provider})
    try:
        saved = tmp_path / 'actual-saved-recording.wav'; saved.write_bytes(b'authored saved recording')
        download(service); assert finish(service)['state'] == 'ready'
        (tmp_path / 'managed/zzz/current.json').write_bytes(b'authored corrupt metadata')
        assert row(service)['state'] == 'error' and row(service)['can_delete']
        provider.revision = 'authored-two'
        download(service); assert finish(service)['state'] == 'ready'
        assert saved.read_bytes() == b'authored saved recording'
    finally: service.close()


def test_delete_fences_a_delayed_plan_and_allows_deleting_without_a_reader(tmp_path):
    provider = Provider(); service = GameDataService(tmp_path, {'zzz': provider})
    entered, release = threading.Event(), threading.Event()
    original = provider.plan; failures = []
    def delayed(request, ctx):
        entered.set(); assert release.wait(3)
        return original(request, ctx)
    provider.plan = delayed
    def run():
        try: service.plan('zzz', REQUEST)
        except GameDataError as error: failures.append(error.code)
    thread = threading.Thread(target=run)
    try:
        thread.start(); assert entered.wait(2)
        service.delete('zzz', {'revision': None}); release.set(); thread.join(3)
        assert failures == ['game_data_changed'] and row(service)['plan_id'] is None
        provider.plan = original; download(service); assert finish(service)['state'] == 'ready'
        service.providers.clear()
        value = row(service); assert value['state'] == 'unsupported' and value['can_delete']
        deleted = service.delete('zzz', {'revision': value['revision']})
        assert deleted['freed_bytes'] > 0 and deleted['game']['installed_bytes'] == 0
    finally: release.set(); thread.join(3); service.close()


def test_saved_source_reference_reopens_original_voice_without_index_recompilation(tmp_path):
    provider = Provider(); descriptors = []
    service = GameDataService(tmp_path, {'zzz': provider}, on_activate=lambda ctx, source: descriptors.append(ctx.source_descriptor))
    try:
        download(service); assert finish(service)['state'] == 'ready'
        source = service.original_voice_source(descriptors[0], expected_owner='local')
        assert source.has({'audio': {'file_id': 'original-bridge'}})
        with pytest.raises(GameDataError):
            service.original_voice_source(descriptors[0], expected_owner='old-account')
        # Cache deletion cannot relabel an unfetched original as unvoiced.
        service.on_activate = None
        service.delete('zzz', {'revision': row(service)['revision']})
        with pytest.raises(GameDataError) as error:
            service.original_voice_source(descriptors[0], expected_owner='local')
        assert error.value.code == 'original_source_not_downloaded'
    finally: service.close()


def test_text_only_then_explicit_audio_plan_retains_data_and_requires_new_consent(tmp_path):
    provider = Provider(); service = GameDataService(tmp_path, {'zzz': provider})
    try:
        text_request = {**REQUEST, 'content_mode': 'text'}
        text = service.plan('zzz', text_request)['game']
        assert text['content_mode'] == 'text' and text['download_bytes'] == 2048
        service.download('zzz', {'plan_id': text['plan_id'], 'revision': text['revision']})
        assert finish(service)['state'] == 'ready'
        saved = tmp_path / 'outside-history.db'; saved.write_bytes(b'authored history retained')
        audio = service.plan('zzz', REQUEST)['game']
        assert audio['content_mode'] == 'text-audio' and audio['download_bytes'] == 8192
        assert provider.downloads == 1  # Planning audio did not transfer it.
        service.download('zzz', {'plan_id': audio['plan_id'], 'revision': audio['revision']})
        assert finish(service)['state'] == 'ready'
        assert saved.read_bytes() == b'authored history retained'
    finally: service.close()


def test_old_mode_less_metadata_is_rejected_without_original_audio_io(tmp_path):
    provider = Provider(); service = GameDataService(tmp_path, {'zzz': provider})
    try:
        download(service); assert finish(service)['state'] == 'ready'
        path = tmp_path / 'zzz/current.json'; value = json.loads(path.read_text())
        value['request'].pop('content_mode'); path.write_text(json.dumps(value))
        assert row(service)['state'] == 'error'
        with pytest.raises(GameDataError): service.restore('zzz')
        assert provider.downloads == 1
    finally: service.close()


def test_text_audio_cannot_be_ready_from_remote_bindings_without_materialized_originals(tmp_path):
    class MissingAudio(Provider):
        def restore(self, handle, ctx):
            source = super().restore(handle, ctx)
            source.voice_source.has = lambda _row: False
            return source
    service = GameDataService(tmp_path, {'zzz': MissingAudio()})
    try:
        download(service); value = finish(service)
        assert value['job']['status'] == 'failed'
        assert value['message'] == 'The requested original audio has not finished downloading.'
        assert not (tmp_path / 'zzz/current.json').exists()
    finally: service.close()


def test_account_change_after_owner_locked_activation_does_not_delete_committed_source(tmp_path):
    owner = ['A:1']; provider = Provider(); saved = []
    def activate(ctx, source):
        # A maintained host checks under its account lock, commits A, then
        # releases that lock. A later switch is not a failed A publication.
        ctx.check(); saved.append(source.snapshot_path)
        owner[0] = 'B:2'
    service = GameDataService(tmp_path, {'zzz': provider}, owner_guard=lambda: owner[0], on_activate=activate)
    try:
        download(service)
        until = time.monotonic() + 3
        while (not saved or service.jobs[(tmp_path, 'zzz')]['status'] == 'running') and time.monotonic() < until:
            time.sleep(.01)
        assert saved and saved[0].is_file()
        assert service.jobs[(tmp_path, 'zzz')]['status'] == 'complete'
        assert (tmp_path / 'zzz/current.json').is_file()
    finally: service.close()


def test_ready_source_survives_new_bootstrap_restart_failure_and_explicit_continuation(tmp_path):
    provider = Provider(); activated = []
    service = GameDataService(tmp_path, {'zzz': provider},
        on_activate=lambda ctx, _: activated.append(ctx.source_descriptor['revision']))
    try:
        download(service); assert finish(service)['state'] == 'ready'
        original = (tmp_path / 'zzz/current.json').read_bytes()
        provider.revision, provider.stage = 'authored-two', True
        download(service); assert finish(service)['job']['status'] == 'needs_plan'
        assert (tmp_path / 'zzz/current.json').read_bytes() == original
        assert json.loads((tmp_path / 'zzz/stage.json').read_text())['revision'] == 'authored-two'
        assert row(service)['installed_revision'] == 'authored-one'
        assert activated == ['authored-one']
    finally: service.close()
    provider.stage = False
    continued = []
    plan = provider.plan
    def inspect(request, ctx):
        continued.append(ctx.stage_handle)
        return plan(request, ctx)
    provider.plan = inspect
    service = GameDataService(tmp_path, {'zzz': provider},
        on_activate=lambda ctx, _: activated.append(ctx.source_descriptor['revision']))
    try:
        assert service.restore('zzz') is not None
        assert activated == ['authored-one', 'authored-one']
        provider.invalid = True
        download(service); assert finish(service)['job']['status'] == 'failed'
        assert (tmp_path / 'zzz/current.json').read_bytes() == original
        assert continued[-1] == {'revision': 'authored-two', 'content_mode': 'text-audio'}
        assert service.restore('zzz') is not None
        provider.invalid = False
        download(service); assert finish(service)['state'] == 'ready'
        assert row(service)['installed_revision'] == 'authored-two'
        assert not (tmp_path / 'zzz/stage.json').exists()
        assert activated[-1] == 'authored-two'
    finally: service.close()


def test_stage_handle_never_crosses_language_region_or_content_mode(tmp_path):
    provider = Provider(); provider.stage = True
    service = GameDataService(tmp_path, {'zzz': provider})
    try:
        download(service); finish(service)
        plan = provider.plan
        def inspect(request, ctx):
            assert ctx.stage_handle is None
            return plan(request, ctx)
        provider.plan = inspect
        for changed in ({'region': 'cn'}, {'source_locale': 'ja'}, {'target_locales': []}, {'content_mode': 'text'}):
            service.plan('zzz', {**REQUEST, **changed})
        assert row(service)['installed_revision'] is None
        assert not (tmp_path / 'zzz/current.json').exists()
    finally: service.close()
