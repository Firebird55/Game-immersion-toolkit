import json

from backend.bilingual import normalize_chinese, subtitle_candidates
from backend.pragmata import PragmataTextIndex
from backend.tests.test_textmaps import make_index


def test_chinese_normalization_keeps_dialogue_and_latin_names():
    assert normalize_chinese("你 好，ＩＤＵＳ！") == "你好idus"
    assert normalize_chinese("你好") != normalize_chinese("再见")


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
