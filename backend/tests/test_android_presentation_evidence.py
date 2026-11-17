"""Optional layout evidence cannot manufacture a native OCR confidence score."""
import copy

import pytest

from backend.android_host import presentation_lines


def spans():
    return [{'text': 'Authored speaker', 'confidence': .91,
        'bounding_rect': {'x1': 40, 'y1': 300, 'x2': 200, 'y2': 300,
            'x3': 200, 'y3': 350, 'x4': 40, 'y4': 350}}]


def test_real_line_geometry_and_zero_score_are_preserved_without_substitution():
    original = spans();before = copy.deepcopy(original)
    assert presentation_lines({'presentation_lines': original}, 1600, 900) == before
    assert original == before
    original[0]['confidence'] = 0
    assert presentation_lines({'presentation_lines': original}, 1600, 900)[0]['confidence'] == 0
    assert presentation_lines({}, 1600, 900) == []


@pytest.mark.parametrize('invalid', [None, True, float('nan'), float('inf'), -.1, 1.1, '0.99'])
def test_unknown_or_invalid_score_discards_all_optional_evidence(invalid):
    value = spans();value[0]['confidence'] = invalid
    assert presentation_lines({'presentation_lines': value}, 1600, 900) == []


def test_incomplete_out_of_frame_and_excessive_evidence_fails_closed():
    value = spans();del value[0]['bounding_rect']['x4']
    assert presentation_lines({'presentation_lines': value}, 1600, 900) == []
    value = spans();value[0]['bounding_rect']['x4'] = 1601
    assert presentation_lines({'presentation_lines': value}, 1600, 900) == []
    assert presentation_lines({'presentation_lines': spans() * 513}, 1600, 900) == []
