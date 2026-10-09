import io
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.local_game import LocalGameTextIndex
from backend.witcher_assets import _bit6, extract_voice, index_install, primary_text, read_speech, read_strings


def bit6(value):
    if value == 0:
        return b"\x80"
    result = bytearray()
    result.append((value & 63) | (64 if value >> 6 else 0))
    value >>= 6
    while value:
        byte = value & 127
        value >>= 7
        result.append(byte | (128 if value else 0))
    return bytes(result)


def strings_file(path, rows, version=164, english=False):
    marker, magic = (0x43975139, 0x79321793) if english else (0, 0)
    unit = 1 if version == 164 else 2
    entries, text_buffer = bytearray(), bytearray()
    for identity, text in rows:
        encoded = text.encode("utf-8" if unit == 1 else "utf-16-le")
        length, offset = len(encoded) // unit, len(text_buffer) // unit
        values = list(encoded) if unit == 1 else list(struct.unpack(f"<{length}H", encoded))
        rolling = (magic >> 8) & 65535
        for index in range(length):
            values[index] ^= ((length + 1) * rolling) & (255 if unit == 1 else 65535)
            rolling = ((rolling << 1) | (rolling >> 15)) & 65535
        entries += struct.pack("<III", identity ^ magic, offset, length)
        text_buffer += bytes(values) if unit == 1 else struct.pack(f"<{length}H", *values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RTSW" + struct.pack("<IH", version, marker >> 16) + bit6(len(rows)) + entries
                     + bit6(0) + bit6(len(text_buffer) // unit) + text_buffer + struct.pack("<H", marker & 65535))


def wave():
    payload = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 48000, 96000, 2, 16) + b"data" + struct.pack("<I", 4) + b"\0\1\0\1"
    return b"RIFF" + struct.pack("<I", len(payload) + 4) + b"WAVE" + payload


def speech_file(path, identities):
    payload = wave()
    header = b"CPSW" + struct.pack("<IH", 164, 0) + bit6(len(identities))
    start = len(header) + len(identities) * 40 + 2
    table, body = bytearray(), bytearray()
    for identity in identities:
        table += struct.pack("<10I", identity, 0, start + len(body), 0, len(payload) + 12, 0, 0, 0, 0, 0)
        body += struct.pack("<I", len(payload)) + payload + b"\0" * 8
    path.write_bytes(header + table + b"\0\0" + body)


@pytest.mark.parametrize("version", [162, 163, 164])
@pytest.mark.parametrize("english", [True, False])
def test_native_localization_reader_retains_ids_and_unicode(tmp_path, version, english):
    path = tmp_path / "localized.w3strings"
    rows = [(2032140290, "Hello, Geralt!" if english else "你好，杰洛特！"), (7, "Two wrapped lines" if english else "两行对白")]
    strings_file(path, rows, version, english)
    assert read_strings(path) == dict(rows)


@pytest.mark.parametrize("count", [0, 1, 63, 64, 127, 4095, 8192, 96915])
def test_bit6_reads_realistic_table_counts(count):
    assert _bit6(io.BytesIO(bit6(count))) == count


def test_modded_and_stock_pairs_resolve_to_the_same_original_speech(tmp_path):
    content = tmp_path / "game/content/content0"
    content.mkdir(parents=True)
    english, chinese = "Stay close, Geralt!", "跟紧我，杰洛特！"
    strings_file(content / "en.w3strings", [(77, english)], english=True)
    strings_file(content / "cn.w3strings", [(77, chinese)])
    speech_file(content / "cnpc.w3speech", [77])
    stock = index_install(tmp_path / "game", tmp_path / "cache")
    strings_file(content / "en.w3strings", [(77, english + "<br>~ " + chinese)], english=True)
    strings_file(content / "cn.w3strings", [(77, chinese + " ~ " + english)])
    dual = index_install(tmp_path / "game", tmp_path / "cache")
    assert stock["records"] == dual["records"]
    (tmp_path / "textmap.json").write_text(json.dumps(dual), encoding="utf-8")
    index = LocalGameTextIndex("witcher3", tmp_path)
    for rows in ([english], [chinese], [english + " ~ " + chinese], [chinese, "~ " + english]):
        assert index.match_lines(rows).text_id == "witcher3:77"
    assert extract_voice(tmp_path / "game", dual["records"][0]["audio"], Path("unused"), tmp_path) == wave()


def test_speech_offsets_above_four_gib_are_not_truncated():
    offset = (1 << 32) + 200
    data = wave()
    table = b"CPSW" + struct.pack("<IH", 164, 0) + bit6(1) + struct.pack("<10I", 7, 0, 200, 1, len(data) + 12, 0, 0, 0, 0, 0) + b"\0\0"
    class VirtualFile:
        position = 0
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def seek(self, position): self.position = position
        def read(self, size):
            source, base = (data, offset + 4) if self.position >= offset else (table, 0)
            result = source[self.position - base:self.position - base + size]
            self.position += len(result)
            return result
    path = SimpleNamespace(open=lambda _: VirtualFile(), stat=lambda: SimpleNamespace(st_size=offset + 1000))
    assert read_speech(path)[7]["offset"] == offset + 4


def test_installed_dlc_is_included_but_separate_mod_content_is_not(tmp_path):
    for folder, identity in (("content/content0", 77), ("dlc/expansion/content", 88), ("mods/unverified/content", 99)):
        content = tmp_path / folder
        strings_file(content / "en.w3strings", [(identity, f"Follow Geralt {identity}")], english=True)
        strings_file(content / "cn.w3strings", [(identity, f"跟着杰洛特{identity}")])
        speech_file(content / "cnpc.w3speech", [identity])
    records = index_install(tmp_path, tmp_path / "cache")["records"]
    assert {record["text_id"] for record in records} == {"witcher3:77", "witcher3:88"}
    assert all(record["audio"] for record in records)


def test_older_mod_header_with_utf8_buffer_is_detected(tmp_path):
    path = tmp_path / "cn.w3strings"
    strings_file(path, [(77, "你好<br>~ Hello")])
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, 4, 163)
    path.write_bytes(data)
    assert read_strings(path) == {77: "你好<br>~ Hello"}


