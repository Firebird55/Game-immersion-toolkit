import json
import struct

import pytest

from backend import hoyo_publisher_voice, language_worker, sophon_assets, zzz_assets, zzz_publisher
from backend.voice_assets import voice_hash


class File:
    def __init__(self, name, data):
        self.name, self.data, self.size = name, data, len(data)

    def read(self, _cache, start, size):
        return self.data[start:start + size]


def archive(name, source, clip):
    offset = 56
    header = b'AKPK' + struct.pack('<6I', offset - 8, 1, 0, 0, 0, 28)
    return File(name, header + struct.pack('<IQ4I', 1, voice_hash(source), 1, len(clip), offset, 0) + clip)


def test_publisher_resolves_cinema_timeline_and_numbered_speakers_only_by_unique_pack_id():
    examples = {
        'cinema': ('OngoingCinema_Cinema_Example_001', 'VO_Cinema/Ver3_2/VO_Example'),
        'numbered': ('Chat_Chapter230_32Actor_001', 'VO_Chat/Ver3_2/VO_32Actor'),
        'timeline': ('Vo_Csr_Timeline_Example_End_ExAmPlE_002', 'VO_TL/Ver2_0/VO_Example'),
        'ambiguous': ('Level_Partner_Example_001', 'VO_Level/Ver2_2/VO_Example'),
    }
    links = [{'text_id': key, 'source': name} for key, (name, _) in examples.items()]
    entries = {voice_hash(f'English(EN)/ex/{path}/{name}.wem'): {'package': 'first.pck'}
               for name, path in examples.values()}
    entries[voice_hash('English(EN)/ex/VO_Accompany/Ver2_2/VO_Example/Level_Partner_Example_001.wem')] = {'package': 'other.pck'}
    result = zzz_publisher.original_bindings(links, entries, 'en', '3.3.0')
    assert set(result) == {'cinema', 'numbered', 'timeline'}
    assert result['numbered']['source'].endswith('VO_32Actor/Chat_Chapter230_32Actor_001.wem')
    assert result['timeline']['source'].endswith('VO_Example/Vo_Csr_Timeline_Example_End_ExAmPlE_002.wem')


def test_publisher_directory_matches_future_source_names_and_requires_a_unique_full_file():
    short = zzz_publisher._short_id
    folder = 'VO_Future/Ver5_11/'
    actors = [folder + "VO_Actor'sFriend/", folder + 'VO_Other/']
    first, second = 'FutureScene_Line_01', 'FutureScene_Line_02'
    directory = zzz_publisher.voice_directory({'prefixes': actors, 'blocks': [
        short(folder), short(first), short(second), 0]})
    paths = {first: [actors[0]], second: actors}
    entries = {voice_hash('English(EN)/ex/' + prefix + name + '.wem'): {'package': 'current.pck'}
               for name, folders in paths.items() for prefix in folders}
    links = [{'text_id': key, 'source': key} for key in paths]
    result = zzz_publisher.original_bindings(links, entries, 'en', '5.11.0', directory)
    assert set(result) == {first}
    assert result[first]['source'] == 'English(EN)/ex/' + actors[0] + first + '.wem'
    assert zzz_publisher.original_bindings(links, entries, 'ja', '5.11.0', directory) == {}


@pytest.mark.parametrize('folder', ['VO_Breath/', 'VO_Bubble/Ver5_0/VO_A/', 'VO_Cinema/Film/',
                                    'VO_Level/Ver5_0/SFX_Bell/', 'VO_Galgame/VO_Effect/'])
def test_directory_does_not_promote_effects_or_whole_films_to_sentences(folder):
    short = zzz_publisher._short_id
    source = 'Galgame_Effect_01'
    directory = zzz_publisher.voice_directory({'prefixes': [folder], 'blocks': [short(folder), short(source), 0]})
    paths = [folder, 'VO_Galgame/VO_Effect/']
    entries = {voice_hash('English(EN)/ex/' + path + source + '.wem'): {'package': 'example.pck'} for path in paths}
    assert zzz_publisher.original_bindings([{'text_id': 'description', 'source': source}],
                                           entries, 'en', '5.0.0', directory) == {}


def test_truncated_and_unknown_directory_groups_are_rejected():
    short = zzz_publisher._short_id
    for blocks in ([short('VO_Actor/'), 341], [3245, 341, 0], [short('VO_Actor/'), -1, 0]):
        with pytest.raises(ValueError, match='directory'):
            zzz_publisher.voice_directory({'prefixes': ['VO_Actor/'], 'blocks': blocks})
    with pytest.raises(ValueError, match='directory path'):
        zzz_publisher.voice_directory({'prefixes': ['../outside/'], 'blocks': [5, 0]})


