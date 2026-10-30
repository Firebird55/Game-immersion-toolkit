from __future__ import annotations

import struct
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from backend.pragmata_audio import (
    PragmataAudioEntry,
    build_sound_id_audio_map,
    cutscene_audio_for_bank,
    mix_voice_layers,
    read_bank_play_layers,
    read_pck_media,
    read_tmlfsm_dialogue_segments,
)


def test_sound_id_maps_to_unique_mandarin_media() -> None:
    graph = {
        "source_event_records": [["dialogue", 22]],
        "source_events": {"111": [0], "222": [0]},
        "media_links": {
            "natives/stm/sound/dialogue.sbnk.1.x64.zhcn": {"dialogue.zhcn": [222]},
        },
        "media_packages": {
            "dialogue.zhcn": {"index": "index.pck", "streaming": "streaming.pck"},
        },
        "bank_events": {
            "dialogue": {"22": {"trigger_ids": [98765]}},
        },
    }
    assert build_sound_id_audio_map(graph)[98765] == {
        "bank": "dialogue",
        "media_id": 222,
        "index": "index.pck",
        "streaming": "streaming.pck",
        "mapping": "sound_id",
    }


def test_reads_media_from_wwise_pck(tmp_path: Path) -> None:
    payload = b"RIFF" + b"\x00" * 28
    table = struct.pack("<I5I", 1, 77, 1, len(payload), 64, 0)
    package = bytearray(64 + len(payload))
    package[:28] = b"AKPK" + struct.pack("<6I", 56, 1, 0, 0, len(table), 0)
    package[28 : 28 + len(table)] = table
    package[64:] = payload
    path = tmp_path / "voice.pck"
    path.write_bytes(package)
    assert read_pck_media(path, 77) == payload


def test_reads_guid_interval_from_pragmata_timeline(tmp_path: Path) -> None:
    guid = "12345678-1234-1234-1234-123456789abc"
    clip_offsets, clip_infos, clip = 88, 96, 128
    properties, keys, names, unicode_values, timeline_names = 340, 396, 444, 464, 700
    data = bytearray(760)
    struct.pack_into("<4sIII", data, 0, b"tfs2", 42091004, 0, 1)
    struct.pack_into(
        "<8Q", data, 24,
        clip_offsets, clip_offsets, clip_offsets, clip_infos, 0, 0, 0, timeline_names,
    )
    struct.pack_into("<Q", data, clip_offsets, clip)
    struct.pack_into("<I", data, clip_infos + 24, 0)
    data[timeline_names : timeline_names + len("cs0010_s00".encode("utf-16-le")) + 2] = (
        "cs0010_s00\0".encode("utf-16-le")
    )
    counts = [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 3]
    struct.pack_into("<II f 11I", data, clip, 0x50494C43, 91, 120.0, *counts)
    offsets = [0] * 19
    offsets[6], offsets[10], offsets[15], offsets[16] = properties, keys, names, unicode_values
    struct.pack_into("<19Q", data, clip + 56, *offsets)
    data[names : names + 17] = b"RequestMessageId\0"
    struct.pack_into("<ffIIqqqHhBBBBq", data, properties, 0.0, 120.0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0x30, 0)
    values = [guid, guid, "00000000-0000-0000-0000-000000000000"]
    cursor = unicode_values
    for index, (frame, value) in enumerate(zip((10.0, 70.0, 71.0), values)):
        encoded = (value + "\0").encode("utf-16-le")
        struct.pack_into("<fBBHq", data, keys + index * 16, frame, 0, 0, 0, (cursor - unicode_values) // 2)
        data[cursor : cursor + len(encoded)] = encoded
        cursor += len(encoded)
    path = tmp_path / "scene.tmlfsm2.42091004"
    path.write_bytes(data)
    assert read_tmlfsm_dialogue_segments(path) == [
        {"guid": guid, "start_seconds": 10 / 60, "end_seconds": 70 / 60}
    ]


def fixed_bank(path: Path, child_kind=2, randomized=False) -> None:
    def node(oid, parent, kind, media=0, props=None):
        props = props or {}
        data = struct.pack('<I', oid)
        if kind == 2:
            data += struct.pack('<IBIIB', 262145, 1, media, 4096, 1)
        data += b'\0\0\0\0' + struct.pack('<IIB', 0, parent, 0)
        data += bytes([len(props)]) + bytes(props) + struct.pack(f'<{len(props)}f', *props.values())
        data += b'\x01\x00' + bytes(8) if randomized and oid == 11 else b'\0'
        return kind, data

    objects = [node(10, 0, 9, props={0: -2, 34: .2}),
               node(11, 10, child_kind, 101, {0: -3, 34: .1}),
               node(12, 10, 2, 102),
               (3, struct.pack('<IHI', 20, 0x0403, 10)),
               (4, struct.pack('<IBI', 30, 1, 20))]
    hirc = struct.pack('<I', len(objects)) + b''.join(struct.pack('<BI', k, len(d)) + d for k, d in objects)
    path.write_bytes(b'BKHD' + struct.pack('<II', 4, 150) + b'HIRC' + struct.pack('<I', len(hirc)) + hirc)


def test_fixed_layers_preserve_inherited_volume_and_delay(tmp_path):
    path = tmp_path / 'dialogue.sbnk.1.x64.zhcn'
    fixed_bank(path)
    layers = read_bank_play_layers(path)[30]
    assert [x['media_id'] for x in layers] == [101, 102]
    assert layers[0]['gain_db'] == -5
    assert layers[0]['delay_seconds'] == pytest.approx(.3)
    graph = {
        'source_event_records': [['dialogue', 30]],
        'source_events': {'101': [0], '102': [0, 1]},
        'media_links': {'natives/stm/sound/wwise/dialogue.sbnk.1.x64.zhcn': {'dialogue.zhcn': [101, 102]}},
        'media_packages': {'dialogue.zhcn': {'index': 'index.pck', 'streaming': 'streaming.pck'}},
        'bank_events': {'dialogue': {'30': {'trigger_ids': [99]}}},
    }
    assert 99 not in build_sound_id_audio_map(graph)
    result = build_sound_id_audio_map(graph, tmp_path)[99]
    assert result['mapping'] == 'sound_id_layers'
    assert result['duration_media_ids'] == [101]
    assert cutscene_audio_for_bank(graph, 'dialogue', tmp_path)['layers'] == layers


@pytest.mark.parametrize('kind,randomized', [(5, False), (6, False), (2, True)])
def test_dynamic_or_randomized_child_does_not_render_incomplete_mix(tmp_path, kind, randomized):
    path = tmp_path / 'bank'
    fixed_bank(path, kind, randomized)
    assert read_bank_play_layers(path) == {}


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg unavailable')
def test_mix_uses_sentence_duration_and_authored_delays(tmp_path):
    waves = {}
    for mid, seconds in ((1, 1), (2, 4)):
        path = tmp_path / f'{mid}.wav'
        with wave.open(str(path), 'wb') as f:
            f.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            f.writeframes(struct.pack('<h', 1000) * int(16000 * seconds))
        waves[mid] = path
    entry = PragmataAudioEntry('line', 1, '', '', '', 'sound_id_layers',
        layers=({'media_id': 1, 'delay_seconds': .2}, {'media_id': 2, 'gain_db': -20}),
        duration_media_ids=(1,))
    output = tmp_path / 'mixed.mp3'
    mix_voice_layers(entry, waves, output)
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output), '-f', 's16le', '-ac', '1', '-ar', '16000', '-'])
    assert len(raw) / 32000 == pytest.approx(1.2, abs=.03)
    assert max(struct.unpack(f'<{len(raw)//2}h', raw)) > 500


