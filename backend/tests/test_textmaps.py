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
            "Tips_Control": "Press to launch a Basic Attack {0}.",
            "ManualQTEDialog_Select": "Select",
            "Chat_999": "Nicole",
            "Avatar_Name_Nicole": "Nicole",
            "Tips_1228010012": "To unlock it, you need to obtain an <color=#FFAF2C>S</color>-Rank in the previous battle.",
            "Comic_test": "{M#What's going on? My eyes just...}{F#What's going on? My eyes just...}",
            "Comic_line_1": "We finally made it inside.",
            "Comic_line_2": "Keep moving before they catch us.",
            "Comic_scroll_1": "...Thanks for your cooperation. We have a rough idea of how things unfolded.",
            "Comic_scroll_2": "Earlier today, you all ended up deep in the Hollow after the Bangboo with your carrot malfunctioned.",
            "Comic_scroll_3": "Then, you were attacked by an unknown monster right here.",
            "GalGame_Chapter02_16_03": "Don't forget, although the upcoming metro renovation project also goes through this area, Public Security has yet to approve any units or individuals to enter.",
            "GalGame_Chapter02_16_08": "But that's not important. We should start looking for the prototype.",
            "unrelated_short": "The prototype?",
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
            "Tips_Control": "按下{0}发动普通攻击。",
            "ManualQTEDialog_Select": "选择",
            "Chat_999": "妮可",
            "Avatar_Name_Nicole": "妮可",
            "Tips_1228010012": "需于上次战斗中取得<color=#FFAF2C>「S级」评价</color>，方能解锁据点入口",
            "Comic_test": "{M#怎么回事？我的眼睛…}{F#怎么回事？我的眼睛…}",
            "Comic_line_1": "我们终于进来了。",
            "Comic_line_2": "在他们追上前继续走。",
            "Comic_scroll_1": "……感谢配合。事情的经过我们已经大致了解了。",
            "Comic_scroll_2": "今天早些时候，你们跟着出故障的萝卜邦布深入了空洞。",
            "Comic_scroll_3": "然后，你们就在这里遭到了一只未知怪物的袭击。",
            "GalGame_Chapter02_16_03": "别忘了，即使地铁改建项目也经过这里，治安局仍未批准任何单位或个人进入。",
            "GalGame_Chapter02_16_08": "不过现在就不说这些了，我们还是赶快开始找原型机吧。",
            "unrelated_short": "「原型机」？",
        },
    )
    write_map(index, "en_overwrite", {"dialogue_old": "The current localization."})
    write_map(index, "zh_overwrite", {"dialogue_old": "当前翻译。"})
    index.load()
    return index


def test_normalize_english_ignores_punctuation_and_markup() -> None:
    assert normalize_english("<b>Don’t</b> wait — Proxy!") == "dontwaitproxy"


def test_menu_subtitles_and_unvoiced_fairy_tutorials_are_not_dialogue() -> None:
    rejected = [
        ("Event_Chat_textmap", "Talk"),
        ("ActivityBangkov_SearchBox_SubTitle2", "Output Value:"),
        ("ActivityBangkov_SearchBox_SubTitleDetail", "Searching..."),
        ("Tips_Newbie_50436_1", "Special Supply found: Blade of the Other!"),
        ("Tips_Newbie_50418_1", "This is the Storage, used to keep Supplies brought back from the Hollow."),
        ("TutorialDialogSubTitle_1", "TUTORIAL"),
    ]
    for text_id, english in rejected:
        for channel in ("dialogue", "tip", "cinematic"):
            assert not TextMapIndex.is_capture_text(text_id, english, channel)
    assert TextMapIndex.is_capture_text("Comic_123", "We have to leave!", "cinematic")
    assert TextMapIndex.is_capture_text("Video_123", "We have to leave!", "cinematic")
    assert TextMapIndex.is_capture_text("GalGame_123", "We have to leave!", "dialogue")
    assert TextMapIndex.is_capture_text("Tips_1228010012", "To unlock it, you need to obtain an S-Rank in the previous battle.", "tip")


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
    assert index.match_text("Press to launch a Basic Attack.", channel="tip") is None


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


def test_full_fuzzy_line_beats_exact_short_suffix(tmp_path) -> None:
    index = make_index(tmp_path)
    match = index.match_lines(
        [
            "Ben",
            "But that's not important. We should start looking for t",
            "The prototype.  ?",
        ],
        threshold=82,
    )
    assert match is not None
    assert match.text_id == "GalGame_Chapter02_16_08"


def test_cumulative_comic_panel_returns_each_visible_official_line(tmp_path) -> None:
    index = make_index(tmp_path)
    matches = index.match_line_groups(
        ["We finally made it inside.", "Keep moving before they catch us."],
        channel="cinematic",
    )
    assert {match.text_id for match in matches} >= {"Comic_line_1", "Comic_line_2"}


def test_scrollable_comic_fragments_resolve_to_complete_official_lines(tmp_path) -> None:
    index = make_index(tmp_path)
    matches = index.match_line_groups(
        [
            "Menu",
            "...Thanks for your",
            "cooperation. We have a",
            "rough idea of how",
            "Earlier today, you all",
            "ended up deep in the",
            "Hollow after the",
            "Then, you were",
            "attacked by an",
            "unknown monster right",
            "here.",
        ],
        channel="cinematic",
    )
    by_id = {match.text_id: match for match in matches}
    assert set(by_id) >= {"Comic_scroll_1", "Comic_scroll_2", "Comic_scroll_3"}
    assert by_id["Comic_scroll_1"].english.endswith("things unfolded.")
    assert by_id["Comic_scroll_2"].english.endswith("carrot malfunctioned.")
    assert by_id["Comic_scroll_1"].source_ocr != by_id["Comic_scroll_1"].english
