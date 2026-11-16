import json
import struct
import wave

import pytest

from backend.endfield_caption_context import EndfieldCaptionContext
from backend.multilingual_index import MultilingualTextIndex
from scripts.import_endfield_cue_context import audible_interval


def test_clock_precision_never_keeps_the_other_captions_samples(tmp_path):
    path = tmp_path / 'authored.wav'
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, 48000, 0, 'NONE', 'NONE'))
        out.writeframes(struct.pack('<h', 5) * 9600)
    with wave.open(str(path)) as pcm:
        assert audible_interval(pcm, 0, .10033, [(.1, .10033)]) == (0, 100)
        assert audible_interval(pcm, .1, .2, [(.1, .10033)]) == (101, 200)
        assert audible_interval(pcm, 0, .2, [(.08, .1)]) is None


def film_row(identity, text, previous=None, conditional=False):
    return {'text_id': identity, 'source_locale': 'en', 'audio_locale': 'en', 'source_text': text,
            'english': text, 'texts': {'en': text}, 'audio': {'file_id': identity},
            'channels': ['cinematic'], 'dialogue_kind': 'cinematic',
            'previous_text_id': previous, 'requires_previous': conditional}


def test_repeated_caption_needs_a_stable_adjacent_observation(tmp_path):
    first = film_row('endfield:film:scene:1', 'We must evacuate the building.')
    other = film_row('endfield:film:elsewhere:1', 'Wait outside the building.')
    second = film_row('endfield:film:scene:2@3', 'Yes!', first['text_id'], True)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': [first, other, second]}))
    index = MultilingualTextIndex('endfield', tmp_path)
    context = EndfieldCaptionContext()

    def scan(text, now, scope=1):
        hits = index.match_full_frame_voice_lines([text])
        return context.observe(index, [text], hits, channel='cinematic', scope=scope, now=now, stable_frames=2)

    assert not index.match_full_frame_voice_lines(['Yes!'])
    assert scan(first['source_text'], 0) is None
    assert scan('Yes!', .1) is None
    assert scan(first['source_text'], 1) is None
    assert scan(first['source_text'], 1.1) is None
    assert scan('Yes!', 1.2).text_id == second['text_id']
    assert scan('Yes!', 1.3, scope=2) is None
    scan(first['source_text'], 2)
    scan(first['source_text'], 2.1)
    scan(other['source_text'], 2.2)
    assert scan('Yes!', 2.3) is None
    scan(first['source_text'], 3)
    scan(first['source_text'], 3.1)
    assert scan('Yes!', 9) is None


@pytest.mark.parametrize('middle_text,conditional', [('Hold the bridge until I return.', False), ('Go!', True)])
def test_confirmed_successor_anchors_next_caption_without_advancing_on_identical_text(tmp_path, middle_text, conditional):
    opening = 'Take cover behind the wall.'
    a, b, c, d, e = [f'endfield:film:scene:{n}' for n in range(5)]
    rows = [film_row(a, opening), film_row(b, middle_text, a, conditional),
            film_row(c, 'Wait!', b, True), film_row(d, 'Wait!', c, True), film_row(e, 'Now!', d, True)]
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': rows}))
    index = MultilingualTextIndex('endfield', tmp_path)
    context = EndfieldCaptionContext()

    def scan(text, now):
        visible = index.match_full_frame_voice_lines([text])
        return context.observe(index, [text], visible, channel='cinematic', scope=1, now=now, stable_frames=2)

    assert scan(opening, 0) is None
    assert scan(opening, .1) is None
    assert scan(middle_text, .2).text_id == b
    assert scan('Wait!', .3) is None  # The middle caption has only one observation.
    scan(opening, .4)
    scan(opening, .5)
    for now in (.6, .7, .8):
        assert scan(middle_text, now).text_id == b
    for now in (.9, 1, 1.1, 1.2):
        assert scan('Wait!', now).text_id == c
    assert scan('Now!', 1.3) is None


@pytest.mark.parametrize('status', ['unknown', 'unavailable'])
@pytest.mark.parametrize('anchor_missing', [False, True])
def test_verified_missing_radio_uses_stable_authored_predecessor_without_borrowing_voice(tmp_path, status, anchor_missing):
    first = {**film_row('endfield:radio:first', 'Keep watching the eastern gate.'),
             'channels': ['dialogue'], 'dialogue_kind': 'radio', 'text_capture_verified': True}
    if anchor_missing:
        first.update(audio=None, voice_status='unavailable')
    missing = {**film_row('endfield:radio:second', 'Roger.', first['text_id'], True),
               'audio': None, 'voice_status': status, 'text_capture_verified': True,
               'channels': ['dialogue'], 'dialogue_kind': 'radio'}
    unrelated = {**film_row('endfield:unrelated', 'Roger.'),
                 'channels': ['dialogue'], 'dialogue_kind': 'radio'}
    path = tmp_path / 'textmap.json'
    payload = {'format': 2, 'game': 'endfield', 'source_locale': 'en', 'records': [first, missing, unrelated]}
    path.write_text(json.dumps(payload), encoding='utf-8')
    index = MultilingualTextIndex('endfield', tmp_path)
    index.capture_missing_audio = True
    context = EndfieldCaptionContext()

    def scan(text, now):
        hit = index.match_lines([text], exact_only=True)
        return context.observe(index, [text], [hit], channel='dialogue',
            scope=(index._signature, index.capture_missing_audio), now=now, stable_frames=2)

    assert index.match_text('Roger.') is None
    assert scan(first['source_text'], 0) is None
    assert scan('Roger.', .1) is None
    scan(first['source_text'], .2)
    scan(first['source_text'], .3)
    hit = scan('Roger.', .4)
    assert hit and hit.text_id == missing['text_id'] and hit.voice_status == status
    assert hit.is_verified_missing_audio and hit.kind == 'exact'
    assert scan('Roger.', .5).text_id == missing['text_id']
    index.capture_missing_audio = False
    assert scan('Roger.', .6) is None
    index.capture_missing_audio = True
    assert scan('Roger.', .7) is None
    scan(first['source_text'], 1)
    scan(first['source_text'], 1.1)
    assert scan('Roger.', 5) is None
    # An authored competing performance after the SAME predecessor remains
    # ambiguous, rather than being silently downgraded to text-only capture.
    unrelated['previous_text_id'] = first['text_id']
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert index.load()
    assert index.match_lines(['Roger.'], previous_text_id=first['text_id']) is None
