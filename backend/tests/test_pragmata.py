from __future__ import annotations

import json

from backend.pragmata import PragmataTextIndex


def test_official_pragmata_line_and_speaker_match(tmp_path) -> None:
    payload = {
        "records": [{
            "text_id": "mes_main/event/cutscene/cs0010.msg.23:cs0010_0020_Ch07200",
            "english": "This is research vessel Eurotas.\nIDUS, do you copy? Over. C-Come on.",
            "chinese": "这里是欧罗塔斯号调查船。\nIDUS，请回复。完毕。靠，还是不行啊。",
            "source": "mes_main/event/cutscene/cs0010.msg.23",
            "speaker_code": "Ch07200",
        }],
        "speakers": {"Ken": ["Ken", "肯"]},
    }
    (tmp_path / "textmap.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    index = PragmataTextIndex(tmp_path)
    assert index.load()
    match = index.match_lines([
        "Ken", "This is research vessel Eurotas.",
        "IDUS, do you copy? Over. C-Come on.",
    ])
    assert match is not None
    assert match.game == "pragmata"
    assert match.chinese.startswith("这里是欧罗塔斯号")
    assert match.speaker_english == "Ken"
    assert match.speaker_chinese == "肯"


def test_pragmata_ui_copy_without_official_spoken_match_is_skipped(tmp_path) -> None:
    (tmp_path / "textmap.json").write_text(
        json.dumps({"records": [], "speakers": {}}), encoding="utf-8"
    )
    index = PragmataTextIndex(tmp_path)
    assert index.load()
    assert index.match_lines(["General Director", "Yasuhiro Ampo"]) is None
