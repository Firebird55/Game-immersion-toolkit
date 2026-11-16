"""Context recordings cannot borrow another event, take or silent caption's voice."""
import io
import wave

import pytest

from backend import endfield_film_context as context, endfield_online


def pcm(samples):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
        output.writeframes(b''.join(int(value).to_bytes(2, 'little', signed=True) for value in samples))
    stream.seek(0)
    return wave.open(stream)


def test_context_keeps_complete_recording_for_overlap_repeat_and_lingering_text():
    # Existing line cuts reject overlaps/repeated clocks. A complete original
    # source retains their utterances without inventing a sentence boundary.
    with pcm([100] * 4000) as source:
        captions = [('overlap', .2, 1), ('repeat', .5, 1.5), ('repeat', 2, 2.5),
                    ('linger', 3.5, 4.5), ('already_verified', .1, .3)]
        rows = dict(context._contexts(captions, [('own_event', 0, 4)],
                                     {'own_event': (7, 'original', source)}, {'already_verified'}))
    assert rows == dict.fromkeys(('overlap', 'repeat', 'linger'), (7, 'original', 4000))


def test_context_rejects_competing_events_different_repeated_takes_and_codec_noise():
    with pcm([1, -1] * 1000 + [100] * 2000) as first, pcm([100] * 4000) as second:
        sources = {'first': (7, 'one', first), 'second': (8, 'two', second)}
        rows = dict(context._contexts([('quiet', .1, .5), ('overlap', 2.1, 2.5)],
                                     [('first', 0, 4), ('second', 2, 4)], sources, set()))
        assert rows == {'quiet': None, 'overlap': None}
        repeated = dict(context._contexts([('repeat', 2.1, 2.5), ('repeat', 5.1, 5.5)],
                                         [('first', 0, 4), ('second', 4, 8)], sources, set()))
        assert repeated == {'repeat': None}


def test_context_and_unresolved_caption_keep_text_player_and_saved_source_identity(tmp_path, monkeypatch):
    stamp = 'endfield-' + 'a' * 64
    class Catalog:
        revision = stamp
        def context_cues(self, dub):
            assert dub == 'english'
            return {('m_scene', 'caption'): (7, 'digest', 4000), ('f_scene', 'quiet'): None}
    tables = {'en': {'1': '{F}Female words.{M}Male words.', '2': 'A caption with unresolved speech.'}, 'ja': {}}
    rows = context.records(Catalog(), tables, 'en', {'caption': {'id': 1}, 'quiet': {'id': 2}}, set())
    assert rows[0]['source_text'] == 'Male words.' and rows[0]['player_voice'] == 'male'
    assert rows[0]['texts'] == {'en': 'Male words.'}
    assert rows[0]['audio_scope'] == 'context' and rows[0]['voice_status'] == 'voiced'
    assert rows[1]['audio'] is None and rows[1]['voice_status'] == 'unknown' and rows[1]['text_capture_verified']
    saved = rows[0]['audio']
    monkeypatch.setattr(context, 'cues', lambda tools, release, dub: Catalog().context_cues(dub))
    monkeypatch.setattr(context.films.release, 'media', lambda tools, release, dub, identity, digest:
                        b'original' if (release, dub, identity, digest) == (stamp, 'english', 7, 'digest') else None)
    assert endfield_online.extract(saved, tmp_path) == b'original'
    with pytest.raises(ValueError):
        endfield_online.extract({**saved, 'end_ms': 3000}, tmp_path)
