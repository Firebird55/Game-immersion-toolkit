"""Synthetic update and presentation regressions; no installed assets are needed."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import nte_assets as assets, nte_cinematics
from backend.multilingual_index import MultilingualTextIndex
from backend.preparation_errors import PreparationFailure
from backend.tests.test_new_game_assets import bank


def cache(path, rows, events=()):
    path.mkdir(parents=True, exist_ok=True)
    (path / 'banks').mkdir()
    (path / 'localization.json').write_text(json.dumps({'en': rows}), encoding='utf8')
    (path / 'media.json').write_text('[]')
    (path / 'voice-events.json').write_text(json.dumps(events))


def test_only_proven_written_presentations_enter_opt_in_exact_capture(tmp_path):
    # A missing bank cannot turn a spoken line or mixed archive into silent text.
    fixtures = [
        ('ST_Bagel_Reply', 'Bagel_Synthetic_1', 'A synthetic written social reply.', 'unvoiced'),
        ('ST_PlayerBirthdayMail', 'UI_PlayerBirthday_Content_1', 'A synthetic birthday letter body.', 'unvoiced'),
        ('ST_DialogueSumUP', 'Synthetic_SumUp', 'A synthetic written scene summary.', 'unvoiced'),
        ('ST_File', 'F_Synthetic_1', 'A synthetic mixed character archive.', 'unknown'),
        ('ST_MainDialogue', 'Synthetic_1', 'A synthetic line with absent voice media.', 'unavailable'),
        ('ST_AmbianceDialogue', 'Synthetic_option_Player_1', 'A synthetic response option.', 'unknown'),
    ]
    cache(tmp_path, [{'ns': ns, 'key': key, 'value': value} for ns, key, value, _ in fixtures], ['Play_Vo_Synthetic_1'])
    rows = assets.build_records(tmp_path, source_locale='en')
    assert [r['voice_status'] for r in rows] == [r[3] for r in fixtures]
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('nte', tmp_path)
    assert index.match_lines([fixtures[0][2]]) is None
    index.capture_unvoiced = True
    assert index.match_lines([fixtures[0][2]]).voice_status == 'unvoiced'
    assert index.match_lines([fixtures[0][2].replace('synthetic', 'synthetix')]) is None
    for fixture in fixtures[3:]:
        assert index.match_lines([fixture[2]]) is None


def test_authored_event_overrides_written_modality_when_voice_is_unavailable(tmp_path):
    cache(tmp_path, [{'ns': 'ST_Bagel_Reply', 'key': 'Synthetic_1', 'value': 'Synthetic voiced social content.'}], ['Play_Vo_Synthetic_1'])
    assert assets.build_records(tmp_path, source_locale='en')[0]['voice_status'] == 'unavailable'


def test_legacy_bilingual_preparation_also_retains_verified_written_content(tmp_path):
    row = {'ns': 'ST_Bagel_Reply', 'key': 'Bagel_Synthetic_1', 'value': 'A synthetic written reply.'}
    cache(tmp_path, [row])
    (tmp_path / 'localization.json').write_text(json.dumps({'en': [row],
        'zh-CN': [{**row, 'value': '这是一条合成的文字回复。'}]}), encoding='utf8')
    records = assets.build_records(tmp_path)
    assert len(records) == 1 and records[0]['voice_status'] == 'unvoiced'


def test_new_wwise_version_fails_before_publishing_or_overwriting_last_good_index(tmp_path, monkeypatch):
    data = tmp_path / 'index'; data.mkdir()
    original = b'{"last_good":"synthetic"}'
    (data / 'textmap.json').write_bytes(original)
    monkeypatch.setattr(nte_cinematics, 'load_catalog', lambda _: [])
    monkeypatch.setattr(assets, 'ensure_extractor', lambda _: Path('synthetic-reader'))
    def read(_install, _tool, destination, *_args, **_kwargs):
        cache(destination, [{'ns': 'ST_MainDialogue', 'key': 'Synthetic_1', 'value': 'Synthetic dialogue.'}])
        (destination / 'banks/Play_Vo_Synthetic_1.bnk').write_bytes(bank(version=155))
    monkeypatch.setattr(assets, 'run_reader', read)
    with pytest.raises(PreparationFailure) as error:
        assets.index_language(tmp_path / 'game', data, 'en', [])
    assert error.value.code == 'unsupported_game_format'
    assert 'Wwise' in str(error.value)
    assert (data / 'textmap.json').read_bytes() == original
    assert not list(data.rglob('complete.json'))


def test_new_native_localization_format_returns_public_typed_error(tmp_path, monkeypatch):
    tool = tmp_path / 'tools/reader.dll'; tool.parent.mkdir(); tool.touch()
    monkeypatch.setattr(assets, 'dotnet_sdk', lambda: Path('dotnet'))
    monkeypatch.setattr(assets, '_archive_metadata', lambda *_: 'private-synthetic-key')
    monkeypatch.setattr(assets.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(returncode=3))
    with pytest.raises(PreparationFailure) as error:
        assets.run_reader(tmp_path / 'game', tool, tmp_path / 'output', 'index')
    assert error.value.code == 'unsupported_game_format'
    assert 'private-synthetic-key' not in str(error.value)


def test_movie_voice_reference_without_media_is_unavailable_and_new_cue_layout_fails(tmp_path):
    cache(tmp_path, [{'ns': 'ST_Sequence', 'key': 'Synthetic_1', 'value': 'A synthetic film subtitle.'}])
    binding = {'subtitle': nte_cinematics.SRT_ROOT + 'Synthetic.srt', 'event': 'Play_Vo_CG_Synthetic', 'namespace': 'ST_Sequence'}
    subtitle = tmp_path / 'cinema-subtitles.json'
    subtitle.write_text(json.dumps({binding['subtitle']: '1\n00:00:01,000 --> 00:00:02,000\nSynthetic_1'}))
    row = assets.build_records(tmp_path, [binding], source_locale='en')[0]
    assert row['voice_status'] == 'unavailable' and row['dialogue_kind'] == 'cinematic'
    subtitle.write_text(json.dumps({binding['subtitle']: 'A newly changed unsupported cue layout'}))
    with pytest.raises(PreparationFailure) as error:
        assets.build_records(tmp_path, [binding], source_locale='en')
    assert error.value.code == 'unsupported_game_format'


def test_installed_short_millisecond_srt_form_preserves_ffmpeg_integer_timing():
    cues = nte_cinematics.subtitle_cues('1\n00:00:01,5 --> 00:00:02,50\nSynthetic_Key\n')
    assert cues == [{'key': 'Synthetic_Key', 'start_ms': 1005, 'end_ms': 2050}]
    with pytest.raises(ValueError):
        nte_cinematics.subtitle_cues('1\n00:00:01,0050 --> 00:00:02,5000\nSynthetic_Key\n')


def test_loose_text_config_movie_hotfixes_and_removals_invalidate_without_voice_changes(tmp_path):
    game = tmp_path / 'Client/WindowsNoEditor/HT'
    original = assets.fingerprint(tmp_path)
    for relative in ('Content/Localization/Game/en/Game.locres', 'Config/DefaultGame.ini',
                     'Content/Movies/synthetic.mp4', 'Content/Paks/patch.hpw'):
        path = game / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'synthetic')
        changed = assets.fingerprint(tmp_path)
        assert changed != original
        path.unlink()
        assert assets.fingerprint(tmp_path) == original


def test_ambiguous_voice_key_preserves_separate_text_without_guessing_the_voice(tmp_path):
    cache(tmp_path, [{'ns': 'ST_MainDialogue', 'key': 'Synthetic_1', 'value': 'First synthetic scene.'},
                     {'ns': 'ST_Dialogue_Side', 'key': 'Synthetic_1', 'value': 'Different synthetic scene.'}],
          ['Play_Vo_Synthetic_1'])
    event = assets.wwise_hash('Play_Vo_Synthetic_1')
    (tmp_path / 'banks/Play_Vo_Synthetic_1.bnk').write_bytes(bank(version=154, bank_id=event,
        language=assets.wwise_hash('English'), event=event))
    (tmp_path / 'media.json').write_text(json.dumps(['HT/Content/WwiseAudio/Media/English/123.wem']))
    rows = assets.build_records(tmp_path, source_locale='en')
    assert len(rows) == 2
    assert all(row['audio'] is None and row['voice_status'] == 'unavailable' for row in rows)
