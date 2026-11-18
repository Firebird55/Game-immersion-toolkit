"""Ordinary service audio stages with original-format, authored-only fixtures.

Native acceptance and codec execution use explicit model seams; no game/audio
download or real native playback is claimed by these service fixtures.
"""
import json
from pathlib import Path
import struct
import sys

import pytest

from backend import nte_game_data_voice as voice, nte_game_data_audio_snapshot as snapshot
from backend import nte_game_data_audio as audio, nte_publisher_pak as pak
from backend.tests.test_nte_game_data_text import setup
from backend.tests.test_nte_game_data import finish
from backend.game_data_protocol import GameDataError

CODEC = {'schema': 'nte-inventoried-audio-codecs-v1', 'manifest_sha256': 'a'*64,
    'executables': {'vgmstream': 'b'*64, 'ffmpeg': 'c'*64}}


def fixture(tmp_path, monkeypatch, locale='ja', *, bank_changes=None):
    original, request = setup(tmp_path, monkeypatch, locale, voiced=True, bank_changes=bank_changes)
    def codecs(layout):
        return {'vgmstream': tmp_path/'owned-vgmstream.exe', 'ffmpeg': tmp_path/'owned-ffmpeg.exe'}, CODEC
    monkeypatch.setattr(voice, 'codecs', codecs)
    monkeypatch.setattr(snapshot, 'codecs', codecs)
    return original, {**request, 'content_mode': 'text-audio'}


def download(service, plan, original):
    owned = service.plans[plan['plan_id']]['plan']
    original.forbid_all_http = owned.download_bytes == 0
    try:
        service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        return finish(service)['job']
    finally: original.forbid_all_http = False


def advance(service, original, request, predicate):
    for _ in range(20):
        plan = service.plan('nte', request)['game']; owned = service.plans[plan['plan_id']]['plan']
        if predicate(owned): return plan, owned
        assert plan['can_download'], plan
        job = download(service, plan, original)
        assert job['status'] == 'needs_plan', job
    pytest.fail('Bounded original audio fixture did not reach the required stage')


@pytest.mark.parametrize('locale', ['en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'])
def test_every_study_locale_prepares_all_emitted_originals_before_ready_and_restores_offline(tmp_path, monkeypatch, locale):
    original, request = fixture(tmp_path, monkeypatch, locale)
    service = original.service(); seen = []
    try:
        for _ in range(20):
            plan = service.plan('nte', request)['game']; assert plan['can_download'], plan
            owned = service.plans[plan['plan_id']]['plan']; seen.append(owned.stage)
            if owned.stage == 'audio-member-ranges':
                assert owned.download_bytes <= 64*1024**2+2*sum(row['bytes'] for row in audio._handle(
                    owned.handle['recipe'] if owned.handle['kind'] == 'banks' else owned.handle['recipe']['binding_recipe'])['verification'].values())
                with monkeypatch.context() as guard:
                    guard.setattr(pak.Archive, 'read', lambda *_: pytest.fail('Audio preflight read a member body'))
                    guard.setattr(pak.Archive, 'read_many', lambda *_: pytest.fail('Audio preflight parsed banks'))
                    repeated = service.plan('nte', request)['game']
                    assert repeated['revision'] == plan['revision']
                    plan = repeated
            job = download(service, plan, original)
            if job['status'] == 'complete': break
            assert job['status'] == 'needs_plan', (owned.stage, json.dumps(job))
            assert not (original.root/'nte/current.json').exists()
        else: pytest.fail('Original audio preparation did not complete')
        assert {'audio-member-ranges', 'process-audio-bindings', 'materialize-audio', 'finalize-audio'} <= set(seen)
        source = service.restore('nte'); payload = json.loads(source.snapshot_path.read_bytes())
        row, = payload['records']
        assert payload['content_mode'] == 'text-audio' and row['voice_status'] == 'voiced'
        assert row['audio'] and not row.get('audio_omitted_by_request')
        assert source.voice_source.has(row)
        assert row['audio']['locale'] == ('zh-Hans' if locale == 'zh-Hant' else locale)
        for name in ('nte_game_data_runtime', 'nte_game_data_audio', 'nte_game_data_content',
                'nte_publisher', 'nte_archive_metadata', 'nte_native_provider', 'nte_native_metadata'):
            monkeypatch.setitem(sys.modules, 'backend.'+name, None)
        # RuntimeLayout selection is an existing host capability, no NTE reader.
        original.forbid_all_http = True
        # Provider's runtime type check imports its tiny capability module;
        # use direct restored-source operation to forbid even that import.
        ctx = source.voice_source.context
        restored = snapshot.restore(source.restore_handle, ctx, source.voice_source.layout)
        assert restored.voice_source.has(row) and restored.source_proof == source.source_proof
        file = next((ctx.directory/'originals').glob('*.wem')); saved = file.read_bytes()
        file.write_bytes(saved[:-1]+bytes([saved[-1]^1]))
        assert not restored.voice_source.has(row)
        with pytest.raises(GameDataError): snapshot.restore(source.restore_handle, ctx, restored.voice_source.layout)
        file.write_bytes(saved)
        assert snapshot.restore(source.restore_handle, ctx, restored.voice_source.layout).voice_source.has(row)
    finally: original.forbid_all_http = False; service.close()


