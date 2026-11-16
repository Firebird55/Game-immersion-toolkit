"""Only synthetic authored cues, localization and deterministic Wwise branches."""
import struct
import json

import pytest

from backend.nte_cinematics import movie_bindings, movie_namespaces, movie_records, subtitle_cues, timed_sequence_cues, SRT_ROOT
from backend.nte_assets import wwise_hash
from backend import nte_assets
from backend.pragmata_audio import read_bank_play_layers


def synthetic_switch(path, group='Sex_Switch', continuous=False, fade=False, *, event_name='Play_Vo_CG_Synthetic', language='Chinese', gain=-6, stream_type=2):
    def sound(oid, media):
        source = struct.pack('<IIBIIIB', oid, 262145, stream_type, media, 0x12345678, 100, 1)
        # Empty effects/metadata, bus/parent, flags, properties/ranges.
        return source + bytes(4) + struct.pack('<IIB', 0, 30, 0) + bytes(2)
    node = struct.pack('<I', 30) + bytes(4) + struct.pack('<IIB', 0, 0, 0)
    node += b'\x01\x00' + struct.pack('<f', gain) + bytes(1)
    node += bytes(6) + b'\x00\x01' + bytes(8)
    node += struct.pack('<BIIB', 0, wwise_hash(group), wwise_hash('female'), int(continuous))
    node += struct.pack('<3I', 2, 10, 11) + struct.pack('<I', 2)
    node += struct.pack('<3I', wwise_hash('female'), 1, 10) + struct.pack('<3I', wwise_hash('male'), 1, 11)
    node += struct.pack('<I', 2)
    node += struct.pack('<IBii', 10, 0, int(fade), 0) + struct.pack('<IBii', 11, 0, 0, 0)
    event = wwise_hash(event_name)
    objects = [(2, sound(10, 123)), (2, sound(11, 456)), (6, node),
               (3, struct.pack('<IHI', 20, 0x0403, 30)), (4, struct.pack('<IBI', event, 1, 20))]
    hirc = struct.pack('<I', len(objects)) + b''.join(struct.pack('<BI', kind, len(data)) + data for kind, data in objects)
    header = struct.pack('<3I', 154, event, wwise_hash(language))
    path.write_bytes(b'BKHD' + struct.pack('<I', len(header)) + header + b'HIRC' + struct.pack('<I', len(hirc)) + hirc)
    return event


@pytest.mark.parametrize('gender,media', [('female', 123), ('male', 456)])
@pytest.mark.parametrize('stream_type', [0, 1, 2])
def test_codec_cache_and_explicit_sex_switch_choose_only_authored_branch(tmp_path, gender, media, stream_type):
    path = tmp_path / 'synthetic.bnk'
    event = synthetic_switch(path, stream_type=stream_type)
    assert read_bank_play_layers(path, allowed_versions=(154,)) == {}
    result = read_bank_play_layers(path, allowed_versions=(154,), switch_states={wwise_hash('Sex_Switch'): wwise_hash(gender)})
    assert result[event] == [{'media_id': media, 'gain_db': -6., 'delay_seconds': 0.}]


@pytest.mark.parametrize('changes', [{'group':'Other'}, {'continuous':True}, {'fade':True}])
@pytest.mark.parametrize('stream_type', [0, 1, 2])
def test_unverified_dynamic_playback_is_not_given_a_default_branch(tmp_path, changes, stream_type):
    path = tmp_path / 'synthetic.bnk'
    synthetic_switch(path, stream_type=stream_type, **changes)
    assert read_bank_play_layers(path, allowed_versions=(154,), switch_states={wwise_hash('Sex_Switch'): wwise_hash('female')}) == {}


