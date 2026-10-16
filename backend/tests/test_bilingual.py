import json

from backend.bilingual import normalize_chinese, subtitle_candidates
from backend.pragmata import PragmataTextIndex
from backend.tests.test_textmaps import make_index


def test_chinese_normalization_keeps_dialogue_and_latin_names():
    assert normalize_chinese("你 好，ＩＤＵＳ！") == "你好idus"
    assert normalize_chinese("你好") != normalize_chinese("再见")


def test_traditional_chinese_matches_without_changing_official_text(tmp_path):
    assert normalize_chinese("裡面的燈籠，ＩＤＵＳ！") == normalize_chinese("里面的灯笼，IDUS！")
    index = make_index(tmp_path)
    match = index.match_text("路上的戰鬥交給我們。")
    assert match is not None and match.score == 100
    assert match.chinese == "路上的战斗交给我们。"
    assert match.source_ocr == "路上的戰鬥交給我們。"


def test_traditional_exact_lookup_keeps_ambiguous_performances():
    from types import SimpleNamespace
    from backend.bilingual import ChineseLookup
    records = [SimpleNamespace(chinese="头发很长。"), SimpleNamespace(chinese="頭髮很長。")]
    lookup = ChineseLookup(records)
    assert lookup.match("頭髮很長。", 88) == (records, 100.0)


def test_zzz_both_languages_resolve_same_voice_identity(tmp_path):
    index = make_index(tmp_path)
    english = index.match_text("Leave any combat along the way to us.")
    chinese = index.match_text("路 上 的 战 斗 交 给 我 们。")
    assert chinese is not None
    assert (chinese.text_id, chinese.english, chinese.chinese) == (english.text_id, english.english, english.chinese)
    assert index.match_text("妮可") is None
    assert index.match_text("选 择") is None


def test_pragmata_chinese_wrapping_and_speaker(tmp_path):
    (tmp_path / "textmap.json").write_text(json.dumps({"records": [{
        "text_id": "scene-1", "english": "Stay close. I will protect you.",
        "chinese": "跟紧我。我会保护你。", "source": "scene"}],
        "speakers": {"Diana": ["Diana", "戴安娜"]}}, ensure_ascii=False), encoding="utf-8")
    index = PragmataTextIndex(tmp_path)
    assert index.load()
    match = index.match_lines(["戴安娜", "跟紧我。", "我会保护你。"])
    assert match.text_id == "pragmata:scene-1"
    assert match.speaker_english == "Diana"


def test_bilingual_mod_blocks_are_not_concatenated():
    candidates = subtitle_candidates(["杰克 Jackie：", "跟紧我。", "我会保护你。", "Stay close.", "I will protect you."])
    assert "跟紧我。 我会保护你。" in candidates
    assert "Stay close. I will protect you." in candidates
    assert "跟紧我。 我会保护你。 Stay close." not in candidates


def test_chinese_header_filters_keep_zzz_unvoiced_screens_excluded():
    from backend.capture import CaptureService
    assert CaptureService._classify_screen_header(["前 情 回 顾"]) == "story_recap"
    assert CaptureService._classify_screen_header(["剧情回顾"]) == "story_recap"
    assert CaptureService._classify_screen_header(["劇情回顧"]) == "story_recap"
    assert CaptureService._classify_screen_header(["剧情委托"]) == "hdd"
    assert CaptureService._classify_screen_header(["战斗委托"]) == "hdd"
    assert CaptureService._classify_screen_header(["戰鬥委託"]) == "hdd"
    assert CaptureService._classify_screen_header(["我会保护你。"]) is None


def test_exact_chinese_from_another_channel_never_fuzzes_into_dialogue():
    from types import SimpleNamespace
    from backend.bilingual import ChineseLookup
    lookup = ChineseLookup([
        SimpleNamespace(chinese="这段是故事回顾画面。", channel="recap"),
        SimpleNamespace(chinese="这段是故事回顾画面啊。", channel="dialogue"),
    ])
    assert lookup.match("这段是故事回顾画面。", 88,
                        allowed=lambda record: record.channel == "dialogue") is None
    assert lookup._choices == {}  # Excluded exact text requires no fuzzy-index scan.


def test_background_chinese_index_build_leaves_status_responsive(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    index = make_index(tmp_path)
    original = index._is_allowed_record
    entered, release = threading.Event(), threading.Event()
    def blocked(record, channel):
        entered.set()
        assert release.wait(5)
        return original(record, channel)
    monkeypatch.setattr(index, "_is_allowed_record", blocked)
    with ThreadPoolExecutor(max_workers=2) as pool:
        loading = pool.submit(index.load)
        try:
            assert entered.wait(2)
            assert pool.submit(index.status).result(timeout=1)["ready"] is True
        finally:
            release.set()
        loading.result(timeout=5)


def test_chinese_cinematic_fragment_does_not_rescan_all_records_per_frame(tmp_path):
    index = make_index(tmp_path)
    class PreparedRecords(dict):
        def items(self):
            raise AssertionError("Per-frame enumeration consumes subtitle stability time")
    index._chinese_lookup.records = PreparedRecords(index._chinese_lookup.records)
    match = index._match_cinematic_fragment("你们跟着出故障的萝卜邦布深入了空洞", 88)
    assert match is not None and match.text_id == "Comic_scroll_2"
    assert match.chinese.startswith("今天早些时候")


def test_ocr_ellipsis_row_does_not_split_a_wrapped_mandarin_subtitle(tmp_path):
    from backend.local_game import LocalGameTextIndex
    (tmp_path / "textmap.json").write_text(json.dumps({"records": [{
        "text_id": "wuwa:rain", "english": "The rain... We must hurry.",
        "chinese": "是溯洄雨……不好，得抓紧时间了。", "audio": {"depot": "exact-original"}}]},
        ensure_ascii=False), encoding="utf-8")
    index = LocalGameTextIndex("wuwa", tmp_path)
    match = index.match_lines(["是溯洄雨 ..", "…… . 不好,得抓紧时间了。"])
    assert match is not None and match.text_id == "wuwa:rain" and match.score == 100