@pytest.mark.parametrize('kind', ['banks', 'media'])
def test_bad_audio_range_retains_the_previous_stage_and_healthy_retry_can_finish(tmp_path, monkeypatch, kind):
    original, request = fixture(tmp_path, monkeypatch)
    service = original.service()
    try:
        plan, owned = advance(service, original, request, lambda row: row.stage == 'audio-member-ranges' and row.handle['kind'] == kind)
        previous = (original.root/'nte/stage.json').read_bytes()
        original.corrupt = True
        assert download(service, plan, original)['status'] == 'failed'
        assert (original.root/'nte/stage.json').read_bytes() == previous
        assert not (original.root/'nte/current.json').exists()
        original.corrupt = False
        plan = service.plan('nte', request)['game']
        assert download(service, plan, original)['status'] == 'needs_plan'
        final, _ = advance(service, original, request, lambda row: row.stage == 'finalize-audio')
        assert download(service, final, original)['status'] == 'complete'
    finally: service.close()


def test_unknown_voice_evidence_stays_unknown_and_never_requires_an_unrelated_wem(tmp_path, monkeypatch):
    original, request = fixture(tmp_path, monkeypatch)
    from backend import nte_assets as assets
    build = assets.build_records
    def unknown(*args, **kwargs):
        rows = build(*args, **kwargs)
        rows.append({**rows[0], 'text_id': 'nte:story:unknown', 'audio': None, 'voice_status': 'unknown'})
        return rows
    monkeypatch.setattr(assets, 'build_records', unknown)
    service = original.service()
    try:
        final, _ = advance(service, original, request, lambda row: row.stage == 'finalize-audio')
        assert download(service, final, original)['status'] == 'complete'
        source = service.restore('nte'); rows = json.loads(source.snapshot_path.read_bytes())['records']
        assert rows[1]['voice_status'] == 'unknown' and not source.voice_source.has(rows[1])
        assert len(list((source.snapshot_path.parent/'originals').glob('*.wem'))) == 1
    finally: service.close()


@pytest.mark.parametrize('change,expected_message', [({'version': 155}, 'unsupported format'),
    ({'bank_id': 998877}, 'declared event or voice language'),
    ({'language': 998877}, 'declared event or voice language')])
def test_original_banks_with_changed_format_or_wrong_event_dub_owner_fail_before_media_selection(tmp_path, monkeypatch, change, expected_message):
    original, request = fixture(tmp_path, monkeypatch, bank_changes=change)
    service = original.service()
    try:
        plan, _ = advance(service, original, request, lambda row: row.stage == 'process-audio-bindings')
        previous = (original.root/'nte/stage.json').read_bytes()
        job = download(service, plan, original)
        assert job['status'] == 'failed' and expected_message in job['message']
        assert (original.root/'nte/stage.json').read_bytes() == previous
        assert not (original.root/'nte/current.json').exists()
        assert not list((original.root/'nte/cache/tools/nte-publisher/game-data-audio/bindings').glob('*.json'))
    finally: service.close()


