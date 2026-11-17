import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import wave

import pytest

from backend import wuthering_assets as assets, wuthering_cinematics as films
from backend import wuthering_context as context
from backend.languages import audio_locale
from backend.local_game import LocalDialogue
from backend.models import AppSettings
from backend.multilingual_index import MultilingualTextIndex
from backend.wuthering_bank import SceneSource
from backend.tests.test_wuthering_narrative import flat_blob, flow_database
from backend.tests.test_wuthering_bank import bank, direct
from backend.wuthering_bank import scene_sources


def scene_db(root, *, scene='owned_scene', event='play_owned_scene', variant=2, start=0., end=-1.):
    def float_bits(value):
        return struct.unpack('<i', struct.pack('<f', value))[0]
    with sqlite3.connect(root / 'db_cgVedio.db') as db:
        db.execute('CREATE TABLE IF NOT EXISTS videocaption (CgName TEXT, BinData BLOB)')
        db.execute('CREATE TABLE IF NOT EXISTS videosound (CgName TEXT, GirlOrBoy INTEGER, BinData BLOB)')
        db.execute('INSERT INTO videocaption VALUES (?,?)',
                   (scene, flat_blob({2: 30, 3: 60, 4: 'caption'})))
        db.execute('INSERT INTO videosound VALUES (?,?,?)', (scene, variant, flat_blob({
            3: f'/Game/Aki/WwiseAudio/Events/{event}.{event}', 4: float_bits(start), 5: float_bits(end)})))


def record(locale='en', *, text='The whole associated utterance remains in its authored scene.', **changes):
    return {'text_id': 'wuwa:caption', 'english': text, 'chinese': '', 'source_text': text,
            'source_locale': locale, 'audio_locale': audio_locale(locale), 'texts': {locale: text},
            'audio': None, 'voice_status': 'unavailable', 'dialogue_kind': 'cinematic', **changes}


def assign(root, rows, sources=None, shapes=None, locale='en', **proof):
    if 'plot_audio_sha256' not in proof:
        path = root / 'db_plot_audio.db'
        if not path.exists():
            complete_plot_table(root)
        proof['plot_audio_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    context.assign_contexts(root, rows, locale,
        {'play_owned_scene': sources or (SceneSource(101, None, 0),)},
        shapes if shapes is not None else {101: (2, 123457)}, **proof)


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_whole_native_scene_keeps_exact_frames_and_selected_dub(locale, tmp_path):
    scene_db(tmp_path)
    rows = [record(locale)]
    assign(tmp_path, rows, locale=locale)
    row = rows[0]
    assert LocalDialogue(**row).audio_scope == 'context'
    assert row['audio']['source_frames'] == 123457  # Not an integer millisecond.
    assert row['audio']['depot'] == films.MEDIA_ROOT + assets.VOICE_LOCALES[locale][0] + '/101.wem'
    assert 'start_ms' not in row['audio'] and 'end_ms' not in row['audio']
    assert row['audio']['scene'] == 'owned_scene' and row['audio']['event'] == 'play_owned_scene'


@pytest.mark.parametrize('change', [
    {'audio': {'depot': 'existing-exact-take'}, 'voice_status': 'voiced'},
    {'voice_status': 'unvoiced'}, {'voice_status': 'unknown'},
    {'dialogue_kind': 'readable'}, {'text': '… ... —'},
])
def test_existing_audio_and_known_silent_unknown_or_ellipsis_entries_survive(change, tmp_path):
    scene_db(tmp_path)
    rows = [record(**change)]
    original = copy.deepcopy(rows)
    assign(tmp_path, rows)
    assert rows == original


@pytest.mark.parametrize('shape', [(2, 17280001), (6, 48000), (3, 48000), (2, 0),
                                   (False, 48000), (2, True), None])
def test_duration_or_channel_metadata_never_becomes_a_fallback(shape, tmp_path):
    scene_db(tmp_path)
    rows = [record()]
    assign(tmp_path, rows, shapes={101: shape})
    assert rows[0]['audio'] is None and rows[0]['voice_status'] == 'unavailable'


