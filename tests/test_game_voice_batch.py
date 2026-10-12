"""Synthetic audio verifies real encoding, variants and authored movie cuts."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from types import SimpleNamespace
import wave

import pytest

from backend import local_voice, cyberpunk_assets, wuthering_assets
from backend.media_tools import ffmpeg_executable
from backend.pragmata_audio import PragmataAudioEntry, mix_voice_layers, mix_voice_batches


def wav(path, frequency=200, seconds=2):
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b''.join(struct.pack('<h', round(5000 * math.sin(2*math.pi*frequency*n/16000)))
                                    for n in range(round(seconds*16000))))


@pytest.mark.parametrize('game', ['cyberpunk', 'witcher3', 'wuwa', 'nte', 'honkai3'])
def test_all_local_games_batch_original_variants_and_cinematic_cuts_without_changing_mp3(tmp_path, monkeypatch, game):
    encoder = ffmpeg_executable()
    if not encoder:
        pytest.skip('Native MP3 encoder unavailable')
    cache = tmp_path / 'cache'; cache.mkdir()
    decoder = tmp_path / 'decoder'; decoder.touch()
    records = [{'text_id': 'one', 'audio': {'depot': 'tone-one'}},
               {'text_id': 'two', 'audio': {'depot': 'tone-two'}},
               {'text_id': 'cut-one', 'audio': {'depot': 'movie', 'start_ms': 200, 'end_ms': 800, 'gain_db': -6}},
               {'text_id': 'cut-two', 'audio': {'depot': 'movie', 'start_ms': 800, 'end_ms': 1700, 'gain_db': -3}}]
    (cache/'textmap.json').write_text(json.dumps({'install': str(tmp_path), 'fingerprint': 'fixture', 'records': records}))
    def extract(install, audio, executable, directory):
        return b'RIFF' + audio['depot'].encode()
    bulk_calls = []
    def bulk(install, audios, executable, directory):
        bulk_calls.append(len(audios))
        return [extract(install, audio, executable, directory) for audio in audios]
    adapter = SimpleNamespace(fingerprint=lambda _: 'fixture', extract_voice=extract, extract_voices=bulk)
    monkeypatch.setattr(local_voice, 'asset_adapter', lambda _: (adapter, 'fixture'))
    original_run = local_voice.subprocess.run
    decoder_calls = []
    def run(args, **options):
        if str(args[0]) != str(decoder):
            return original_run(args, **options)
        if '-o' in args:
            pairs = [(Path(args[-1]), Path(args[args.index('-o')+1]))]
        else:
            pairs = [(Path(p), Path(str(p)+'.wav')) for p in args[2:]]
        decoder_calls.append(len(pairs))
        for source, destination in pairs:
            wav(destination, 200 + sum(source.read_bytes()) % 300)
    monkeypatch.setattr(local_voice.subprocess, 'run', run)
    service = local_voice.LocalVoiceAssetService(game, cache, decoder, tmp_path/'scalar')
    try:
        requests = [(r['text_id'], n, None) for n, r in enumerate(records)]
        expected = [hashlib.sha256((service.output_dir / service.extract(*request)).read_bytes()).hexdigest() for request in requests]
        decoder_calls.clear(); service.output_dir = tmp_path/'batch'
        paths = service.extract_batch(requests)
        assert [hashlib.sha256((service.output_dir / name).read_bytes()).hexdigest() for name in paths] == expected
        assert bulk_calls == [3] and decoder_calls == [3]  # Two cuts share one original movie.
        assert expected[0] != expected[1] and expected[2] != expected[3]
        service._entries['cut-two']['end_ms'] = 9999
        service.output_dir = tmp_path/'invalid'
        with pytest.raises(ValueError, match='outside'):
            service.extract_batch(requests)
        assert not list(service.output_dir.glob('*.mp3'))
    finally:
        service.close()


def test_pragmata_batch_preserves_layer_delays_gain_sentence_duration_and_movie_cut(tmp_path):
    if not ffmpeg_executable():
        pytest.skip('Native MP3 encoder unavailable')
    waves = {1: tmp_path/'first.wav', 2: tmp_path/'second.wav'}
    wav(waves[1], 250, 1); wav(waves[2], 450, 2)
    layers = ({'media_id': 1, 'delay_seconds': .2}, {'media_id': 2, 'gain_db': -20})
    entries = [PragmataAudioEntry('sentence', 1, '', '', '', 'sound_id_layers', layers=layers, duration_media_ids=(1,)),
               PragmataAudioEntry('movie', 1, '', '', '', 'cinema', start_seconds=.3, end_seconds=.9, layers=layers)]
    expected = []
    for n, entry in enumerate(entries):
        path = tmp_path/f'scalar{n}.mp3'; mix_voice_layers(entry, waves, path); expected.append(path.read_bytes())
    requests = [(entry, waves, tmp_path/f'batch{n}.mp3') for n, entry in enumerate(entries)]
    mix_voice_batches(requests)
    assert [path.read_bytes() for entry, waves, path in requests] == expected


def test_cyberpunk_bulk_extract_separates_dlc_and_base_archives_and_exact_resources(tmp_path, monkeypatch):
    audios = []
    for group, name, depots in [('content', 'lang_zh-cn_voice.archive', ['one.wem', 'two.wem']),
                               ('ep1', 'ep1_lang_zh-cn_voice.archive', ['one.wem'])]:
        path = tmp_path / 'archive/pc' / group / name; path.parent.mkdir(parents=True); path.touch()
        audios += [{'archive': path.relative_to(tmp_path).as_posix(), 'depot': depot} for depot in depots]
    calls = []
    def unpack(executable, *args):
        archive = Path(args[1]); directory = Path(args[args.index('-o')+1]); pattern = args[args.index('-r')+1]
        calls.append(archive)
        assert not re.match(pattern, 'not-requested.wem')
        for depot in ['one.wem', 'two.wem']:
            if re.match(pattern, depot):
                (directory/depot).write_bytes(archive.parent.name.encode() + depot.encode())
    monkeypatch.setattr(cyberpunk_assets, 'run_wolvenkit', unpack)
    result = cyberpunk_assets.extract_voices(tmp_path, audios, Path('fixture'), tmp_path/'out')
    assert result == [b'contentone.wem', b'contenttwo.wem', b'ep1one.wem'] and len(calls) == 2
    with pytest.raises(ValueError):
        cyberpunk_assets.extract_voices(tmp_path, [{**audios[0], 'depot': '../one.wem'}], Path(), tmp_path/'out')


@pytest.mark.parametrize('broad', [False, True])
def test_wuthering_shared_prefix_is_used_only_when_installed_inventory_bounds_it(tmp_path, monkeypatch, broad):
    root = wuthering_assets.EXTERNAL_ROOT
    depots = [root+'zh_scene_001.wem', root+'zh_scene_002.wem']
    inventory = depots + ([root+f'zh_scene_00extra_{n:03d}.wem' for n in range(3, 30)] if broad else [])
    executable = tmp_path/'tools/reader'
    cache = tmp_path/'index-cache/fixture/complete.json'; cache.parent.mkdir(parents=True); cache.write_text(json.dumps(inventory))
    monkeypatch.setattr(wuthering_assets, 'fingerprint', lambda _: 'fixture')
    calls = []
    def unpack(install, exe, directory, prefix):
        calls.append(prefix)
        for depot in inventory:
            if prefix in depot:
                path = directory/depot; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(depot.encode())
    monkeypatch.setattr(wuthering_assets, 'run_extractor', unpack)
    result = wuthering_assets.extract_voices(tmp_path, [{'depot': p} for p in depots], executable, tmp_path/'out')
    assert result == [p.encode() for p in depots]
    assert len(calls) == (2 if broad else 1)