@pytest.mark.parametrize('version,event,language,expected', [(154,12,34,None),
    (155,12,34,'unsupported_game_format'), (155,99,77,'unsupported_game_format'),
    (154,99,34,'nte_voice_binding_unverified'), (154,12,77,'nte_voice_binding_unverified')])
def test_bank_header_distinguishes_schema_from_owner_evidence(version, event, language, expected):
    raw = b'BKHD'+struct.pack('<IIII',12,version,event,language)
    if expected is None: audio._validate_bank_header(raw,12,34)
    else:
        with pytest.raises(GameDataError) as caught: audio._validate_bank_header(raw,12,34)
        assert caught.value.code == expected


@pytest.mark.parametrize('damage', ['short', 'marker', 'short-chunk', 'long-chunk'])
def test_malformed_bank_shape_keeps_the_format_gate(damage):
    raw = b'BKHD'+struct.pack('<IIII',12,154,12,34)
    if damage == 'short': raw = raw[:19]
    elif damage == 'marker': raw = b'NOPE'+raw[4:]
    else: raw = raw[:4]+struct.pack('<I',8 if damage == 'short-chunk' else len(raw))+raw[8:]
    with pytest.raises(GameDataError) as caught: audio._validate_bank_header(raw,12,34)
    assert caught.value.code == 'unsupported_game_format'


def test_audio_source_rejects_final_pointer_change_interruption_and_codec_switch_without_losing_old_ready(tmp_path, monkeypatch):
    original, request = fixture(tmp_path, monkeypatch); service = original.service()
    try:
        plan, _ = advance(service, original, request, lambda row: row.stage == 'finalize-audio')
        assert download(service, plan, original)['status'] == 'complete'
        previous = (original.root/'nte/current.json').read_bytes(); source = service.restore('nte')
        from backend import nte_game_data_text as text, nte_updater_source as updater
        plan = service.plan('nte', request)['game']; recheck = text._recheck; calls = []
        saved = original.metadata[updater.VERSION_URL]
        def change(*args):
            calls.append(True)
            if len(calls) == 2: original.metadata[updater.VERSION_URL] += b'!'
            return recheck(*args)
        with monkeypatch.context() as fault:
            fault.setattr(text, '_recheck', change)
            assert download(service, plan, original)['status'] == 'failed'
        original.metadata[updater.VERSION_URL] = saved
        assert len(calls) == 2 and (original.root/'nte/current.json').read_bytes() == previous
        plan = service.plan('nte', request)['game']; atomic = audio._atomic_file
        def interrupt(path, raw):
            if path.name == 'nte-source-receipt.json': raise OSError('Authored snapshot interruption')
            return atomic(path, raw)
        with monkeypatch.context() as fault:
            fault.setattr(audio, '_atomic_file', interrupt)
            assert download(service, plan, original)['status'] == 'failed'
        assert (original.root/'nte/current.json').read_bytes() == previous
        plan = service.plan('nte', request)['game']
        with monkeypatch.context() as fault:
            def newer(layout):
                return ({'vgmstream': tmp_path/'owned-vgmstream.exe', 'ffmpeg': tmp_path/'owned-ffmpeg.exe'},
                    {**CODEC, 'manifest_sha256': 'f'*64})
            fault.setattr(voice, 'codecs', newer)
            assert download(service, plan, original)['status'] == 'failed'
        assert (original.root/'nte/current.json').read_bytes() == previous
        assert download(service, service.plan('nte', request)['game'], original)['status'] == 'complete'
        assert service.restore('nte').restore_handle == source.restore_handle
        assert (original.root/'nte/current.json').read_bytes() == previous
    finally: service.close()


def test_normal_audio_growth_uses_successive_explicit_64mib_quotes():
    from types import SimpleNamespace
    cached = set(); source = SimpleNamespace(_cached=lambda index: b'ok' if index in cached else None,
        checksums=bytes(1600*4), item=SimpleNamespace(size=100*1024**2))
    members = [{'pak': 'original.pak', 'offset': 0, 'stored_bytes': 100*1024**2}]
    first = audio._wanted({'original.pak': source}, members)
    assert sum((row['stop']-row['first'])*65536 for row in first) == 64*1024**2
    for row in first: cached.update(range(row['first'], row['stop']))
    second = audio._wanted({'original.pak': source}, members)
    assert sum((row['stop']-row['first'])*65536 for row in second) == 36*1024**2
    assert min(row['first'] for row in second) == 1024