def test_native_muted_carrier_is_not_promoted_by_its_real_source_and_short_duration(tmp_path):
    # Observed native carrier shape: root Play -> streamed sound, Volume=-96 dB.
    # It is a genuine original recording, but this event supplies no audible
    # ownership proof. Do not amplify it into a spoken sentence or call it silent.
    scene_db(tmp_path, event='owned_scene')
    sources = scene_sources(bank(direct(properties={0: -96})), 'owned_scene', {101})
    assert sources == (SceneSource(101, None, 0, True),)
    rows = [record()]
    original = copy.deepcopy(rows)
    context.assign_contexts(tmp_path, rows, 'en', {'owned_scene': sources}, {101: (2, 123457)},
                            plot_audio_sha256=complete_plot_table(tmp_path))
    assert rows == original and rows[0]['voice_status'] == 'unavailable'


@pytest.mark.parametrize('options', [{'start': 2.5}, {'end': 20.}, {'start': float('nan')},
                                    {'variant': 0}, {'variant': 1}])
def test_partial_or_unresolved_player_callers_do_not_authorize_full_source(options, tmp_path):
    scene_db(tmp_path, **options)
    rows = [record()]
    assign(tmp_path, rows)
    assert rows[0]['audio'] is None


def test_one_caption_reused_in_other_scenes_is_not_owned_by_the_first_source(tmp_path):
    scene_db(tmp_path)
    scene_db(tmp_path, scene='other_scene', event='other_event')
    rows = [record()]
    assign(tmp_path, rows)
    assert rows[0]['audio'] is None


def test_separately_posted_caption_voice_cannot_be_replaced_by_scene_soundtrack(tmp_path):
    scene_db(tmp_path)
    with sqlite3.connect(tmp_path / 'db_cgVedio.db') as db:
        db.execute('UPDATE videocaption SET BinData=?',
                   (flat_blob({2: 30, 3: 60, 4: 'caption', 11: 1}),))
    rows = [record()]
    assign(tmp_path, rows, plot_audio_sha256=None)
    assert rows[0]['audio'] is None


def flagged_scene(root):
    scene_db(root)
    with closing(sqlite3.connect(root/'db_cgVedio.db')) as db, db:
        db.execute('UPDATE videocaption SET BinData=?',
                   (flat_blob({2:30,3:60,4:'caption',11:1}),))


def complete_plot_table(root, *, identity=None, data=None, collation='BINARY'):
    path=root/'db_plot_audio.db'
    with closing(sqlite3.connect(path)) as db, db:
        assert collation in ('BINARY','NOCASE')
        db.execute(f'CREATE TABLE PlotAudio (Id TEXT COLLATE {collation}, BinData BLOB)')
        if identity is not None:db.execute('INSERT INTO PlotAudio VALUES (?,?)',(identity,data))
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('locale',assets.SUPPORTED_LOCALES)
def test_flag_without_config_uses_only_independently_owned_complete_scene_after_full_table_proof(tmp_path,locale):
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path)
    rows=[record(locale)];assign(tmp_path,rows,locale=locale,plot_audio_sha256=digest)
    assert rows[0]['audio_scope']=='context' and rows[0]['voice_status']=='voiced'
    assert rows[0]['audio']['depot']==films.MEDIA_ROOT+assets.VOICE_LOCALES[locale][0]+'/101.wem'
    assert rows[0]['audio']['locale']==audio_locale(locale)


@pytest.mark.parametrize('data',[None,b'',b'unknown-or-missing-pack-config'])
def test_existing_empty_null_or_unresolved_external_config_keeps_its_veto(tmp_path,data):
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path,identity='caption',data=data)
    rows=[record()];assign(tmp_path,rows,plot_audio_sha256=digest)
    assert rows[0]['audio'] is None and rows[0]['voice_status']=='unavailable'


def test_absence_uses_native_sql_key_collation_and_never_python_case_assumptions(tmp_path):
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path,identity='CaPtIoN',collation='NOCASE')
    rows=[record()];assign(tmp_path,rows,plot_audio_sha256=digest)
    assert rows[0]['audio'] is None