def test_index_excludes_non_dialogue_and_never_borrows_an_identical_performance(tmp_path, monkeypatch):
    from scripts import index_pragmata_assets as indexer
    path = tmp_path / 'mes_main/conv/test.msg.23'
    path.parent.mkdir(parents=True)
    path.touch()
    bank = tmp_path.parent / 'sound/wwise/dialogue.sbnk.1.x64.zhcn'
    bank.parent.mkdir(parents=True)
    bank.touch()
    def row(name, en='Hello.', zh='你好。', sid=0):
        return dict(name=name, english=en, chinese=zh, sound_id=sid, guid='')
    monkeypatch.setattr(indexer, 'read_msg', lambda _: [
        row('Original_Ch01000', sid=1), row('Alias_Ch01000'),
        row('OtherSpeaker_Ch05000'), row('OtherTranslation_Ch01000', zh='您好。'),
        row('OP_StaffList_1'), row('SoundSupport_1'), row('Rejected_Ch01000', en='#Rejected# Hello.'),
    ])
    monkeypatch.setattr(indexer, 'build_sound_id_audio_map', lambda *_: {1: {'media_id': 123, 'bank': 'dialogue'}})
    payload = indexer.build_index(tmp_path, None, sound_graph={'test': True})
    records = payload['records']
    assert len(records) == 4
    assert records[0]['audio']['media_id'] == 123
    assert all('audio' not in record for record in records[1:])
    assert len(payload['excluded']) == 3
    assert len(payload['unresolved_audio']) == 3


def test_old_alias_index_cannot_play_borrowed_audio_while_refresh_is_pending(tmp_path, monkeypatch):
    import json
    from backend import pragmata_audio
    decoder = tmp_path / 'decoder.exe'
    decoder.touch()
    tools = tmp_path / 'tools'
    tools.mkdir()
    (tools / 'REE.Unpacker.exe').touch()
    monkeypatch.setattr(pragmata_audio, 'ffmpeg_executable', lambda: 'ffmpeg')
    audio = {'media_id': 1, 'bank': 'dialogue', 'mapping': 'sound_id'}
    (tmp_path / 'textmap.json').write_text(json.dumps({
        'format': 4, 'install': str(tmp_path), 'records': [
            {'text_id': 'authored', 'audio': audio},
            {'text_id': 'borrowed', 'audio': {**audio, 'mapping': 'bilingual_alias'}}]}))
    service = pragmata_audio.PragmataVoiceAssetService(tmp_path, decoder, tmp_path / 'audio')
    try:
        assert service.has('pragmata:authored')
        assert not service.has('pragmata:borrowed')
    finally:
        service.close()
