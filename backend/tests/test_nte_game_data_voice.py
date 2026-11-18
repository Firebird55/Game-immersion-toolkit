"""Original binding/codec-closure controls with inert authored fixtures."""
import hashlib
import json
from pathlib import Path
import subprocess
import threading
from types import MappingProxyType, SimpleNamespace
import wave

import pytest

from backend import nte_game_data_voice as voice, nte_game_data_audio_snapshot as snapshot
from backend import nte_game_data_snapshot as text
from backend.game_data_protocol import GameDataRequest, GameDataError
from backend.game_tools import _atomic_file
from backend.tests.test_native_codecs import fixture as codec_fixture, seal


def fixture(tmp_path, monkeypatch):
    layout, root, value = codec_fixture(tmp_path, monkeypatch)
    (root/'vgmstream-cli.exe').write_bytes((root/'ffmpeg.exe').read_bytes())
    (root/'owned-library.dll').write_bytes(b'Authored inert library-closure fixture')
    value['tools']['vgmstream'] = 'vgmstream-cli.exe'; layout = seal(layout, root, value)
    folder = layout.cache_root/'complete-source'; folder.mkdir(parents=True)
    request = GameDataRequest('global', 'en', (), 'text-audio')
    ctx = SimpleNamespace(directory=folder, request=request, check=lambda: None, transfer_lock=threading.RLock())
    member = 'HT/Content/WwiseAudio/Media/English/123.wem'
    row = {'text_id': 'nte:story:owned', 'source_locale': 'en', 'source_text': 'Authored original line.',
        'texts': {'en': 'Authored original line.'}, 'english': 'Authored original line.', 'chinese': '',
        'audio_locale': 'en', 'voice_status': 'voiced', 'dialogue_kind': 'conversation',
        'audio': {'depot': member, 'event': 'Play_Vo_owned', 'locale': 'en', 'gain_db': -3.0}}
    payload = {'format': 2, 'game': 'nte', 'install': None, 'source_mode': 'publisher', 'source_region': 'global',
        'content_mode': 'text-audio', 'source_locale': 'en', 'targets_requested': [],
        'missing_translation_locales': [], 'records': [row]}
    inputs = {key: 'a'*64 for key in text.INPUTS-{'reader', 'initial_descriptions'}}
    inputs.update(reader={'kind': 'nte-owned-model-reader-v1', 'source_sha256': 'b'*64, 'dependencies_sha256': 'c'*64},
        initial_descriptions=dict.fromkeys(('archive', 'localization', 'seed'), 'd'*64))
    raw = b'RIFF'+(24).to_bytes(4, 'little')+b'WAVE'+bytes(20)
    digest = hashlib.sha256(raw).hexdigest(); original = layout.cache_root/(digest+'.wem'); original.write_bytes(raw)
    originals = {'schema': snapshot.SCHEMA, 'request': request.json(), 'recipe_sha256': inputs['recipe_sha256'],
        'files': {member: {'sha256': digest, 'bytes': len(raw), 'member_sha256': 'e'*64}},
        'bindings': [voice.binding(row)], 'codecs': voice.codecs(layout)[1]}
    source = snapshot.publish(payload, inputs, originals, {digest: original}, ctx, layout, _atomic_file)
    return source, row, layout, root, ctx


def test_has_accepts_only_original_binding_and_core_scope_normalization_without_running_codecs(tmp_path, monkeypatch):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(voice, 'codecs', lambda *_: pytest.fail('has queried a decoder'))
    assert source.voice_source.has(row)
    assert source.voice_source.has(MappingProxyType({**row, 'audio_scope': 'line'}))
    for wrong in ({**row, 'player_voice': 'male'}, {**row, 'audio_locale': 'ja'},
            {**row, 'audio_scope': 'context'}, {**row, 'text_id': 'nte:other:owned'},
            {**row, 'audio': {**row['audio'], 'gain_db': 0}}, {**row, 'voice_status': 'unknown'}):
        assert not source.voice_source.has(wrong)
    assert not source.voice_source.has({**row, 'audio': None})


@pytest.mark.parametrize('damage', ['file', 'receipt', 'profile', 'originals', 'codec', 'extra-dll', 'member-owner'])
def test_audio_restore_rejects_tampering_and_swapped_local_contracts(tmp_path, monkeypatch, damage):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch)
    if damage == 'file':
        path = next((ctx.directory/'originals').glob('*.wem')); raw = path.read_bytes(); path.write_bytes(raw[:-1]+b'!')
    elif damage == 'codec': (root/'owned-library.dll').write_bytes(b'changed closure')
    elif damage == 'extra-dll': (root/'unowned.dll').write_bytes(b'foreign')
    elif damage == 'member-owner':
        handle = dict(source.restore_handle); handle['recipe'] = 'f'*64
        with pytest.raises(GameDataError): snapshot.restore(handle, ctx, layout)
        return
    else:
        path = ctx.directory/({'receipt': 'nte-source-receipt.json', 'profile': 'nte-source-profile.json', 'originals': 'nte-audio-originals.json'}[damage])
        path.write_bytes(path.read_bytes()+b'!')
    with pytest.raises(GameDataError): snapshot.restore(source.restore_handle, ctx, layout)


