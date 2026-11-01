"""Keep the complete user corpus, captions and redactions in the public gate."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2] / 'tests/fixtures/game-screenshots'


def test_all_supplied_game_images_are_present_and_account_regions_are_redacted():
    cases = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))['cases']
    assert {case['attachment_number'] for case in cases} == set(range(1, 40)) - {1, 5, 6}
    assert Counter(case['game'] for case in cases) == dict(zzz=4, endfield=3, pragmata=3,
        nte=7, starrail=6, genshin=4, wuwa=9)
    assert len({case['id'] for case in cases}) == 36
    for case in cases:
        file = ROOT / case['file']
        assert file.parent == ROOT
        assert hashlib.sha256(file.read_bytes()).hexdigest() == case['sha256']
        assert case['voice_status'] == 'unknown', 'A still image cannot certify voice'
        assert case['expected_captions'] or case['presentation'] == 'menu'
        with Image.open(file) as image:
            assert list(image.size) == case['dimensions']
            for rectangle in case['redactions']:
                assert image.crop(rectangle).convert('RGB').getbbox() is None
