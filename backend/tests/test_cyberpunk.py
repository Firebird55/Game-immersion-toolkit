import json
from pathlib import Path

from backend.cyberpunk_assets import archive_sources, build_records, extract_voice
from backend.local_game import LocalGameTextIndex


def resource(path):
    return {"DepotPath": {"$value": path}}


def make_index(tmp_path, records):
    (tmp_path / "textmap.json").write_text(json.dumps({"records": records}, ensure_ascii=False), encoding="utf-8")
    return LocalGameTextIndex("cyberpunk", tmp_path)


def test_male_female_text_and_voice_variants_are_joined_by_exact_id(tmp_path):
    en = {"1": {"femaleVariant": "You are safe!", "maleVariant": ""}}
    zh = {"1": {"femaleVariant": "你安全了！", "maleVariant": "你已经安全了！"}}
    vo = {"1": {"archive": "archive/pc/content/lang_zh-cn_voice.archive",
                "femaleResPath": resource(r"base\localization\zh-cn\vo\v_f.wem"),
                "maleResPath": resource(r"base\localization\zh-cn\vo\v_m.wem")}}
    records = build_records(en, zh, vo)
    index = make_index(tmp_path, records)
    assert index.match_lines(["You are safe!"]) is None
    index.player_voice = "male"
    assert index.match_lines(["You are safe!"]).text_id == "cyberpunk:1:male"
    assert index.match_lines(["你已经安全了！"]).text_id == "cyberpunk:1:male"
    assert index.match_lines(["你安全了！"]) is None


def test_dual_language_mod_matches_wrapped_blocks_once_and_ignores_ui(tmp_path):
    records = [{"text_id": "cyberpunk:1:female", "english": "Stay close. I will protect you.",
                "chinese": "跟紧我。我会保护你。", "audio": {"depot": "a.wem"}},
               {"text_id": "cyberpunk:2:female", "english": "Inventory", "chinese": "物品栏", "audio": None}]
    index = make_index(tmp_path, records)
    for lines in (["跟紧我。", "我会保护你。"], ["Stay close.", "I will protect you."],
                  ["杰克 Jackie：", "跟紧我。", "我会保护你。", "Stay close.", "I will protect you."],
                  ["跟紧我。我会保护你。 Stay close. I will protect you."]):
        match = index.match_lines(lines)
        assert match and match.text_id == "cyberpunk:1:female"
        assert match.english == records[0]["english"] and match.chinese == records[0]["chinese"]
    assert index.match_lines(["物品栏", "Inventory"]) is None


def test_repeated_text_with_distinct_voices_is_not_guessed(tmp_path):
    records = [{"text_id": f"cyberpunk:{i}:female", "english": "They're coming!", "chinese": "他们来了！",
                "audio": {"depot": f"{i}.wem"}} for i in range(2)]
    assert make_index(tmp_path, records).match_lines(["They're coming!"]) is None


def test_phantom_liberty_sources_are_optional_and_mods_are_excluded(tmp_path):
    for name in ("archive/pc/content/lang_en_text.archive", "archive/pc/ep1/ep1_lang_en_text.archive",
                 "archive/pc/ep1/ep1_lang_zh-cn_voice.archive", "archive/pc/mod/lang_zh-cn_text.archive"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    names = {p.relative_to(tmp_path).as_posix() for p in archive_sources(tmp_path)}
    assert len(names) == 3
    assert "archive/pc/ep1/ep1_lang_zh-cn_voice.archive" in names


def test_voice_extraction_uses_exact_depot_and_rejects_path_escape(tmp_path, monkeypatch):
    import backend.cyberpunk_assets as module
    import pytest
    install, output = tmp_path / "game", tmp_path / "output"
    install.mkdir(); output.mkdir()
    voice_archive = install / "archive/pc/content/lang_zh-cn_voice.archive"
    voice_archive.parent.mkdir(parents=True)
    voice_archive.touch()
    calls = []
    def run(_exe, *arguments):
        calls.append(arguments)
        (output / "voice.wem").write_bytes(b"original-wem")
    monkeypatch.setattr(module, "run_wolvenkit", run)
    assert extract_voice(install, {"archive": voice_archive.relative_to(install).as_posix(), "depot": "voice.wem"}, Path("tool"), output) == b"original-wem"
    assert "^voice\\.wem$" in calls[0]
    with pytest.raises(ValueError):
        extract_voice(install, {"archive": "../other.archive", "depot": "voice.wem"}, Path("tool"), output)
