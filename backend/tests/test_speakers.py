from __future__ import annotations

import json

from backend.models import TextMatch
from backend.speakers import SpeakerResolver
from backend.storage import TranscriptStore
from backend.textmaps import TextMapIndex
from backend.voice_assets import VoiceAssetService


def _textmaps(tmp_path) -> TextMapIndex:
    index = TextMapIndex(tmp_path / "maps")
    index.data_dir.mkdir()
    values = {
        "en_base": {"Avatar_Name_Belle": "Belle", "Avatar_Name_Nanson": "Nanson"},
        "zh_base": {"Avatar_Name_Belle": "铃", "Avatar_Name_Nanson": "南升"},
        "en_overwrite": {},
        "zh_overwrite": {},
    }
    for name, payload in values.items():
        index.file_path(name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    index.load()
    return index


def _line(store: TranscriptStore, text_id: str, source_ocr: str):
    return store.add(
        TextMatch(
            text_id=text_id,
            english="We should leave now.",
            chinese="我们该走了。",
            source_ocr=source_ocr,
            score=100,
            kind="exact",
        ),
        "session",
    )


def test_speaker_uses_exact_game_voice_path(tmp_path):
    package = tmp_path / "voice.pck"
    package.write_bytes(b"unused")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "entries": {
        "line-1": {"source": "chinese(prc)/ex/VO_Galgame/Ver3_1/VO_Nanson/line.wem"}
    }}), encoding="utf-8")
    store = TranscriptStore(tmp_path / "transcript.db")
    assets = VoiceAssetService(manifest, tmp_path / "decoder.exe", tmp_path / "audio")
    resolver = SpeakerResolver(_textmaps(tmp_path), assets, store)
    enriched = resolver.enrich(_line(store, "line-1", "We should leave now."))
    assert (enriched.speaker_english, enriched.speaker_chinese) == ("Nanson", "南升")
    assets.close()


def test_speaker_falls_back_to_ocr_nameplate(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": 1, "entries": {}}), encoding="utf-8")
    store = TranscriptStore(tmp_path / "transcript.db")
    assets = VoiceAssetService(manifest, tmp_path / "decoder.exe", tmp_path / "audio")
    resolver = SpeakerResolver(_textmaps(tmp_path), assets, store)
    enriched = resolver.enrich(_line(store, "line-2", "Belle We should leave now."))
    assert (enriched.speaker_english, enriched.speaker_chinese) == ("Belle", "铃")
    assets.close()
