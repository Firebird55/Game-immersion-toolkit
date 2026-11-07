"""Regressions for authored multi-voice choices and game-specific Mandarin PCKs."""
import struct

import pytest

from backend import genshin_assets, hoyo_dialogue, starrail_assets, voice_pack_probe
from backend.voice_assets import voice_hash


@pytest.mark.parametrize('locale', ['zh-Hans', 'zh-Hant'])
@pytest.mark.parametrize('folder', ['Chinese', 'Chinese(PRC)'])
def test_genshin_mandarin_pack_probe_binding_and_extraction(tmp_path, locale, folder):
    suffix = r'\VO_Test\line.wem'
    source = folder + suffix
    canonical = 'Chinese' + suffix
    payload = b'RIFF' + bytes(8)
    path = tmp_path / 'GenshinImpact_Data' / 'StreamingAssets' / 'AudioAssets' / folder / '1001.pck'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'AKPK' + struct.pack('<6I', 60, 1, 4, 4, 4, 28) + bytes(12)
                     + struct.pack('<IQ4I', 1, voice_hash(source), 1, len(payload), 68, 0) + payload)

    links = genshin_assets.dialogue_links([{'voice': {'gameTrigger': 'Dialog', 'gameTriggerArgs': 8,
        'sourceNames': [{'sourceFileName': suffix[1:]}]}}], {'8': '19'}, locale)
    assert links[0]['source'] == canonical
    assert voice_pack_probe.probe('genshin', tmp_path, locale) == 'present'
    entries = hoyo_dialogue.inventory(tmp_path, 'genshin', locale)
    row, = hoyo_dialogue.records('genshin', links, {locale: {'19': 'Synthetic.'}}, locale, entries)
    assert row['audio']['source'] == source
    assert genshin_assets.extract_voice(tmp_path, row['audio'], None, None) == payload
    assert hoyo_dialogue.voice_namespace('starrail', locale) == 'Chinese(PRC)'
    with pytest.raises(ValueError, match='crosses locales'):
        genshin_assets.extract_voice(tmp_path, {**row['audio'], 'locale': 'ja'}, None, None)


def test_multi_voice_requires_one_consistent_authored_performance():
    def sentence(identity, primary=None):
        return {'TalkSentenceID': identity, 'TalkSentenceText': {'Hash': identity + 100}, 'VoiceID': primary}

    voices = [{'VoiceID': 6, 'VoicePath': 'greeting'}, {'VoiceID': 7, 'VoicePath': 'reply'}]
    sentences = [sentence(1), sentence(2), sentence(3, 7), sentence(4), sentence(5, 6)]
    multi = [{'TalkSentenceID': i, 'VoiceIDList': options}
             for i, options in [(1, [6]), (1, [6]), (2, [6]), (2, [7]), (3, [6]), (4, [8]), (5, [6])]]
    links = {row['id']: row for row in starrail_assets.sentence_links(sentences, voices, 'en', multi)}
    assert links['1']['source'] == links['5']['source'] == 'English/voice/greeting.wem'
    assert all(links[i]['voice_status'] == 'unavailable' and links[i]['source'] is None for i in ('2', '3', '4'))

    with pytest.raises(ValueError, match='multi-voice IDs'):
        starrail_assets.sentence_links(sentences, voices, 'en', [{'TalkSentenceID': 1, 'VoiceIDList': '6'}])
