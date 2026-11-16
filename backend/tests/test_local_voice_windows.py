"""Decoded late windows must survive single/batch playback and offline reload.

The existing authored-cut tests decode whole sources and cannot detect a second
trim or batch reuse of PCM from a different window of the same original.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from backend import local_voice as module


def pcm_file(path, start, end, *, frames=None):
    frames = (end - start) * 48 if frames is None else frames
    # Distinct owned PCM for different windows of the same source.
    pcm = int(start % 30000).to_bytes(2, 'little', signed=True) * frames * 2
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        stream.writeframes(pcm)
    return pcm


def test_single_batch_and_fresh_offline_service_keep_each_original_window(tmp_path, monkeypatch):
    data = tmp_path / 'cache'; data.mkdir()
    binary = tmp_path / 'decoder'; binary.touch()
    rows = [{'text_id': f'owned:{n}', 'audio': {'publisher': 'owned-snapshot', 'depot': 'same-original',
             'start_ms': start, 'end_ms': start + 150}}
            for n, start in enumerate((300025, 300175))]
    payload = {'install': None, 'fingerprint': 'owned-snapshot', 'source_locale': 'en', 'records': rows}
    snapshot = json.dumps(payload)
    (data / 'textmap.json').write_text(snapshot)
    originals = copy.deepcopy(rows)
    decoded = []

    def decode(raw, audio, output, decoder, scratch):
        assert raw == b'RIFF' + bytes(100) and decoder == binary and scratch.is_dir()
        decoded.append((audio['start_ms'], audio['end_ms']))
        pcm_file(output, audio['start_ms'], audio['end_ms'])
        return audio['start_ms']

    adapter = SimpleNamespace(extract_voice=lambda *_: b'RIFF' + bytes(100),
        publisher_snapshot_available=lambda *_: True, decode_voice_source=decode)
    monkeypatch.setattr(module, 'asset_adapter', lambda _: (adapter, ''))
    monkeypatch.setattr(module, 'ffmpeg_executable', lambda: 'encoder')

    def encode(args, **_):
        assert args[0] == 'encoder' and '-ss' not in args and '-t' not in args
        inputs = [Path(args[n + 1]) for n, x in enumerate(args) if x == '-i']
        source_index = 0
        for n, value in enumerate(args):
            if value == '-map':
                source_index = int(args[n + 1].split(':')[0])
            if str(value).endswith('.mp3'):
                with wave.open(str(inputs[source_index])) as stream:
                    assert stream.getnframes() == 150 * 48
                    pcm = stream.readframes(stream.getnframes())
                Path(value).write_bytes(b'owned-encoding' + pcm[:256])
    monkeypatch.setattr(module.subprocess, 'run', encode)
    monkeypatch.setattr('urllib.request.urlopen', lambda *_args, **_kwargs: pytest.fail('Offline playback accessed the network'))

    def open_service(folder):
        service = module.LocalVoiceAssetService('wuwa', data, binary, folder)
        assert service.ready
        return service

    service = open_service(tmp_path / 'clips')
    try:
        single = [service.output_dir / service.extract(row['text_id'], n) for n, row in enumerate(rows)]
        batch = [service.output_dir / name for name in service.extract_batch([(r['text_id'], n + 10, '') for n, r in enumerate(rows)])]
        assert [p.read_bytes() for p in single] == [p.read_bytes() for p in batch]
        assert single[0].read_bytes() != single[1].read_bytes()
        assert decoded == [(300025, 300175), (300175, 300325)] * 2
        assert service._entries == {r['text_id']: r['audio'] for r in originals}
    finally:
        service.close()
    service = open_service(tmp_path / 'fresh-clips')
    try:
        fresh = service.output_dir / service.extract(rows[1]['text_id'], 22)
        assert fresh.read_bytes() == single[1].read_bytes()
    finally:
        service.close()
    assert (data / 'textmap.json').read_text() == snapshot


@pytest.mark.parametrize('origin', [-1, False, 0, 300026, 300025.0, '300025'])
def test_decoder_origin_must_exactly_equal_the_original_integer_start(tmp_path, origin):
    wav = tmp_path / 'owned.wav'; pcm_file(wav, 300025, 300175)
    with pytest.raises(ValueError, match='window'):
        module._audio_options({'start_ms': 300025, 'end_ms': 300175}, wav, decoded_origin_ms=origin)


@pytest.mark.parametrize('start,end,frames', [(300025, 300175, 7199), (300025, 300175, 7201),
                                           (300025, 600026, 7200), (False, 150, 7200),
                                           (300025, None, 7200)])
def test_window_duration_and_pcm_must_agree_before_skipping_the_second_trim(tmp_path, start, end, frames):
    wav = tmp_path / 'owned.wav'; pcm_file(wav, 300025, 300175, frames=frames)
    with pytest.raises(ValueError, match='window'):
        module._audio_options({'start_ms': start, 'end_ms': end}, wav, decoded_origin_ms=300025)