def test_partial_media_download_stays_an_intermediate_stage_until_every_quoted_batch_completes(tmp_path, monkeypatch):
    original, request = fixture(tmp_path, monkeypatch); service = original.service()
    try:
        advance(service, original, request, lambda row: row.stage == 'audio-member-ranges' and row.handle['kind'] == 'media')
        from backend import nte_game_data_ranges as ranges
        count = 0
        with monkeypatch.context() as smaller_fixture_budget:
            # A lower fixture budget exercises multiple real transport stages
            # without constructing a 100 MiB bank or audio file in CI.
            smaller_fixture_budget.setattr(pak, 'TRANSFER', 128*1024)
            smaller_fixture_budget.setattr(ranges, 'MAX_RANGE_BYTES', 128*1024)
            for _ in range(8):
                plan = service.plan('nte', request)['game']; owned = service.plans[plan['plan_id']]['plan']
                if owned.stage == 'materialize-audio': break
                assert owned.stage == 'audio-member-ranges' and owned.handle['kind'] == 'media'
                assert download(service, plan, original)['status'] == 'needs_plan'
                assert not (original.root/'nte/current.json').exists()
                count += 1
            else: pytest.fail('Explicit media stages did not finish')
        assert count >= 2
        plan, _ = advance(service, original, request, lambda row: row.stage == 'finalize-audio')
        assert download(service, plan, original)['status'] == 'complete'
    finally: service.close()


def test_missing_packaged_codec_keeps_the_bank_size_quote_but_blocks_transfers(tmp_path, monkeypatch):
    real_codecs = voice.codecs
    original, request = fixture(tmp_path, monkeypatch); service = original.service()
    try:
        advance(service, original, request, lambda row: row.stage == 'audio-member-ranges')
        monkeypatch.setattr(voice, 'codecs', real_codecs)
        before = len([row for row in original.calls if row['range']])
        with monkeypatch.context() as no_bodies:
            no_bodies.setattr(pak.Archive, 'read', lambda *_: pytest.fail('Codec-gated quote read a member'))
            plan = service.plan('nte', request)['game']
        owned = service.plans[plan['plan_id']]['plan']
        assert owned.stage == 'audio-member-ranges' and owned.download_bytes > 0
        assert not owned.runtime_available and not plan['can_download']
        with pytest.raises(GameDataError): service.download('nte', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        assert len([row for row in original.calls if row['range']]) == before
        assert not (original.root/'nte/current.json').exists()
    finally: service.close()


def test_reprocessing_a_missing_stage_receipt_reuses_verified_originals_without_replacing_old_hardlinks(tmp_path, monkeypatch):
    original, request = fixture(tmp_path, monkeypatch); service = original.service()
    try:
        final, owned = advance(service, original, request, lambda row: row.stage == 'finalize-audio')
        assert download(service, final, original)['status'] == 'complete'
        source = service.restore('nte'); row, = json.loads(source.snapshot_path.read_bytes())['records']
        saved = next((source.snapshot_path.parent/'originals').glob('*.wem'))
        inode, raw = saved.stat().st_ino, saved.read_bytes()
        media_recipe = owned.handle['media_recipe']
        pointer = original.root/'nte/cache/tools/nte-publisher/game-data-audio/media'/(audio.content._identity(media_recipe)+'.json')
        pointer.unlink()
        assert service.restore('nte').voice_source.has(row)
        plan = service.plan('nte', request)['game']
        assert service.plans[plan['plan_id']]['plan'].stage == 'materialize-audio'
        atomic = audio._atomic_file
        def no_duplicate_original(path, data):
            assert path.suffix != '.wem', 'Unchanged original was unnecessarily replaced'
            return atomic(path, data)
        with monkeypatch.context() as guard:
            guard.setattr(audio, '_atomic_file', no_duplicate_original)
            assert download(service, plan, original)['status'] == 'needs_plan'
        assert saved.stat().st_ino == inode and saved.read_bytes() == raw
        assert service.restore('nte').voice_source.has(row)
    finally: service.close()
