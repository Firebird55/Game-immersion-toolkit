"""Authored cuts must be bounded by decoded original audio; never recorded audio."""
import json
import io
from types import SimpleNamespace
import wave
from pathlib import Path

import pytest

import backend.local_voice as module


def test_original_fmod_and_wwise_containers_keep_decoder_suffix_for_single_and_batch(tmp_path, monkeypatch):
    data = tmp_path / 'cache'; data.mkdir()
    decoder = tmp_path / 'decoder'; decoder.touch()
    rows = [{'text_id': magic, 'audio': {'container': magic}} for magic in ('FSB4', 'FSB5', 'RIFF')]
    (data / 'textmap.json').write_text(json.dumps({'install': str(tmp_path), 'fingerprint': 'verified', 'records': rows}), encoding='utf-8')
    adapter = SimpleNamespace(fingerprint=lambda _: 'verified', extract_voice=lambda _root, audio, *_: audio['container'].encode() + bytes(100))
    monkeypatch.setattr(module, 'asset_adapter', lambda _: (adapter, ''))
    monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'encoder')
    seen = []
    def run(args, **_):
        if str(args[0]) == str(decoder):
            inputs = [Path(args[-1])] if '-o' in args else [Path(path) for path in args[2:]]
            for source in inputs:
                magic = source.read_bytes()[:4]
                assert source.suffix == ('.fsb' if magic in {b'FSB4', b'FSB5'} else '.wem')
                seen.append(magic)
                destination = args[args.index('-o') + 1] if '-o' in args else str(source) + '.wav'
                with wave.open(destination, 'wb') as stream:
                    stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8000)
                    stream.writeframes(bytes(16000))
        else:
            for value in args:
                if str(value).endswith('.mp3'):
                    Path(value).write_bytes(bytes(200))
    monkeypatch.setattr(module.subprocess, 'run', run)
    service = module.LocalVoiceAssetService('riseofthetombraider', data, decoder, tmp_path / 'clips')
    try:
        for number, row in enumerate(rows):
            assert (service.output_dir / service.extract(row['text_id'], number)).is_file()
        names = service.extract_batch([(row['text_id'], number + 10, '') for number, row in enumerate(rows)])
        assert all((service.output_dir / name).is_file() for name in names)
        assert seen == [b'FSB4', b'FSB5', b'RIFF'] * 2
        # Distinct cinematic captions share one original performance. Preserve
        # each line's file lifetime without decoding the entire scene repeatedly.
        for identity in ('caption-a', 'caption-b'):
            service._entries[identity] = {'container': 'RIFF', 'playback_scope': 'full_track'}
        first = service.extract('caption-a', 30)
        second = service.extract('caption-b', 31)
        assert seen == [b'FSB4', b'FSB5', b'RIFF'] * 2 + [b'RIFF']
        (service.output_dir / first).unlink()
        assert (service.output_dir / second).read_bytes() == bytes(200)
        batch = service.extract_batch([('caption-a', 32, ''), ('caption-b', 33, '')])
        assert all((service.output_dir / name).is_file() for name in batch)
        assert len(seen) == 7
        adapter.fingerprint = lambda _: 'changed'
        with pytest.raises(ValueError, match='Game files changed'):
            service.extract('caption-a', 34)
    finally:
        service.close()


