"""Users rebuild their own installed content; no real game data is checked in."""
import json
from types import SimpleNamespace

import pytest

from backend import cyberpunk_assets as cyberpunk
from backend.local_game import LocalGameTextIndex
from backend.local_game_updates import LocalGameUpdateManager
from backend.tests.test_witcher import strings_file, speech_file


def resource(depot):
    return {"DepotPath": {"$value": depot}}


def cyberpunk_archive(install, group, language, identity, text="Synthetic dialogue."):
    name = ("ep1_" if group == "ep1" else "") + f"lang_{language}.archive"
    path = install / "archive/pc" / group / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if "voice" in language:
        depot = f"{group}/localization/zh-cn/vo/synthetic-{identity}.wem"
        row = {"stringId": identity, "femaleResPath": resource(depot), "maleResPath": resource(depot)}
    else:
        row = {"stringId": identity, "femaleVariant": text, "maleVariant": ""}
    path.write_text(json.dumps({"entries": [row]}), encoding="utf8")
    return path


def mock_cyberpunk_reader(monkeypatch):
    monkeypatch.setattr(cyberpunk, "ensure_wolvenkit", lambda _: "synthetic-reader")
    def run(_exe, command, *args):
        if command == "cr2w":
            return
        archive, destination = args[0], args[2]
        data = json.loads(archive.read_bytes())
        data['$type'] = 'locVoiceoverMap' if 'voice' in archive.name else 'localizationPersistenceSubtitleEntries'
        name = "voiceovermap.json.json" if "voice" in archive.name else "subtitles.json.json"
        target = destination / "nested/resources" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"Data": {"RootChunk": {"root": {"Data": data}}}}))
    monkeypatch.setattr(cyberpunk, "run_wolvenkit", run)


def test_users_can_add_update_and_remove_phantom_liberty_without_toolkit_changes(tmp_path, monkeypatch):
    import backend.local_game_updates as updates
    install, cache = tmp_path / "game", tmp_path / "cache"
    for language, text in [("en_text", "Base synthetic dialogue."), ("zh-cn_text", "基础测试对白。"), ("zh-cn_voice", "")]:
        cyberpunk_archive(install, "content", language, "10", text)
    monkeypatch.setattr(updates, "discover_install", lambda _: install)
    mock_cyberpunk_reader(monkeypatch)
    manager = LocalGameUpdateManager("cyberpunk", LocalGameTextIndex("cyberpunk", cache), SimpleNamespace(reload=lambda: None))
    manager._run()
    assert manager.index.entry_count == 1
    assert cyberpunk.expansion_status(install)["expansion_state"] == "not_installed"
    # DLC text without its own voice pack must never borrow a base-game voice.
    dlc = [cyberpunk_archive(install, "ep1", "en_text", "20", "DLC synthetic dialogue."),
           cyberpunk_archive(install, "ep1", "zh-cn_text", "20", "扩展测试对白。")]
    manager._run()
    assert cyberpunk.expansion_status(install)["expansion_state"] == "missing_voice"
    assert manager.index.match_lines(["DLC synthetic dialogue."], exact_only=True) is None
    dlc.append(cyberpunk_archive(install, "ep1", "zh-cn_voice", "20"))
    manager._run()
    assert cyberpunk.expansion_status(install)["expansion_state"] == "available"
    match = manager.index.match_lines(["DLC synthetic dialogue."], exact_only=True)
    assert match.text_id == "cyberpunk:20:female"
    payload = json.loads(manager.index.path.read_bytes())
    row = next(r for r in payload["records"] if r["text_id"] == match.text_id)
    assert row["audio"]["archive"] == "archive/pc/ep1/ep1_lang_zh-cn_voice.archive"
    assert "1 Phantom Liberty voice mappings" in manager.index.message
    before = payload["fingerprint"]
    cyberpunk_archive(install, "ep1", "en_text", "20", "Updated DLC synthetic dialogue.")
    cyberpunk_archive(install, "ep1", "zh-cn_text", "20", "更新后的扩展测试对白。")
    manager._run()
    assert json.loads(manager.index.path.read_bytes())["fingerprint"] != before
    assert manager.index.match_lines(["Updated DLC synthetic dialogue."], exact_only=True).chinese == "更新后的扩展测试对白。"
    assert manager.index.match_lines(["DLC synthetic dialogue."], exact_only=True) is None
    for path in dlc:
        path.unlink()
    manager._run()
    assert manager.index.entry_count == 1
    assert manager.index.match_lines(["Updated DLC synthetic dialogue."], exact_only=True) is None
    assert manager.index.match_lines(["Base synthetic dialogue."], exact_only=True)


@pytest.mark.parametrize("language", ["en_text", "zh-cn_text"])
def test_partial_dlc_text_download_is_visible_in_setup(tmp_path, language):
    cyberpunk_archive(tmp_path, "ep1", language, "20")
    assert cyberpunk.expansion_status(tmp_path)["expansion_state"] == "missing_text"


