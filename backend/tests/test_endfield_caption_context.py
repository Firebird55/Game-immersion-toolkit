import json
import struct
import wave

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


def test_repeated_caption_needs_a_stable_adjacent_observation(tmp_path):
    def row(identity, text, previous=None, conditional=False):
        return {'text_id': identity, 'source_locale': 'en', 'audio_locale': 'en', 'source_text': text,
                'english': text, 'texts': {'en': text}, 'audio': {'file_id': identity},
                'channels': ['cinematic'], 'dialogue_kind': 'cinematic',
                'previous_text_id': previous, 'requires_previous': conditional}
    first = row('endfield:film:scene:1', 'We must evacuate the building.')
    other = row('endfield:film:elsewhere:1', 'Wait outside the building.')
    second = row('endfield:film:scene:2@3', 'Yes!', first['text_id'], True)
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
