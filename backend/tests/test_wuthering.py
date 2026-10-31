import sqlite3
import struct
from pathlib import Path

import pytest

from backend.wuthering_assets import EXTERNAL_ROOT, archive_sources, build_records, extract_voice, fingerprint, run_extractor


def plot_blob(text_id, filename, gender=False, global_language=False):
    # Authored PlotAudio schema: ID, setting, filename, global, EN/JA/KO/ZH
    # gender flags, lip-sync, tail time, parameters. No heuristic blob searches.
    values = [text_id, "subtitle_normal", filename, global_language, False, False, False, gender, False, False, ""]
    table = 32
    blob = bytearray(table + 48)
    struct.pack_into("<I", blob, 0, table)
    struct.pack_into("<HH", blob, 4, 26, 48)
    struct.pack_into("<i", blob, table, table - 4)
    for slot, value in enumerate(values):
        position = table + 4 + slot * 4
        if isinstance(value, str) and value:
            struct.pack_into("<H", blob, 8 + slot * 2, 4 + slot * 4)
            struct.pack_into("<I", blob, position, len(blob) - position)
            encoded = value.encode()
            blob.extend(struct.pack("<I", len(encoded)) + encoded + b"\0")
            blob.extend(b"\0" * (-len(blob) % 4))
        elif value:
            struct.pack_into("<H", blob, 8 + slot * 2, 4 + slot * 4)
            blob[position] = 1
    return bytes(blob)


def database(root, rows):
    for language in ("en", "zh-Hans"):
        path = root / language / "lang_multi_text.db"
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE MultiText (Id TEXT, Content TEXT)")
            connection.executemany("INSERT INTO MultiText VALUES (?, ?)", [(key, en if language == "en" else zh) for key, en, zh, blob in rows])
    with sqlite3.connect(root / "db_plot_audio.db") as connection:
        connection.execute("CREATE TABLE plotaudio (Id TEXT, BinData BLOB)")
        connection.executemany("INSERT INTO plotaudio VALUES (?, ?)", [(key, blob) for key, en, zh, blob in rows])


def test_original_mandarin_identity_uses_authored_filename_and_gender(tmp_path):
    database(tmp_path, [("scene1", "Stay close!", "跟紧我！", plot_blob("scene1", "vo_scene1", gender=True))])
    files = [EXTERNAL_ROOT + "zh_vo_scene1_F.wem", EXTERNAL_ROOT + "zh_vo_scene1_M.wem"]
    records = build_records(tmp_path, files)
    assert [(r["text_id"], r["player_voice"], r["audio"]["depot"]) for r in records] == [
        ("wuwa:scene1:female", "female", files[0]), ("wuwa:scene1:male", "male", files[1])]


def test_missing_pack_shared_and_similar_filenames_are_not_mandarin_fallbacks(tmp_path):
    database(tmp_path, [
        ("scene1", "Stay close!", "跟紧我！", plot_blob("scene1", "vo_scene1")),
        ("shared", "A roar", "吼声", plot_blob("shared", "vo_shared", global_language=True)),
        ("dynamic", "Hello there", "你好啊", plot_blob("dynamic", "vo_{VarParams}")),
    ])
    records = build_records(tmp_path, [EXTERNAL_ROOT + "en_vo_scene1.wem", EXTERNAL_ROOT + "zh_vo_scene12.wem",
                                    EXTERNAL_ROOT + "gl_vo_shared.wem", EXTERNAL_ROOT + "zh_vo_shared.wem"])
    assert len(records) == 3
    assert not any(record["audio"] for record in records)


def test_text_must_join_to_the_same_authored_plot_audio_id(tmp_path):
    database(tmp_path, [("scene1", "Stay close!", "跟紧我！", plot_blob("different", "vo_scene1"))])
    assert build_records(tmp_path, [EXTERNAL_ROOT + "zh_vo_scene1.wem"]) == []


def test_installed_language_pack_changes_fingerprint_and_mods_are_excluded(tmp_path):
    directory = tmp_path / "Client/Content/Paks"
    directory.mkdir(parents=True)
    (directory / "pakchunk0.pak").write_bytes(b"base")
    old = fingerprint(tmp_path)
    language = tmp_path / "Client/Saved/Resources/3.0.0/Lang_zh/Base"
    language.mkdir(parents=True)
    (language / "pakchunk13.pak").write_bytes(b"Mandarin")
    assert fingerprint(tmp_path) != old
    current = fingerprint(tmp_path)
    mods = directory / "~mods"
    mods.mkdir()
    (mods / "pakchunk99.pak").write_bytes(b"unrelated mod")
    assert fingerprint(tmp_path) == current