def test_partial_or_unattested_table_is_never_treated_as_an_absence_inventory(tmp_path):
    flagged_scene(tmp_path);complete_plot_table(tmp_path)
    rows=[record()];assign(tmp_path,rows,plot_audio_sha256=None)
    assert rows[0]['audio'] is None


@pytest.mark.parametrize('fault',['unavailable','truncated','changed','malformed','wrong-schema'])
def test_bad_complete_table_proof_fails_actionably_without_mutating_records(tmp_path,fault):
    from backend.preparation_errors import PreparationFailure
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path);path=tmp_path/'db_plot_audio.db'
    if fault=='unavailable':path.unlink()
    elif fault=='truncated':path.write_bytes(path.read_bytes()[:128])
    elif fault=='changed':path.write_bytes(path.read_bytes()+b'new source bytes')
    elif fault=='malformed':path.write_bytes(b'not a database');digest=hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        with closing(sqlite3.connect(path)) as db, db:db.execute('DROP TABLE PlotAudio')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
    rows=[record()];before=copy.deepcopy(rows)
    with pytest.raises(PreparationFailure) as error:assign(tmp_path,rows,plot_audio_sha256=digest)
    assert error.value.code=='game_metadata_unavailable' and rows==before


def test_ordinary_update_that_adds_config_invalidates_old_absence_without_negative_caching(tmp_path):
    from backend.preparation_errors import PreparationFailure
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path);first=[record()]
    assign(tmp_path,first,plot_audio_sha256=digest);assert first[0]['audio']
    path=tmp_path/'db_plot_audio.db'
    with closing(sqlite3.connect(path)) as db, db:db.execute('INSERT INTO PlotAudio VALUES (?,NULL)',('caption',))
    with pytest.raises(PreparationFailure):assign(tmp_path,[record()],plot_audio_sha256=digest)
    current=[record()];assign(tmp_path,current,plot_audio_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert current[0]['audio'] is None


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
@pytest.mark.parametrize('shape', [(2, 123457), (6, 123457, 0x60f)])
def test_global_native_performance_cannot_borrow_localized_whole_scene_speech(tmp_path, locale, shape):
    scene_db(tmp_path)
    digest = complete_plot_table(tmp_path, identity='caption', data=flat_blob({0:'caption',2:'creature_shared',3:1}))
    rows = [record(locale)]
    original = copy.deepcopy(rows)
    assign(tmp_path, rows, locale=locale, shapes={101:shape}, plot_audio_sha256=digest)
    assert rows == original  # No translated words, silence or locale recording invented.


@pytest.mark.parametrize('shape', [(2, 123457), (6, 123457, 0x60f)])
def test_unflagged_caption_also_requires_complete_authenticated_language_role_inventory(tmp_path, shape):
    from backend.preparation_errors import PreparationFailure
    scene_db(tmp_path)
    digest = complete_plot_table(tmp_path)
    rows = [record()]
    assign(tmp_path, rows, shapes={101:shape}, plot_audio_sha256=None)
    assert rows[0]['audio'] is None
    with pytest.raises(PreparationFailure):
        assign(tmp_path, [record()], shapes={101:shape}, plot_audio_sha256='f'*64)
    assign(tmp_path, rows, shapes={101:shape}, plot_audio_sha256=digest)
    assert rows[0]['audio_scope'] == 'context'


@pytest.mark.parametrize('collation,blocked', [('BINARY',False),('NOCASE',True)])
def test_global_performance_veto_uses_native_config_key_collation(tmp_path, collation, blocked):
    scene_db(tmp_path)
    digest = complete_plot_table(tmp_path, identity='CaPtIoN',
        data=flat_blob({0:'CaPtIoN',2:'shared',3:1}), collation=collation)
    rows = [record()]
    assign(tmp_path, rows, plot_audio_sha256=digest)
    assert (rows[0]['audio'] is None) is blocked


def test_normal_update_adding_global_role_revokes_context_after_new_full_table_proof(tmp_path):
    from backend.preparation_errors import PreparationFailure
    scene_db(tmp_path)
    digest = complete_plot_table(tmp_path)
    previous = [record()]
    assign(tmp_path, previous, plot_audio_sha256=digest)
    assert previous[0]['audio']
    path = tmp_path/'db_plot_audio.db'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('INSERT INTO PlotAudio VALUES (?,?)', ('caption',flat_blob({0:'caption',2:'shared',3:1})))
    with pytest.raises(PreparationFailure):
        assign(tmp_path, [record()], plot_audio_sha256=digest)
    current = [record()]
    assign(tmp_path, current, plot_audio_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert current[0]['audio'] is None and current[0]['voice_status'] == 'unavailable'


@pytest.mark.parametrize('data', [None,b''])
def test_empty_native_role_cannot_establish_localized_film_speech(tmp_path, data):
    scene_db(tmp_path)
    digest = complete_plot_table(tmp_path, identity='caption',data=data)
    rows = [record()]
    assign(tmp_path, rows, plot_audio_sha256=digest)
    assert rows[0]['audio'] is None


def test_proven_config_absence_does_not_default_rover_or_fill_missing_native_branch(tmp_path):
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path);rows=[record()]
    assign(tmp_path,rows,(SceneSource(101,'female',0),SceneSource(102,'male',0)),{101:(2,123457)},
           plot_audio_sha256=digest)
    assert {r['player_voice']:r['voice_status'] for r in rows}=={'female':'voiced','male':'unavailable'}
    (tmp_path/'textmap.json').write_text(json.dumps({'format':2,'game':'wuwa','source_locale':'en','records':rows}),encoding='utf-8')
    index=MultilingualTextIndex('wuwa',tmp_path);assert index.ready
    for gender in ['unconfigured','male']:
        index.player_voice=gender;assert not index.match_lines([rows[0]['source_text']],channel='cinematic',exact_only=True)
    index.player_voice='female';assert index.match_lines([rows[0]['source_text']],channel='cinematic',exact_only=True)


@pytest.mark.parametrize('item',[{'TidTalkOption':'caption'},
    {'TidTalk':'caption','PlayVoice':False},{'TidTalk':'caption','Type':'AvgNarration'}])
def test_proven_config_absence_cannot_hide_a_silent_or_unknown_written_presentation(tmp_path,item):
    flagged_scene(tmp_path);digest=complete_plot_table(tmp_path)
    flow_database(tmp_path,[{'Name':'ShowTalk','Params':{'TalkItems':[item]}}])
    rows=[record()];assign(tmp_path,rows,plot_audio_sha256=digest)
    assert rows[0]['audio'] is None and rows[0]['voice_status']=='unavailable'


@pytest.mark.parametrize('item', [
    {'TidTalkOption': 'caption'},
    {'TidTalk': 'caption', 'PlayVoice': False},
    {'TidTalk': 'caption', 'Type': 'AvgNarration'},
])
def test_merged_cinematic_status_cannot_hide_a_known_written_or_silent_presentation(item, tmp_path):
    scene_db(tmp_path)
    flow_database(tmp_path, [{'Name': 'ShowTalk', 'Params': {'TalkItems': [item]}}])
    rows = [record()]
    assign(tmp_path, rows)
    assert rows[0]['audio'] is None and rows[0]['voice_status'] == 'unavailable'


def test_explicit_rover_branches_match_only_the_configured_player_and_preserve_missing_branch(tmp_path):
    scene_db(tmp_path)
    rows = [record()]
    sources = (SceneSource(101, 'female', 0), SceneSource(102, 'male', 0))
    assign(tmp_path, rows, sources, {101: (2, 123457)})
    assert {row['text_id'] for row in rows} == {'wuwa:caption:female', 'wuwa:caption:male'}
    assert next(row for row in rows if row['player_voice'] == 'male')['voice_status'] == 'unavailable'
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'wuwa',
        'source_locale': 'en', 'records': rows}), encoding='utf8')
    index = MultilingualTextIndex('wuwa', tmp_path)
    assert index.ready
    for selected in ('unconfigured', 'male'):
        index.player_voice = AppSettings(wuwa_rover_voice=selected).wuwa_rover_voice
        assert index.match_lines([rows[0]['source_text']]) is None
    index.player_voice = AppSettings(wuwa_rover_voice='female').wuwa_rover_voice
    hit = index.match_lines([rows[0]['source_text']])
    assert hit and hit.text_id == 'wuwa:caption:female' and hit.audio_scope == 'context'