def test_repeated_original_performances_and_missing_mandarin_are_excluded(tmp_path):
    content = tmp_path / "content/content0"
    content.mkdir(parents=True)
    strings_file(content / "en.w3strings", [(77, "Stay close!")], english=True)
    strings_file(content / "cn.w3strings", [(77, "跟紧我！")])
    speech_file(content / "cnpc.w3speech", [77, 77])
    assert index_install(tmp_path, tmp_path / "cache")["records"][0]["audio"] is None
    (content / "cnpc.w3speech").unlink()
    payload = index_install(tmp_path, tmp_path / "cache")
    assert payload["records"][0]["audio"] is None
    assert "Chinese speech pack" in payload["message"]


def test_corrupt_localization_or_voice_bounds_fail_without_fallback(tmp_path):
    path = tmp_path / "cn.w3strings"
    strings_file(path, [(77, "跟紧我！")])
    path.write_bytes(path.read_bytes()[:-5])
    with pytest.raises(ValueError): read_strings(path)
    with pytest.raises(ValueError):
        extract_voice(tmp_path, {"archive": "../outside/cnpc.w3speech", "offset": 1, "size": 100}, Path("unused"), tmp_path)


def test_only_an_unambiguous_mod_language_component_is_used():
    assert primary_text("Hello ~ 你好", False) == "Hello"
    assert primary_text("你好<br>~ Hello", True) == "你好"
    assert primary_text("Hello ~ Goodbye ~ 你好", False) == ""
    assert primary_text("Hello ~ Goodbye", False) == "Hello ~ Goodbye"