def storage_cache(path, stream_type, *, cinematic=True, mixed=False):
    event = 'Play_Vo_CG_StorageFixture'
    (path / 'banks').mkdir()
    bank = path / 'banks' / (event + '.bnk')
    synthetic_switch(bank, event_name=event, stream_type=stream_type)
    if mixed:
        def source(oid, media, storage):
            return (struct.pack('<IIBIIIB', oid, 262145, storage, media, 0x12345678, 4096, 1) +
                    bytes(4) + struct.pack('<IIB', 0, 30, 0) + bytes(2))
        layer = struct.pack('<I', 30) + bytes(4) + struct.pack('<IIB', 0, 0, 0) + bytes(2)
        objects = [(2, source(10, 123, 2)), (2, source(11, 456, 0)), (9, layer),
                   (3, struct.pack('<IHI', 20, 0x0403, 30)), (4, struct.pack('<IBI', wwise_hash(event), 1, 20))]
        hirc = struct.pack('<I', len(objects)) + b''.join(struct.pack('<BI', kind, len(data)) + data for kind, data in objects)
        header = struct.pack('<3I', 154, wwise_hash(event), wwise_hash('Chinese'))
        bank.write_bytes(b'BKHD' + struct.pack('<I', len(header)) + header + b'HIRC' + struct.pack('<I', len(hirc)) + hirc)
    text = {'ns': 'ST_Owned', 'key': 'Owned_Cue', 'value': '独立测试字幕。'}
    (path / 'localization.json').write_text(json.dumps({'zh-CN': [text]}), encoding='utf8')
    (path / 'media.json').write_text(json.dumps([nte_assets.MEDIA_ROOT + str(mid) + '.wem' for mid in [123, 456]]))
    (path / 'dialogue-events.json').write_text(json.dumps({'owned_cue': [event.lower()]}))
    if cinematic:
        (path / 'sequence-cues.json').write_text(json.dumps({'events': {'owned': [event]}, 'groups': {'owned': [
            dict(ns='ST_Owned', key='Owned_Cue', start_ms=100, end_ms=900, starts=[], ends=[])]}}))
    return bank, event


@pytest.mark.parametrize('stream_type', [0, 1, 2])
def test_cinematic_storage_requires_supported_clock_without_leaking_internal_metadata(tmp_path, stream_type):
    storage_cache(tmp_path, stream_type)
    rows = nte_assets.build_records(tmp_path, source_locale='zh-Hans')
    if stream_type == 2:
        assert len(rows) == 2 and all(row['voice_status'] == 'voiced' for row in rows)
        assert {row['audio']['start_ms'] for row in rows} == {100}
        assert {row['audio']['end_ms'] for row in rows} == {900}
        assert {row['audio']['gain_db'] for row in rows} == {-6}
        assert all('storage_type' not in row['audio'] for row in rows)
    else:
        assert len(rows) == 2
        assert all(not row['audio'] and row['voice_status'] == 'unavailable' and row['dialogue_kind'] == 'cinematic' for row in rows)


@pytest.mark.parametrize('stream_type', [0, 1, 2])
def test_exact_whole_recording_binding_preserves_its_schema_for_all_storage_formats(tmp_path, stream_type):
    storage_cache(tmp_path, stream_type, cinematic=False)
    rows = nte_assets.build_records(tmp_path, source_locale='zh-Hans')
    assert len(rows) == 2 and all(row['voice_status'] == 'voiced' for row in rows)
    assert all('storage_type' not in row['audio'] and 'start_ms' not in row['audio'] for row in rows)


def test_unsuitable_layer_cannot_disappear_from_a_partially_playable_cinematic_mix(tmp_path):
    bank, event = storage_cache(tmp_path, 0, mixed=True)
    layers = read_bank_play_layers(bank, allowed_versions=(154,), include_storage_type=True)[wwise_hash(event)]
    assert {row['storage_type'] for row in layers} == {0, 2}
    rows = nte_assets.build_records(tmp_path, source_locale='zh-Hans')
    assert len(rows) == 1 and not rows[0]['audio'] and rows[0]['voice_status'] == 'unavailable'
    assert rows[0]['dialogue_kind'] == 'cinematic'


def test_movie_cue_joins_owned_namespace_key_and_exact_original_timing():
    srt = '1\n00:00:01,000 --> 00:00:03,000\nSynthetic_Key\n'
    bindings = [{'subtitle': SRT_ROOT+'Synthetic.srt', 'event':'Play_Vo_CG_Synthetic', 'namespace':'ST_Sequence'}]
    variants = [{'player_voice': g, 'audio': {'depot':f'Chinese/{g}.wem'}} for g in ['female','male']]
    args = [bindings, {bindings[0]['subtitle']: srt}, {('ST_Sequence','Synthetic_Key'):'A synthetic movie line.'},
            {('ST_Sequence','Synthetic_Key'):'测试电影台词。'}, {'play_vo_cg_synthetic': variants}]
    rows = movie_records(*args)
    assert len(rows) == 2
    assert rows[0]['audio']['start_ms'] == 1000 and rows[0]['audio']['end_ms'] == 3000
    assert {r['player_voice'] for r in rows} == {'female','male'}
    assert movie_records(*[args[0], args[1], {('Wrong','Synthetic_Key'):'Wrong.'}, *args[3:]]) == []