def test_short_and_qualified_scene_paths_require_same_verified_take():
    name = 'Galgame_Example_Billy_22'
    directory = 'VO_Galgame/VO_Billy/'
    exact = directory + name
    file_id = voice_hash('English(EN)/ex/' + exact + '.wem')
    entries = {file_id: {'package': 'voice.pck'}}
    def match(other):
        links = [{'text_id': 'one', 'source': ref} for ref in (name, other)]
        return zzz_publisher.original_bindings(links, entries, 'en', '3.3.0')
    assert match(exact)['one']['file_id'] == f'{file_id:016x}'
    assert match('Other/' + name) == {}
    assert match(directory + name + '_alt') == {}
    entries[voice_hash('English(EN)/ex/Other/' + name + '.wem')] = {'package': 'second.pck'}
    assert match('Other/' + name) == {}


def test_two_launcher_releases_keep_exact_historical_recordings_and_skip_missing_bodies(tmp_path, monkeypatch):
    current = ['a']
    def release(channel):
        assert channel == 'zzz-global'
        return {'channel': channel, 'version': '1.0.0', 'build': current[0],
                'manifests': {'zh-cn': [current[0]]}}
    def catalogue(build, data, locales, namespace, progress):
        assert namespace == 'Chinese(PRC)'
        assert locales == {'zh-Hant', 'en'}
        tag = build['build']
        return ([{'text_id': 'text_' + tag, 'source': 'VO_Message/Actor/Message_Different_' + tag,
                  'dialogue_kind': 'message'},
                 {'text_id': 'missing', 'source': 'VO_Message/Other/Message_Missing', 'dialogue_kind': 'message'},
                 {'text_id': 'choice', 'source': '', 'dialogue_kind':'choice', 'voice_status':'unknown'}],
                {'en': {'text_' + tag: 'test'}, 'zh-Hant': {'text_' + tag: '測試', 'missing':'其他','choice':'選擇'}},
                {'recorded_messages':2, 'ambiguous_messages':2}, None)
    def clip(tag):
        return b'RIFF' + struct.pack('<I', 5) + b'WAVE' + tag.encode()
    def manifest(cache, channel, spec, suffixes):
        assert channel == 'zzz-global' and suffixes == ('.pck',)
        tag, = spec
        source = 'Chinese(PRC)/ex/VO_Message/Actor/Message_Different_' + tag + '.wem'
        prefix = 'ZenlessZoneZero_Data/StreamingAssets/Audio/Windows/Full/'
        return {path: archive(path, source, clip(tag)) for folder in ('Cn', 'Jp') for path in [prefix + folder + '/record.pck']}
    monkeypatch.setattr(sophon_assets, 'release', release)
    monkeypatch.setattr(sophon_assets, 'manifest', manifest)
    monkeypatch.setattr(zzz_publisher, '_read_catalogue', catalogue)
    first_audio = None
    for tag in ('a', 'b'):
        current[0] = tag
        path = tmp_path / 'snapshot.json'
        language_worker.build('zzz', None, tmp_path, 'zh-Hant', ('en', 'nl'), path)
        snapshot = json.loads(path.read_bytes())
        rows = {row['text_id']:row for row in snapshot['records']}
        row = rows['text_' + tag]
        assert rows['choice']['voice_status'] == 'unknown' and rows['missing']['voice_status'] == 'unavailable'
        assert row['text_id'] == 'text_' + tag and row['voice_status'] == 'voiced' and row['audio_locale'] == 'zh-Hans'
        assert snapshot['coverage'] == {'recorded_messages': 2, 'ambiguous_messages': 2}
        assert snapshot['missing_translation_locales'] == ['nl']
        assert snapshot['install'] is None and snapshot['source_mode'] == 'publisher'
        assert zzz_assets.publisher_snapshot_available(tmp_path / 'tools', snapshot['fingerprint'])
        assert zzz_assets.extract_voice(None, row['audio'], tmp_path / 'tools', None) == clip(tag)
        first_audio = first_audio or row['audio']
    assert first_audio['publisher'] != row['audio']['publisher']
    assert zzz_assets.extract_voice(None, first_audio, tmp_path / 'tools', None) == clip('a')
    with pytest.raises(ValueError):
        zzz_assets.extract_voice(None, {**row['audio'], 'locale': 'ja'}, tmp_path / 'tools', None)
    assert not hoyo_publisher_voice.snapshot_available(tmp_path / 'tools', first_audio['publisher'], 'starrail')
