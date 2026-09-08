from __future__ import annotations

import struct
from pathlib import Path

from backend.pragmata_audio import (
    build_sound_id_audio_map,
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
