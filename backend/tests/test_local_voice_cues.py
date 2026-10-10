"""Authored cuts must be bounded by decoded original audio; never recorded audio."""
import json
from types import SimpleNamespace
import wave

import pytest

import backend.local_voice as module


@pytest.mark.parametrize('change', [{}, {'end_ms':3000}, {'start_ms':-1}, {'start_ms':'500'},
                                  {'gain_db':float('nan')}, {'end_ms':None}])
def test_original_movie_cut_is_exact_and_invalid_cues_never_encode(tmp_path, monkeypatch, change):
    data = tmp_path / 'cache'; data.mkdir()
    decoder = tmp_path / 'decoder'; decoder.touch()
    output = tmp_path / 'clips'
    audio = {'depot':'original', 'start_ms':500, 'end_ms':1300, 'gain_db':-6, **change}
    (data/'textmap.json').write_text(json.dumps({'install':str(tmp_path), 'fingerprint':'verified',
        'records':[{'text_id':'nte:synthetic','audio':audio}]}), encoding='utf8')
    adapter = SimpleNamespace(fingerprint=lambda _: 'verified', extract_voice=lambda *_: b'RIFF'+bytes(100))
    monkeypatch.setattr(module, 'asset_adapter', lambda _: (adapter,'synthetic'))
    monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'encoder')
    encoded = []
    def run(args, **options):
        if str(args[0]) == str(decoder):
            with wave.open(args[args.index('-o')+1], 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
                stream.writeframes(bytes(32000))  # A two-second original source.
        else:
            encoded.append(args)
            from pathlib import Path
            Path(args[-1]).write_bytes(bytes(200))
    monkeypatch.setattr(module.subprocess, 'run', run)
    service = module.LocalVoiceAssetService('nte', data, decoder, output)
    try:
        if change:
            with pytest.raises(ValueError):
                service.extract('nte:synthetic',1)
            assert not encoded and not list(output.glob('*.mp3'))
        else:
            service.extract('nte:synthetic',1)
            command = encoded[0]
            assert command[command.index('-ss')+1] == '0.5'
            assert command[command.index('-t')+1] == '0.8'
            assert command[command.index('-af')+1] == 'volume=-6.000000dB'
    finally:
        service.close()