def reference():
    return {'publisher': 'wuwa-' + 'a' * 64, 'locale': 'en', 'depot': films.MEDIA_ROOT + 'en/101.wem',
            'scene_context': True, 'scene': 'owned_scene', 'event': 'play_owned_scene',
            'source_frames': 123457, 'source_channels': 2}


@pytest.mark.parametrize('change', [{'source_frames': True}, {'source_frames': 17280001},
    {'source_channels': 6}, {'source_channels': False}, {'start_ms': 0}, {'end_ms': 100},
    {'scene': '../../unsafe'}, {'event': 'filename #r 100'}, {'playback_scope': 'full_track'}])
def test_context_references_require_bounded_exact_shape_without_decoder_directives(change):
    ref = reference()
    assert assets._validate_voice(ref) == ref['depot']
    with pytest.raises(ValueError):
        assets._validate_voice({**ref, **change})


def pcm(path, frames=123457, channels=2):
    with wave.open(str(path), 'wb') as output:
        output.setparams((channels, 2, 48000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\x01\0' * frames * channels)


@pytest.mark.parametrize('frames,channels', [(123457, 2), (123456, 2), (123458, 2), (123457, 1)])
def test_adapter_keeps_all_scene_frames_and_rejects_wrong_or_truncated_pcm(tmp_path, monkeypatch, frames, channels):
    def decode(command, **options):
        assert command[1:3] == ['-i', '-o'] and Path(command[-1]).name == 'source.wem'
        assert Path(command[-1]).read_bytes() == b'owned-source'
        pcm(Path(command[3]), frames, channels)
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    output = tmp_path / 'output.wav'
    if (frames, channels) == (123457, 2):
        assert assets.decode_voice_source(b'owned-source', reference(), output, 'decoder', tmp_path) is None
        with wave.open(str(output)) as decoded:
            assert decoded.getnframes() == 123457
    else:
        with pytest.raises(ValueError, match='verified source'):
            assets.decode_voice_source(b'owned-source', reference(), output, 'decoder', tmp_path)


def test_a_header_cannot_hide_truncated_pcm_behind_matching_total_file_size(tmp_path, monkeypatch):
    def decode(command, **options):
        output = Path(command[3])
        pcm(output)
        raw = output.read_bytes()
        # Keep total bytes and the declared data length, but replace the first
        # 16 PCM bytes with another header chunk. WAV metadata alone looks valid.
        output.write_bytes(raw[:36] + b'JUNK' + struct.pack('<I', 8) + bytes(8) + raw[36:-16])
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    with pytest.raises(ValueError, match='verified source'):
        assets.decode_voice_source(b'owned-source', reference(), tmp_path / 'out.wav', 'decoder', tmp_path)


def test_longer_whole_film_keeps_all_original_frames_without_extending_song_or_trim_contracts(tmp_path):
    # Real M0355 metadata shape: 321.063 seconds, longer than five minutes.
    scene_db(tmp_path)
    rows = [record()]
    assign(tmp_path, rows, shapes={101: (2, 15411020)})
    assert rows[0]['audio']['source_frames'] == 15411020
    assert rows[0]['audio_scope'] == 'context'
    assets._validate_voice({**rows[0]['audio'], 'publisher': 'wuwa-' + 'a' * 64})
    boundary = [record()]
    assign(tmp_path, boundary, shapes={101: (2, 17280000)})
    assert boundary[0]['audio']['source_frames'] == 17280000
    with pytest.raises(ValueError):
        assets._validate_voice({**rows[0]['audio'], 'publisher': 'wuwa-' + 'a' * 64, 'source_frames': 17280001})
    with pytest.raises(ValueError):
        assets._validate_voice({'depot': films.MEDIA_ROOT + 'en/101.wem', 'locale': 'en',
            'publisher': 'wuwa-' + 'a' * 64, 'start_ms': 0, 'end_ms': 321064})
