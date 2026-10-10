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
