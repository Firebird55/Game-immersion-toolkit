"""The full shared fixture must return a real original WAV for native playback."""
import hashlib
import json
from pathlib import Path
import wave

from backend.android_probe import run


def test_all_game_fixtures_keep_the_retained_numeric_line_id_for_native_media(tmp_path):
    result = json.loads(run(tmp_path / 'authored-core'))
    policy = result['results']['game_caption_policy']
    for field in ('endfield_training_original_identity', 'endfield_training_original_fields',
                  'endfield_training_left_rejected', 'endfield_training_unpositioned_rejected',
                  'endfield_training_opt_out_rejected'):
        assert policy[field] is True
    audio = Path(result['private_audio_path'])
    assert audio.is_file()
    assert hashlib.sha256(audio.read_bytes()).hexdigest() == result['results']['old_recording_sha256']
    with wave.open(str(audio), 'rb') as source:
        assert source.getnchannels() == 1 and source.getsampwidth() == 2 and source.getnframes() > 0
