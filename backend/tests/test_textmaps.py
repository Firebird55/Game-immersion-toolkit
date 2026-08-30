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
            "Tips_1228010012": "To unlock it, you need to obtain an <color=#FFAF2C>S</color>-Rank in the previous battle.",
            "Comic_test": "{M#What's going on? My eyes just...}{F#What's going on? My eyes just...}",
            "GalGame_Chapter02_16_03": "Don't forget, although the upcoming metro renovation project also goes through this area, Public Security has yet to approve any units or individuals to enter.",
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
            "Tips_1228010012": "需于上次战斗中取得<color=#FFAF2C>「S级」评价</color>，方能解锁据点入口",
            "Comic_test": "{M#怎么回事？我的眼睛…}{F#怎么回事？我的眼睛…}",
            "GalGame_Chapter02_16_03": "别忘了，即使地铁改建项目也经过这里，治安局仍未批准任何单位或个人进入。",
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


def test_top_right_tip_uses_separate_safe_channel(tmp_path) -> None:
    index = make_index(tmp_path)
    text = "To unlock it, you need to obtain an S-Rank in the previous battle."
    assert index.match_text(text) is None
    match = index.match_text(text, channel="tip")
    assert match is not None
    assert match.text_id == "Tips_1228010012"
    assert match.chinese.startswith("需于上次战斗中取得")


def test_comic_gender_variants_match_in_cinematic_channel(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_text("What's going on? My eyes just...", channel="cinematic")
    assert match is not None
    assert match.text_id == "Comic_test"
    assert match.chinese == "怎么回事？我的眼睛…"


def test_crowded_dialogue_crop_can_match_three_subtitle_rows(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_lines(
        [
            "QICAI JIE",
            "Belle",
            "Don't forget, although the upcoming metro renovation",
            "project also goes through this area, Public Security",
            "has yet to approve any units or individuals to enter.",
        ]
    )
    assert match is not None
    assert match.text_id == "GalGame_Chapter02_16_03"