def test_multichannel_original_uses_authored_mix_and_rejects_incompatible_channels(tmp_path, monkeypatch):
    data = tmp_path / 'cache'; data.mkdir()
    decoder = tmp_path / 'decoder'; decoder.touch()
    audio = {'decoder_format': 'mul', 'channel_mix': [[1, 0], [0, 1]], 'start_ms': 100, 'end_ms': 900}
    (data / 'textmap.json').write_text(json.dumps({'install': str(tmp_path), 'fingerprint': 'verified',
        'records': [{'text_id': 'rise:synthetic', 'audio': audio}]}), encoding='utf-8')
    original = (44100).to_bytes(4, 'little') + bytes(8192)
    adapter = SimpleNamespace(fingerprint=lambda _: 'verified', extract_voice=lambda *_: original)
    monkeypatch.setattr(module, 'asset_adapter', lambda _: (adapter, ''))
    monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'encoder')
    encoded = []
    def run(args, **_):
        if str(args[0]) == str(decoder):
            inputs = [Path(args[-1])] if '-o' in args else [Path(path) for path in args[2:]]
            for source in inputs:
                assert source.suffix == '.mul' and source.read_bytes() == original
                destination = args[args.index('-o') + 1] if '-o' in args else str(source) + '.wav'
                with wave.open(destination, 'wb') as stream:
                    stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(8000)
                    stream.writeframes(bytes(32000))
        else:
            assert args[args.index('-af') + 1] == 'pan=stereo|c0=1*c0+0*c1|c1=0*c0+1*c1,volume=0.000000dB'
            encoded.append(args)
            Path(args[-1]).write_bytes(bytes(200))
    monkeypatch.setattr(module.subprocess, 'run', run)
    decoded = []
    def decode(payload, _audio, destination, executable, scratch):
        assert payload == original and executable == decoder and scratch.is_dir()
        decoded.append(destination)
        with wave.open(str(destination), 'wb') as stream:
            stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(8000)
            stream.writeframes(bytes(32000))
    adapter.decode_voice_source = decode
    service = module.LocalVoiceAssetService('riseofthetombraider', data, decoder, tmp_path / 'clips')
    try:
        service.extract('rise:synthetic', 1)
        service.extract_batch([('rise:synthetic', 2, '')])
        assert len(encoded) == 2
        assert len(decoded) == 2, 'Both single and batch paths use the adapter decode hook'
        for invalid in ([[1, 1]], [[1, 0], [0, float('nan')]], [[1, 0], [0, 17]], [[True, 0], [0, 1]]):
            service._entries['rise:synthetic']['channel_mix'] = invalid
            with pytest.raises(ValueError, match='channel mix'):
                service.extract('rise:synthetic', 3)
            with pytest.raises(ValueError, match='channel mix'):
                service.extract_batch([('rise:synthetic', 4, '')])
        assert len(encoded) == 2
        with pytest.raises(ValueError, match='MUL'):
            module._source_suffix(b'not a MUL', audio, 'riseofthetombraider')
        with pytest.raises(ValueError, match='MUL'):
            module._source_suffix(original, audio, 'shadowofthetombraider')
    finally:
        service.close()


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


@pytest.mark.parametrize('game', ['beyond', 'heavyrain'])
def test_quantic_original_wav_is_trimmed_without_external_wem_decoder(tmp_path, monkeypatch, game):
    data = tmp_path / 'cache'; data.mkdir()
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(44100)
        stream.writeframes(bytes(44100 * 2))
    identity = f'{game}:synthetic'
    (data / 'textmap.json').write_text(json.dumps({'install': str(tmp_path), 'fingerprint': 'verified',
        'source_locale': 'nl', 'records': [{'text_id': identity, 'audio': {'start_ms': 100, 'end_ms': 900}}]}))
    adapter = SimpleNamespace(fingerprint=lambda _: 'verified', extract_voice=lambda *_: buffer.getvalue())
    monkeypatch.setattr(module, 'asset_adapter', lambda _: (adapter, ''))
    monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'encoder')
    commands = []
    def encode(args, **_):
        assert args[0] == 'encoder', 'The game reader already decoded the original to WAV'
        assert args[args.index('-ss') + 1] == '0.1'
        assert args[args.index('-t') + 1] == '0.8'
        commands.append(args)
        from pathlib import Path
        Path(args[-1]).write_bytes(bytes(200))
    monkeypatch.setattr(module.subprocess, 'run', encode)
    service = module.LocalVoiceAssetService(game, data, tmp_path / 'absent-decoder', tmp_path / 'clips')
    try:
        assert service.ready and service.has_variant(identity)
        assert (service.output_dir / service.extract(identity, 1)).is_file()
        assert len(commands) == 1
    finally:
        service.close()