def test_extractor_errors_never_include_archive_metadata(tmp_path, monkeypatch):
    import backend.wuthering_assets as module
    import subprocess
    key = '0x' + 'a' * 64
    monkeypatch.setattr(module, "_archive_metadata", lambda *_: (key,))
    monkeypatch.setattr(module, '_reader_command', lambda *_: (['tool'], None, tmp_path))
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["tool", "private-placeholder"])
    monkeypatch.setattr(module.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="could not complete") as error:
        run_extractor(tmp_path / 'game', Path("tool"), None, "WwiseExternalSource/")
    assert "private-placeholder" not in str(error.value)


def test_official_downloaded_video_archives_are_allowed_but_custom_paks_are_rejected(tmp_path, monkeypatch):
    import backend.wuthering_assets as module
    from types import SimpleNamespace
    video = tmp_path / "Client/Saved/Resources/Video/hd/Paks/101_1/Video_101_1-HD-WindowsNoEditor.pak"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"official video fixture")
    monkeypatch.setattr(module, "_archive_metadata", lambda *_: ('0x' + 'a' * 64,))
    def command(_install, _executable, destination, *_):
        (destination / 'files.json').write_text('[]')
        return ['tool'], None, tmp_path
    monkeypatch.setattr(module, '_reader_command', command)
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    assert archive_sources(tmp_path) == [video]
    assert run_extractor(tmp_path, Path("tool"), None, "WwiseExternalSource/") == []
    custom = video.parent / "Video_999_9-HD-WindowsNoEditor.pak"
    custom.write_bytes(b"unknown")
    assert custom not in archive_sources(tmp_path)
    with pytest.raises(ValueError, match="unsupported mod archives"):
        run_extractor(tmp_path, Path("tool"), None, "WwiseExternalSource/")


def test_small_empty_official_patch_does_not_block_valid_language_archives(tmp_path, monkeypatch):
    import json
    from Crypto.Cipher import AES
    import backend.wuthering_assets as module
    directory = tmp_path / "Client/Content/Paks"
    directory.mkdir(parents=True)
    empty = directory / "pakchunk_empty.pak"
    footer = b"\0" * 17 + struct.pack("<IIQQ", 0x5A6F12E1, 12, 0, 0) + b"\0" * 20
    empty.write_bytes(b"\0" * (461 - len(footer)) + footer)
    # An in-memory mock encoding, never a real game's extraction metadata.
    encoding = bytes(32)
    plain = struct.pack("<i", 4) + b"../\0" + b"\0" * 8
    encrypted = AES.new(encoding, AES.MODE_ECB).encrypt(plain)
    language = directory / "pakchunk_language.pak"
    language.write_bytes(encrypted + b"\0" * 16 + b"\1" + struct.pack("<IIQQ", 0x5A6F12E1, 12, 0, 16) + b"\0" * 20)
    candidate = "0x" + encoding.hex()
    monkeypatch.setattr(module, "_download", lambda _: json.dumps([candidate]).encode())
    assert module._archive_metadata(tmp_path, "fixture") == (candidate,)


def test_voice_extraction_only_accepts_an_exact_mandarin_resource(tmp_path, monkeypatch):
    import backend.wuthering_assets as module
    calls = []
    depot = EXTERNAL_ROOT + "zh_vo_scene1.wem"
    def run(install, executable, destination, filter_text):
        calls.append(filter_text)
        target = destination / depot
        target.parent.mkdir(parents=True)
        target.write_bytes(b"original")
    monkeypatch.setattr(module, "run_extractor", run)
    assert extract_voice(tmp_path, {"depot": depot}, Path("tool"), tmp_path / "cache") == b"original"
    assert calls == [depot]
    with pytest.raises(ValueError):
        extract_voice(tmp_path, {"depot": EXTERNAL_ROOT + "en_vo_scene1.wem"}, Path("tool"), tmp_path / "cache")


def test_other_unreal_game_is_not_detected_as_wuthering(tmp_path, monkeypatch):
    from backend.models import AppSettings
    import backend.windows as windows
    monkeypatch.setattr(windows, "list_visible_windows", lambda: [windows.WindowInfo(1, "Unrelated game", "Client-Win64-Shipping.exe", (0, 0, 3840, 2160))])
    monkeypatch.setattr(windows, "executable_path_for_window", lambda _: tmp_path / "unrelated.exe")
    monkeypatch.setattr("backend.game_paths.discover_install", lambda _: tmp_path)
    assert windows.find_active_game_window(AppSettings()) is None
