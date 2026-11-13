"""Verify release-paired caption timing, locale and actor bindings."""
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_films as films
from backend.voice_assets import voice_hash


def track():
    data = bytearray(86)
    data[:4] = b'RIFF'
    data[8:16] = b'WAVEfmt '
    struct.pack_into('<IHHI', data, 16, 66, 0xffff, 2, 48000)
    struct.pack_into('<H', data, 36, 48)
    struct.pack_into('<I', data, 44, 96000)
    return bytes(data)


def test_authored_caption_uses_referenced_voice_and_actor_or_retains_text(tmp_path, monkeypatch):
    tools = tmp_path / 'tools'
    source = 'Japanese/voice/vo_movie_m.wem'
    entries = {voice_hash(source): {'publisher': 'release', 'package': 'chapter'}}
    def extract(audio, path, game):
        assert audio['source'] == source and audio['publisher'] == 'release' and audio['locale'] == 'ja'
        assert (path, game) == (tools, 'starrail')
        return track()
    monkeypatch.setattr(films.voices, 'extract', extract)
    script = {'CaptionList': [{'CaptionTextID': {'Hash': 100}, 'StartTime': 0.5, 'EndTime': 1.125},
                              {'CaptionTextID': {'Hash': 101}, 'EndTime': 2.5}]}
    configs = [{'CutSceneName': 'Movie', 'CaptionPath': 'Config/CutSceneCaption/Movie_Caption.json',
                'CutScenePath': 'timeline', 'VoiceID': 20}]
    voc = [{'VoiceID': 20, 'VoicePath': 'vo_movie', 'VoiceType': 'Cutscene', 'IsPlayerInvolved': True}]
    catalog = SimpleNamespace(file=lambda p: configs if 'CutSceneConfig' in p else voc,
                              caption_scripts=lambda: [('Movie_Caption.json', script), ('Film_Caption.json', script)])
    rows = films.caption_rows(tools, catalog, {'ja': {'100': 'a', '101': 'b'}}, 'ja', entries)
    male, female, *other = rows
    assert male['player_voice'] == 'male' and male['audio']['start_ms'] == 500 and male['audio']['end_ms'] == 1125
    assert female['player_voice'] == 'female'
    assert all(r['audio'] is None and r['voice_status'] == 'unavailable' for r in [female, *other])
    assert len(rows) == 6
    configs[0]['CaptionPath'] = 'Config/CutSceneCaption/Another_Caption.json'
    with pytest.raises(ValueError):
        films.caption_rows(tools, catalog, {}, 'ja', entries)


def test_unrecognized_recording_format_has_no_authorized_clock():
    assert films._duration(track()) == 2000
    assert films._duration(bytes(86)) is None
    assert films._duration(track()[:70]) is None