@pytest.mark.parametrize('text', ['1\n00:00:03,000 --> 00:00:01,000\nSynthetic_Key',
                                 '1\n00:90:01,000 --> 00:90:03,000\nSynthetic_Key',
                                 '1\n00:00:01,000 --> 00:00:03,000\n../../file',
                                 '1\n00:00:01,000 --> 00:00:03,000\nA plain caption.'])
def test_bad_timing_or_non_key_subtitles_cannot_supply_original_clips(text):
    with pytest.raises(ValueError):
        subtitle_cues(text)


@pytest.mark.parametrize('event', ['Play_Vo_CG_Synthetic', 'Play_Vo_OwnedFuture'])
def test_movie_binding_cannot_choose_music_or_an_escaped_asset_path(event):
    row = {'StringTableID':'Sequence','Path':{'FilePath':'../../../Projects/HT/Content/Movies/FFMpeg/Story/Synthetic.mp4'},
           'PlayVoice':{'AssetPathName':f'/Game/WwiseAudio/Events/CG/Guide/Synthetic/{event}.{event}'}}
    assert movie_bindings([row])[0]['subtitle'] == SRT_ROOT+'Synthetic.srt'
    assert movie_bindings([{**row,'PlayVoice':{'AssetPathName':row['PlayVoice']['AssetPathName'].replace('Play_Vo','Play_Sfx')}}]) == []
    assert movie_bindings([{**row,'Path':{'FilePath':row['Path']['FilePath'].replace('Synthetic','../escaped')}}]) == []
    assert movie_bindings([{**row,'PlayVoice':{'AssetPathName':row['PlayVoice']['AssetPathName'].replace('/Events/CG/', '/Events/Dialogue/')}}]) == []
    assert movie_bindings([{**row,'PlayVoice':{'AssetPathName':row['PlayVoice']['AssetPathName'] + 'Other'}}]) == []


@pytest.mark.parametrize('event', ['Play_Vo_CG_Owned', 'Play_Vo_OwnedFuture'])
def test_original_registry_can_add_a_movie_alias_without_a_toolkit_alias_update(event):
    row = {'StringTableID': 'OwnedFutureAlias',
           'Path': {'FilePath': '../../../Projects/HT/Content/Movies/FFMpeg/Story/OwnedMovie.mp4'},
           'PlayVoice': {'AssetPathName': f'/Game/WwiseAudio/Events/CG/Owned/{event}.{event}'}}
    owners = movie_namespaces({'StringTableNamespaces.json': {'OwnedFutureAlias': 'Different.Authored.Namespace'}})
    binding, = movie_bindings([row], owners)
    assert binding['namespace'] == 'Different.Authored.Namespace'
    assert movie_bindings([row]) == []
    # FName aliases are insensitive to case; the original namespace is exact.
    assert movie_bindings([{**row, 'StringTableID': 'OWNEDFUTUREALIAS'}], owners) == [binding]
    srt = '1\n00:00:01,000 --> 00:00:02,000\nOwnedLine\n'
    events = {event.lower(): [{'player_voice': None, 'audio': {'depot': 'Owned/voice.wem'}}]}
    records = movie_records([binding], {binding['subtitle']: srt},
        {('Different.Authored.Namespace', 'OwnedLine'): 'An independently owned caption.'},
        {('Different.Authored.Namespace', 'OwnedLine'): '独立测试字幕。'}, events)
    assert len(records) == 1 and records[0]['audio']['start_ms'] == 1000
    assert movie_records([binding], {binding['subtitle']: srt},
        {('WrongOwner', 'OwnedLine'): 'Another caption.'},
        {('WrongOwner', 'OwnedLine'): '其他测试字幕。'}, events) == []


def test_missing_or_conflicting_registry_owners_cannot_borrow_legacy_aliases():
    assert movie_namespaces({}) is None
    with pytest.raises(ValueError, match='ownership'):
        movie_namespaces({}, required=True)
    owners = movie_namespaces({'StringTableNamespaces.json': {
        'Sequence': None, 'Future': 'Owned.One', 'FUTURE': 'Owned.Two', 'fUtUrE': 'Owned.One'}})
    assert owners == {'sequence': None, 'future': None}
    row = {'StringTableID': 'Sequence',
           'Path': {'FilePath': '../../../Projects/HT/Content/Movies/FFMpeg/Story/Owned.mp4'},
           'PlayVoice': {'AssetPathName': '/Game/WwiseAudio/Events/CG/Owned/Play_Vo_CG_Owned.Play_Vo_CG_Owned'}}
    assert movie_bindings([row], owners) == []
    assert movie_bindings([row], {}) == []