def test_resolve_uses_only_closed_codecs_and_authored_gain_and_keeps_previous_output_on_cancellation(tmp_path, monkeypatch):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch); commands = []
    class Child:
        returncode = 0
        def __init__(self, command, **kwargs):
            commands.append(command)
            assert kwargs['env']['PATH'] == str(root) and kwargs['cwd'].is_relative_to(layout.data_root)
            if Path(command[0]).name == 'vgmstream-cli.exe':
                with wave.open(command[command.index('-o')+1], 'wb') as stream:
                    stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000); stream.writeframes(bytes(32000))
            else: Path(command[-1]).write_bytes(b'ID3'+bytes(200))
        def communicate(self, **_): return None
        def poll(self): return 0
    monkeypatch.setattr(voice.subprocess, 'Popen', Child)
    output = layout.data_root/'audio/owned.mp3'
    assert source.voice_source.resolve(row, output, cancelled=lambda: False) == output
    assert len(commands) == 2 and commands[0][0] == str(root/'vgmstream-cli.exe')
    assert commands[1][0] == str(root/'ffmpeg.exe') and 'volume=-3.000000dB' in commands[1]
    saved = output.read_bytes(); commands.clear()
    assert source.voice_source.resolve(row, output, cancelled=lambda: True) is None
    assert not commands and output.read_bytes() == saved


def test_codec_or_original_mutation_during_decode_cannot_replace_an_existing_clip(tmp_path, monkeypatch):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch)
    class Child:
        returncode = 0
        def __init__(self, command, **_):
            if Path(command[0]).name == 'vgmstream-cli.exe':
                with wave.open(command[command.index('-o')+1], 'wb') as stream:
                    stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000); stream.writeframes(bytes(32000))
            else:
                Path(command[-1]).write_bytes(b'ID3'+bytes(200))
                (root/'owned-library.dll').write_bytes(b'changed after processing')
        def communicate(self, **_): return None
        def poll(self): return 0
    monkeypatch.setattr(voice.subprocess, 'Popen', Child)
    output = layout.data_root/'existing.mp3'; output.parent.mkdir(exist_ok=True); output.write_bytes(b'previous clip')
    with pytest.raises(GameDataError): source.voice_source.resolve(row, output, cancelled=lambda: False)
    assert output.read_bytes() == b'previous clip'


def test_missing_runtime_is_typed_and_locale_contract_matches_the_existing_reader(tmp_path, monkeypatch):
    from backend.nte_assets import VOICE_LOCALES
    assert voice.DUBS == VOICE_LOCALES
    with pytest.raises(GameDataError) as failure: voice.codecs(SimpleNamespace(mode='source'))
    assert failure.value.code == 'nte_audio_runtime_unavailable'


def test_cancellation_stops_the_running_child_and_keeps_existing_output(tmp_path, monkeypatch):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch); state = {'cancelled': False, 'killed': False}
    class Child:
        returncode = None
        def __init__(self, *_a, **_k): pass
        def communicate(self, **_):
            state['cancelled'] = True
            raise subprocess.TimeoutExpired('authored-codec', .1)
        def poll(self): return self.returncode
        def kill(self): state['killed'] = True; self.returncode = 1
        def wait(self, **_): return 1
    monkeypatch.setattr(voice.subprocess, 'Popen', Child)
    output = layout.data_root/'existing.mp3'; output.parent.mkdir(exist_ok=True); output.write_bytes(b'previous clip')
    assert source.voice_source.resolve(row, output, cancelled=lambda: state['cancelled']) is None
    assert state['killed'] and output.read_bytes() == b'previous clip'


def test_codec_change_after_first_child_rejects_before_starting_the_second_child(tmp_path, monkeypatch):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch); commands = []
    class Child:
        returncode = 0
        def __init__(self, command, **_):
            commands.append(command)
            assert Path(command[0]).name == 'vgmstream-cli.exe'
            with wave.open(command[command.index('-o')+1], 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000); stream.writeframes(bytes(32000))
        def communicate(self, **_): (root/'owned-library.dll').write_bytes(b'changed before second child')
        def poll(self): return 0
    monkeypatch.setattr(voice.subprocess, 'Popen', Child)
    output = layout.data_root/'existing.mp3'; output.parent.mkdir(exist_ok=True); output.write_bytes(b'previous clip')
    with pytest.raises(GameDataError): source.voice_source.resolve(row, output, cancelled=lambda: False)
    assert len(commands) == 1 and output.read_bytes() == b'previous clip'


def test_provider_restores_audio_from_explicit_codec_layout_without_reopening_native_reader_or_keys(tmp_path, monkeypatch):
    source, row, layout, root, ctx = fixture(tmp_path, monkeypatch)
    from backend.nte_game_data import NteGameDataProvider
    from backend.nte_game_data_runtime import WindowsNteRuntime
    provider = NteGameDataProvider(platform='windows', native=WindowsNteRuntime(object(), audio_layout=layout))
    monkeypatch.setattr(provider, '_reader', lambda *_: pytest.fail('Historical audio restore opened the native reader'))
    import sys
    for name in ('nte_native_provider', 'nte_native_metadata', 'nte_publisher', 'nte_archive_metadata'):
        monkeypatch.setitem(sys.modules, 'backend.'+name, None)
    restored = provider.restore(source.restore_handle, ctx)
    assert restored.voice_source.has(row) and restored.source_proof == source.source_proof
