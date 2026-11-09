"""Only synthetic authored cues, localization and deterministic Wwise branches."""
import struct

import pytest

from backend.nte_cinematics import movie_bindings, movie_records, subtitle_cues, timed_sequence_cues, SRT_ROOT
from backend.nte_assets import wwise_hash
from backend.pragmata_audio import read_bank_play_layers


def synthetic_switch(path, group='Sex_Switch', continuous=False, fade=False):
    def sound(oid, media):
        source = struct.pack('<IIBIIIB', oid, 262145, 2, media, 987, 100, 1)
        # Empty effects/metadata, bus/parent, flags, properties/ranges.
        return source + bytes(4) + struct.pack('<IIB', 0, 30, 0) + bytes(2)
    node = struct.pack('<I', 30) + bytes(4) + struct.pack('<IIB', 0, 0, 0)
    node += b'\x01\x00' + struct.pack('<f', -6) + bytes(1)
    node += bytes(6) + b'\x00\x01' + bytes(8)
    node += struct.pack('<BIIB', 0, wwise_hash(group), wwise_hash('female'), int(continuous))
    node += struct.pack('<3I', 2, 10, 11) + struct.pack('<I', 2)
    node += struct.pack('<3I', wwise_hash('female'), 1, 10) + struct.pack('<3I', wwise_hash('male'), 1, 11)
    node += struct.pack('<I', 2)
    node += struct.pack('<IBii', 10, 0, int(fade), 0) + struct.pack('<IBii', 11, 0, 0, 0)
    event = wwise_hash('Play_Vo_CG_Synthetic')
    objects = [(2, sound(10, 123)), (2, sound(11, 456)), (6, node),
               (3, struct.pack('<IHI', 20, 0x0403, 30)), (4, struct.pack('<IBI', event, 1, 20))]
    hirc = struct.pack('<I', len(objects)) + b''.join(struct.pack('<BI', kind, len(data)) + data for kind, data in objects)
    header = struct.pack('<3I', 154, event, wwise_hash('Chinese'))
    path.write_bytes(b'BKHD' + struct.pack('<I', len(header)) + header + b'HIRC' + struct.pack('<I', len(hirc)) + hirc)
    return event


@pytest.mark.parametrize('gender,media', [('female', 123), ('male', 456)])
def test_prefetch_cache_and_explicit_sex_switch_choose_only_authored_branch(tmp_path, gender, media):
    path = tmp_path / 'synthetic.bnk'
    event = synthetic_switch(path)
    assert read_bank_play_layers(path, allowed_versions=(154,)) == {}
    result = read_bank_play_layers(path, allowed_versions=(154,), switch_states={wwise_hash('Sex_Switch'): wwise_hash(gender)})
    assert result[event] == [{'media_id': media, 'gain_db': -6., 'delay_seconds': 0.}]


@pytest.mark.parametrize('changes', [{'group':'Other'}, {'continuous':True}, {'fade':True}])
def test_unverified_dynamic_playback_is_not_given_a_default_branch(tmp_path, changes):
    path = tmp_path / 'synthetic.bnk'
    synthetic_switch(path, **changes)
    assert read_bank_play_layers(path, allowed_versions=(154,), switch_states={wwise_hash('Sex_Switch'): wwise_hash('female')}) == {}


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


def test_movie_binding_cannot_choose_music_or_an_escaped_asset_path():
    row = {'StringTableID':'Sequence','Path':{'FilePath':'../../../Projects/HT/Content/Movies/FFMpeg/Story/Synthetic.mp4'},
           'PlayVoice':{'AssetPathName':'/Game/WwiseAudio/Events/CG/Guide/Synthetic/Play_Vo_CG_Synthetic.Play_Vo_CG_Synthetic'}}
    assert movie_bindings([row])[0]['subtitle'] == SRT_ROOT+'Synthetic.srt'
    assert movie_bindings([{**row,'PlayVoice':{'AssetPathName':row['PlayVoice']['AssetPathName'].replace('Play_Vo','Play_Sfx')}}]) == []
    assert movie_bindings([{**row,'Path':{'FilePath':row['Path']['FilePath'].replace('Synthetic','../escaped')}}]) == []


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


def test_sequence_clock_uses_dub_override_and_blocks_overlapping_unowned_or_repeated_cues():
    def cue(key, start, end, ns='ST_Fixture', ends=None):
        return dict(ns=ns, key=key, start_ms=start, end_ms=end, starts=[], ends=ends or [])
    rows = [cue('First', 100, 500, ends=[{'Key': 'EVoiceCultureType::ko', 'Value': 650}]),
            cue('Second', 600, 900), cue(None, 800, 850, ns=None),
            cue('Repeated', 900, 980), cue('Repeated', 1000, 1050), cue('Last', 1200, 1500)]
    payload = {'events': {'group': ['Play_Vo_CG_Fixture'], 'mixed': ['Play_Vo_CG_Fixture', '']},
               'groups': {'group': rows, 'mixed': rows}}
    event, en = timed_sequence_cues(payload, 'en')[0]
    assert event == 'Play_Vo_CG_Fixture' and [c['key'] for c in en] == ['First', 'Last']
    assert [c['key'] for c in timed_sequence_cues(payload, 'ko')[0][1]] == ['Last']
    rows[0]['ends'][0]['Key'] = 'EVoiceCultureType::future'
    with pytest.raises(ValueError, match='culture override'):
        timed_sequence_cues(payload, 'en')


def test_unknown_switch_value_does_not_fall_back_to_female(tmp_path):
    path = tmp_path / 'synthetic.bnk'
    synthetic_switch(path)
    assert read_bank_play_layers(path, allowed_versions=(154,),
                                 switch_states={wwise_hash('Sex_Switch'):wwise_hash('Other')}) == {}