@pytest.mark.parametrize('registry', [[], {'Future': True}, {'Future': ''}, {'Future': 'x' * 513},
                                     {'Future': 'Invalid\0Namespace'}, {'': 'Owned'},
                                     {'invalid\nname': 'Owned'}])
def test_changed_movie_registry_shapes_are_not_silently_accepted(registry):
    with pytest.raises(ValueError, match='registry'):
        movie_namespaces({'StringTableNamespaces.json': registry})


@pytest.mark.parametrize(('table', 'namespace'), [
    ('Sequence_Legend', 'ST_Sequence_Legend'), ('WuChao', 'ST_Miandialogue_Wuchao'), ('HeiYu', 'ST_Main_BlackBird')])
def test_movie_binds_its_owning_string_table_even_when_another_table_reuses_the_key(table, namespace):
    row = {'StringTableID': table,
           'Path': {'FilePath': '../../../Projects/HT/Content/Movies/FFMpeg/Story/Synthetic.mp4'},
           'PlayVoice': {'AssetPathName': '/Game/WwiseAudio/Events/CG/Guide/Play_Vo_CG_Synthetic.Play_Vo_CG_Synthetic'}}
    binding, = movie_bindings([row])
    subtitles = {binding['subtitle']: '1\n00:00:01,000 --> 00:00:02,000\nFixture_Key'}
    en = {(namespace, 'Fixture_Key'): 'The legend begins.', ('ST_Sequence', 'Fixture_Key'): 'Another scene.'}
    zh = {(namespace, 'Fixture_Key'): '传说开始了。'}
    events = {'play_vo_cg_synthetic': [{'player_voice': None, 'audio': {'depot': 'fixture.wem'}}]}
    record, = movie_records([binding], subtitles, en, zh, events)
    assert record['text_id'] == f'nte:{namespace}:Fixture_Key'
    assert record['english'] == 'The legend begins.'
    assert movie_bindings([{**row, 'StringTableID': 'FutureStoryAlias'}]) == []


def test_repeated_cue_key_has_no_guessed_original_clip():
    binding = {'subtitle': SRT_ROOT+'Synthetic.srt', 'event':'Play_Vo_CG_Synthetic', 'namespace':'ST_Sequence'}
    text = '1\n00:00:01,000 --> 00:00:03,000\nSynthetic_Key\n\n2\n00:00:04,000 --> 00:00:06,000\nSynthetic_Key'
    assert movie_records([binding], {binding['subtitle']:text}, {('ST_Sequence','Synthetic_Key'):'Synthetic line.'},
                         {('ST_Sequence','Synthetic_Key'):'测试台词。'},
                         {'play_vo_cg_synthetic':[{'player_voice':None,'audio':{'depot':'Chinese/123.wem'}}]}) == []


@pytest.mark.parametrize('event', ['Play_Vo_CG_Fixture', 'Play_Vo_OwnedFuture'])
def test_sequence_clock_uses_dub_override_and_blocks_overlapping_unowned_or_repeated_cues(event):
    def cue(key, start, end, ns='ST_Fixture', ends=None):
        return dict(ns=ns, key=key, start_ms=start, end_ms=end, starts=[], ends=ends or [])
    rows = [cue('First', 100, 500, ends=[{'Key': 'EVoiceCultureType::ko', 'Value': 650}]),
            cue('Second', 600, 900), cue(None, 800, 850, ns=None),
            cue('Repeated', 900, 980), cue('Repeated', 1000, 1050), cue('Last', 1200, 1500)]
    payload = {'events': {'group': [event], 'mixed': [event, ''], 'music': ['Play_Sfx_Owned']},
               'groups': {'group': rows, 'mixed': rows, 'music': rows}}
    actual_event, en = timed_sequence_cues(payload, 'en')[0]
    assert actual_event == event and [c['key'] for c in en] == ['First', 'Last']
    assert len(timed_sequence_cues(payload, 'en')) == 1
    assert [c['key'] for c in timed_sequence_cues(payload, 'ko')[0][1]] == ['Last']
    rows[0]['ends'][0]['Key'] = 'EVoiceCultureType::future'
    with pytest.raises(ValueError, match='culture override'):
        timed_sequence_cues(payload, 'en')


@pytest.mark.parametrize('stream_type', [0, 1, 2])
def test_unknown_switch_value_does_not_fall_back_to_female(tmp_path, stream_type):
    path = tmp_path / 'synthetic.bnk'
    synthetic_switch(path, stream_type=stream_type)
    assert read_bank_play_layers(path, allowed_versions=(154,),
                                 switch_states={wwise_hash('Sex_Switch'):wwise_hash('Other')}) == {}