def test_incomplete_dlc_with_reused_ids_cannot_mix_base_text_or_voices(tmp_path, monkeypatch):
    mock_cyberpunk_reader(monkeypatch)
    for language, text in [("en_text", "Base synthetic dialogue."), ("zh-cn_text", "基础测试对白。"), ("zh-cn_voice", "")]:
        cyberpunk_archive(tmp_path, "content", language, "10", text)
    cyberpunk_archive(tmp_path, "ep1", "en_text", "10", "New DLC synthetic dialogue.")
    # No corresponding DLC Chinese: do not combine the two content groups.
    with pytest.raises(ValueError, match="No official bilingual"):
        cyberpunk.index_install(tmp_path, tmp_path / "cache")
    cyberpunk_archive(tmp_path, "ep1", "zh-cn_text", "10", "扩展测试对白。")
    payload = cyberpunk.index_install(tmp_path, tmp_path / "cache")
    assert payload["records"][0]["audio"] is None


def test_phantom_liberty_voice_extracts_from_its_exact_dlc_archive(tmp_path, monkeypatch):
    install, output = tmp_path / "game", tmp_path / "output"
    archive = cyberpunk_archive(install, "ep1", "zh-cn_voice", "20")
    depot = "ep1/localization/zh-cn/vo/synthetic-20.wem"
    calls = []
    def run(_exe, *_args):
        calls.append(_args)
        path = output / depot
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic-original-mandarin")
    monkeypatch.setattr(cyberpunk, "run_wolvenkit", run)
    audio = {"archive": archive.relative_to(install).as_posix(), "depot": depot}
    assert cyberpunk.extract_voice(install, audio, tmp_path / "tool", output) == b"synthetic-original-mandarin"
    assert calls[0][1] == archive.resolve()
    with pytest.raises(ValueError):
        cyberpunk.extract_voice(install, {**audio, "depot": "/outside.wem"}, tmp_path / "tool", output)


def test_witcher_patch_rebuilds_installed_base_and_expansion_language_ids(tmp_path, monkeypatch):
    import backend.local_game_updates as updates
    install, cache = tmp_path / "game", tmp_path / "cache"
    for group, identity in [("content/content0", 77), ("dlc/expansion/content", 88)]:
        folder = install / group
        strings_file(folder / "en.w3strings", [(identity, f"Synthetic Witcher dialogue {identity}.")], english=True)
        strings_file(folder / "cn.w3strings", [(identity, f"测试巫师对白{identity}。")])
        speech_file(folder / "cnpc.w3speech", [identity])
    monkeypatch.setattr(updates, "discover_install", lambda _: install)
    manager = LocalGameUpdateManager("witcher3", LocalGameTextIndex("witcher3", cache), SimpleNamespace(reload=lambda: None))
    manager._run()
    assert manager.index.audio_count == 2
    folder = install / "dlc/expansion/content"
    strings_file(folder / "en.w3strings", [(89, "Updated synthetic Witcher DLC dialogue.")], english=True)
    strings_file(folder / "cn.w3strings", [(89, "更新后的巫师扩展测试对白。")])
    speech_file(folder / "cnpc.w3speech", [89])
    manager._run()
    assert manager.index.match_lines(["Updated synthetic Witcher DLC dialogue."], exact_only=True).text_id == "witcher3:89"
    assert manager.index.match_lines(["Synthetic Witcher dialogue 88."], exact_only=True) is None
    assert manager.index.audio_count == 2


def test_pragmata_refresh_uses_a_fresh_extraction_and_rejects_mid_patch_changes(tmp_path, monkeypatch):
    from scripts import index_pragmata_assets as reader
    install, data = tmp_path / "game", tmp_path / "data"
    install.mkdir()
    archive = install / "re_chunk_000.pak"
    archive.write_bytes(b"synthetic-first-patch")
    stale = data / "extracted-next/removed-old-file"
    stale.parent.mkdir(parents=True)
    stale.touch()
    monkeypatch.setattr(reader, "DATA_DIR", data)
    monkeypatch.setattr(reader, "load_sound_graph", lambda: {})
    destinations = []
    def extract(_install, destination, _tools):
        destinations.append(destination)
        assert not (destination / "removed-old-file").exists()
        (destination / "natives/stm/message").mkdir(parents=True)
    monkeypatch.setattr(reader, "extract_assets", extract)
    monkeypatch.setattr(reader, "build_index", lambda *_: {"records": [{"text_id": "synthetic"}], "audio_count": 1})
    first = reader.refresh_install(install)
    assert first["fingerprint"] == reader.fingerprint(install)
    assert not destinations[0].exists()
    def patch_while_reading(*args):
        archive.write_bytes(b"synthetic-game-is-now-patching")
        return {"records": [{"text_id": "synthetic"}]}
    monkeypatch.setattr(reader, "build_index", patch_while_reading)
    with pytest.raises(ValueError, match="files changed while indexing"):
        reader.refresh_install(install)
    monkeypatch.setattr(reader, "build_index", lambda *_: {"records": []})
    with pytest.raises(ValueError, match="previous index preserved"):
        reader.refresh_install(install)


def test_pragmata_failed_refresh_preserves_previous_published_index(tmp_path, monkeypatch):
    from scripts import index_pragmata_assets as reader
    output = tmp_path / "textmap.json"
    output.write_text('{"records":[{"text_id":"old-synthetic"}]}')
    before = output.read_bytes()
    monkeypatch.setattr(reader, "find_install", lambda: tmp_path)
    monkeypatch.setattr(reader.sys, "argv", ["index", "--output", str(output)])
    monkeypatch.setattr(reader, "refresh_install", lambda _: (_ for _ in ()).throw(ValueError("Incomplete patch")))
    with pytest.raises(ValueError, match="Incomplete patch"):
        reader.main()
    assert output.read_bytes() == before
