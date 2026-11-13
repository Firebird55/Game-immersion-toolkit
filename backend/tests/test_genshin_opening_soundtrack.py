"""Protect the opening-film dub, timing and payload when a release changes."""
import hashlib

import pytest

from backend import genshin_opening_soundtrack as opening, genshin_publisher as publisher
from backend.genshin_cinematics import opening_performances
from backend.local_voice import _source_suffix


def chunk(kind, index, payload, *, content=0):
    header = bytearray(32)
    header[:4] = kind
    header[4:8] = (24 + len(payload)).to_bytes(4, 'big')
    header[9], header[12], header[15] = 24, index, content
    return bytes(header) + payload


class Asset:
    def __init__(self, data):
        self.data = data
        self.size = len(data)
        self.digest = hashlib.md5(data).hexdigest()

    def read(self, directory, start, length):
        return self.data[start:start + length]


def test_repacked_movie_matches_dub_content_and_authenticates_each_export(tmp_path, monkeypatch):
    track = b'HCA\x00japanese'
    digest = hashlib.sha256(track).hexdigest()
    monkeypatch.setattr(opening, 'TRACKS', {(0, 'unrelated movie'): digest})
    header = chunk(b'CRID', 0, b'header', content=1)
    data = header + chunk(b'@SFA', 5, track[:5]) + chunk(b'@SFV', 0, b'video') + chunk(b'@SFA', 5, track[5:])
    data += chunk(b'@SFA', 2, b'HCA\x00another dub')
    asset = Asset(data)
    assert opening.verified_track(asset, tmp_path) == (digest, track)
    binding = opening.binding(asset, tmp_path, 'stamp')
    audio = dict(binding, start_ms=24100, end_ms=28844)
    monkeypatch.setattr(publisher, 'movie_assets', lambda *_: {opening.MOVIE: asset})
    assert publisher.extract(audio, tmp_path) == track
    assert _source_suffix(track, audio, 'genshin') == '.hca'
    for override in ({'locale': 'en'}, {'movie': 'other'}, {'start_ms': 2}, {'track_sha256': 'wrong'}):
        with pytest.raises(ValueError):
            publisher.extract(audio | override, tmp_path)
    for malformed in (data[:-1], header + chunk(b'@SFA', 2, b'wrong'), data + chunk(b'@SFA', 3, track)):
        assert opening.binding(Asset(malformed), tmp_path, 'stamp') is None
    asset.digest = '0' * 32
    with pytest.raises(ValueError):
        publisher.extract(audio, tmp_path)


def test_japanese_mix_requires_all_captions_and_the_reviewed_line_and_clock():
    sentences = ['一', '二', '三', *(text for _, _, text in opening.JAPANESE_LINES.values())]
    intervals = [(100, 200), (300, 400), (500, 600), (24100, 28844), (30781, 31725), (32025, 36986)]
    rows = [{'text_id': 'genshin:' + str(3500401 + i), 'source_text': text,
             'texts': {'ja': text}, 'english': '', 'chinese': '', 'audio': None} for i, text in enumerate(sentences)]
    rows[4]['text_id'] += ':female'
    def captions():
        return [{'text_id': f'genshin:movie:{opening.MOVIE}:{i}:{a}-{b}', 'source_text': text}
                for i, ((a, b), text) in enumerate(zip(intervals, sentences), 1)]
    binding = {'publisher': 'release', 'movie': opening.MOVIE, 'locale': 'ja', 'track_sha256': next(iter(opening.TRACKS.values()))}
    cues = captions()
    opening_performances(cues, rows, 'ja', binding)
    assert [c['audio']['start_ms'] for c in cues if 'audio' in c] == [24100, 30781, 32025]
    for locale, source in [('en', binding), ('ja', None)]:
        cues = captions()
        opening_performances(cues, rows, locale, source)
        assert all('audio' not in c for c in cues)
    cues = captions()
    cues[-1]['text_id'] = cues[-1]['text_id'].replace('36986', '37000')
    opening_performances(cues, rows, 'ja', binding)
    assert 'audio' not in cues[-1]
    rows[-1]['source_text'] = '変更'
    cues = captions()
    opening_performances(cues, rows, 'ja', binding)
    assert all('audio' not in c for c in cues)
