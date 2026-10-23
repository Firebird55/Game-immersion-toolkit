"""Footage verification must preserve geometry and fail meaningful annotations."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

spec = importlib.util.spec_from_file_location('video_replay', Path(__file__).resolve().parents[2] / 'scripts/replay-video-ocr.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.mark.parametrize('size', [(800, 600), (1280, 720), (1920, 1080), (3840, 2160), (3440, 1440), (5120, 1440)])
def test_fit_keeps_square_pixels_and_pads_instead_of_distorting(size):
    source = Image.new('RGB', (160, 90), 'white')
    image = replay.prepare_frame(source, size)
    box = image.getbbox()
    assert image.size == size
    width, height = box[2]-box[0], box[3]-box[1]
    assert abs(width/height - 16/9) < .005
    assert source.size == (160, 90)


def test_unannotated_and_contradictory_replays_are_rejected():
    clip = {'game': 'nte', 'duration': 10}
    with pytest.raises(ValueError, match='Annotate'):
        replay.validate_clip(clip)
    with pytest.raises(ValueError, match='negative'):
        replay.validate_clip({**clip, 'expect_no_lines': True, 'expected': ['nte:a']})


@pytest.mark.parametrize('negative', [False, True])
def test_false_positive_is_not_a_passing_replay(negative):
    clip = {'name': 'Fixture', 'expected': [] if negative else ['nte:a'],
            'expected_exact': True, 'expect_no_lines': negative}
    lines = [SimpleNamespace(id=1, text_id='nte:b', channel='dialogue')]
    with pytest.raises(AssertionError):
        replay.validate_result(clip, lines, lines, {'nte:a', 'nte:b'})


def test_replay_checks_original_asset_queue_identity_not_only_count():
    clip = {'name': 'Fixture', 'expected': ['nte:a']}
    line = SimpleNamespace(id=1, text_id='nte:a', channel='dialogue')
    wrong = SimpleNamespace(id=2, text_id='nte:a', channel='dialogue')
    with pytest.raises(AssertionError, match='queues'):
        replay.validate_result(clip, [line], [wrong], {'nte:a'})


def test_reviewed_brief_caption_has_explicit_expectations_at_each_cadence():
    clip = {'name':'Brief boundary caption', 'game':'nte', 'duration':2, 'expected':['nte:a'],
            'expected_exact':True, 'expected_by_fps':{'4':['nte:a','nte:brief']}}
    replay.validate_clip(clip)
    lines = [SimpleNamespace(id=n, text_id=key, channel='dialogue') for n,key in enumerate(['nte:a','nte:brief'])]
    replay.validate_result(clip, lines[:1], lines[:1], {'nte:a','nte:brief'}, fps=2)
    replay.validate_result(clip, lines, lines, {'nte:a','nte:brief'}, fps=4)
    with pytest.raises(AssertionError):
        replay.validate_result(clip, lines[:1], lines[:1], {'nte:a','nte:brief'}, fps=4)


def test_cadence_expectations_cannot_silently_weaken_negative_annotations():
    with pytest.raises(ValueError, match='negative'):
        replay.validate_clip({'game':'nte','duration':2,'expect_no_lines':True,'expected_by_fps':{'4':['nte:a']}})
    with pytest.raises(ValueError, match='FPS'):
        replay.validate_clip({'game':'nte','duration':2,'expected':['nte:a'],'expected_by_fps':{'8':['nte:a']}})


def test_authored_context_preserves_independently_annotated_cue_identities():
    context = 'beyond:SCENE:context-100-900'
    members = ['beyond:SCENE:1', 'beyond:SCENE:2']
    coverage = replay.authored_coverage([{'text_id': context, 'member_text_ids': members}])
    lines = [SimpleNamespace(id=1, text_id=context, channel='dialogue')]
    clip = {'name': 'Context', 'expected': members, 'expected_exact': True}
    assert replay.validate_result(clip, lines, lines, {context}, coverage=coverage) == set(members)
    with pytest.raises(AssertionError, match='unexpected'):
        replay.validate_result({**clip, 'expected': members[:1]}, lines, lines, {context}, coverage=coverage)
    with pytest.raises(ValueError, match='context members'):
        replay.authored_coverage([{'text_id': context, 'member_text_ids': [members[0], 'beyond:OTHER:2']}])
    with pytest.raises(ValueError, match='context members'):
        replay.authored_coverage([{'text_id': context, 'member_text_ids': [{}, members[1]]}])


def test_catalog_only_ocr_replay_is_explicit_temporary_and_never_claims_native_audio(tmp_path, monkeypatch):
    import json
    source = tmp_path / 'genshin/textmap.json'
    source.parent.mkdir()
    source.write_text(json.dumps({'records': [{'text_id': 'genshin:1', 'audio': None}]}))
    original = source.read_bytes()
    directories = []
    def fake_replay(clip, resolution, directory, fps):
        directories.append(directory)
        assert directory != tmp_path
        row, = json.loads((directory / 'genshin/textmap.json').read_text())['records']
        assert row['audio'] == {'catalog_binding_only': 'genshin:1'}
        return {'passed': True}
    run = replay.replay
    monkeypatch.setattr(replay, 'replay', fake_replay)
    result = run({'game': 'genshin'}, (1280, 720), tmp_path, catalog_bindings_only=True)
    assert result['passed'] and 'mocked' in result['voice_evidence']
    assert source.read_bytes() == original
    assert not directories[0].exists()


def test_new_rpg_footage_cases_have_meaningful_positive_and_negative_annotations():
    import json
    path = Path(__file__).with_name('fixtures') / 'new-rpg-video-ocr.json'
    cases = json.loads(path.read_text())['clips']
    for game in ('starrail', 'genshin', 'endfield'):
        clips = [clip for clip in cases if clip['game'] == game]
        assert any(clip.get('expected') for clip in clips)
        assert any(clip.get('expect_no_lines') for clip in clips)
        for clip in clips:
            replay.validate_clip(clip)
            assert clip['expected_exact'] and 'youtube.com/watch' in clip['source_url']
