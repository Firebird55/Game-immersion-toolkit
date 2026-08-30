from __future__ import annotations

import json

from backend.textmaps import TextMapIndex, normalize_english


def write_map(index: TextMapIndex, name: str, payload: dict[str, str]) -> None:
    index.data_dir.mkdir(parents=True, exist_ok=True)
    index.file_path(name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_index(tmp_path) -> TextMapIndex:
    index = TextMapIndex(tmp_path)
    write_map(
        index,
        "en_base",
        {
            "dialogue_1": "Leave any combat along the way to us.",
            "dialogue_2": "Stay close to me.",
            "dialogue_3": "Understood!",
            "dialogue_old": "An older localization.",
            "Activity_Chat_Test_Name_02": "Ray",
            "Activity_Chat_Test_Name01": "Roland",
            "hud_percent": "20%",
            "Tips_123": "Danger ahead!",
            "ManualQTEDialog_Select": "Select",
            "Chat_999": "Nicole",
            "Avatar_Name_Nicole": "Nicole",
        },
    )
    write_map(
        index,
        "zh_base",
        {
            "dialogue_1": "路上的战斗交给我们。",
            "dialogue_2": "跟紧我。",
            "dialogue_3": "明白！",
            "dialogue_old": "旧翻译。",
            "Activity_Chat_Test_Name_02": "蕾",
            "Activity_Chat_Test_Name01": "罗兰",
            "hud_percent": "20%",
            "Tips_123": "前方危险！",
            "ManualQTEDialog_Select": "选择",
            "Chat_999": "妮可",
            "Avatar_Name_Nicole": "妮可",
        },
    )
    write_map(index, "en_overwrite", {"dialogue_old": "The current localization."})
    write_map(index, "zh_overwrite", {"dialogue_old": "当前翻译。"})
    index.load()
    return index


def test_normalize_english_ignores_punctuation_and_markup() -> None:
    assert normalize_english("<b>Don’t</b> wait — Proxy!") == "dontwaitproxy"


def test_exact_match_uses_shared_id(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_text("Leave any combat along the way to us!")
    assert match is not None
    assert match.kind == "exact"
    assert match.chinese == "路上的战斗交给我们。"
    assert match.score == 100


def test_overwrite_wins_over_base(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_text("The current localization.")
    assert match is not None
    assert match.chinese == "当前翻译。"


def test_fuzzy_match_recovers_small_ocr_error(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_text("Leave any cornbat along the way to us.", threshold=75)
    assert match is not None
    assert match.kind == "fuzzy"
    assert match.text_id == "dialogue_1"


def test_line_matching_can_skip_speaker_name(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_lines(["Anby", "Stay close to me."])
    assert match is not None
    assert match.text_id == "dialogue_2"


def test_short_spoken_line_requires_dialogue_context_or_punctuation(tmp_path) -> None:
    index = make_index(tmp_path)
    assert index.match_text("Understood") is None
    assert index.match_text("Understood.") is not None
    match = index.match_lines(["Anby", "Understood"])
    assert match is not None
    assert match.text_id == "dialogue_3"


def test_short_hud_fragments_are_ignored(tmp_path) -> None:
    index = make_index(tmp_path)
    assert index.match_text("20") is None
    assert index.match_text("Ray") is None
    assert index.match_text("Roland") is None
    assert index.match_text("Danger ahead!") is None
    assert index.match_text("Select") is None
    assert index.match_text("Nicole") is None
