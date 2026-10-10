"""Synthetic catalogs/banks only: never depend on a contributor's game files."""
import json
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace

import pytest

from backend import honkai_assets as honkai, nte_assets as nte
from backend.local_game import LocalGameTextIndex
from backend.pragmata_audio import read_bank_play_layers


def bank(version=135, bank_id=77, language=None, event=None, dynamic=False, multi=False, bits=1):
    language = nte.wwise_hash(honkai.MANDARIN) if language is None else language
    event = nte.wwise_hash("VO_Synthetic_1") if event is None else event
    sound = struct.pack("<IIBIIB", 10, 262145, 1, 123, 200, bits)
    if version == 154:
        sound += b"\0\0\0\0" + struct.pack("<IIB", 0, 0, 0) + b"\0\0"
    objects = [(5 if dynamic else 2, sound), (3, struct.pack("<IHI", 20, 0x0403, 10)),
               (4, struct.pack("<IB", event, 2 if multi else 1) + struct.pack("<I", 20) * (2 if multi else 1))]
    hirc = struct.pack("<I", len(objects)) + b"".join(struct.pack("<BI", k, len(d)) + d for k, d in objects)
    header = struct.pack("<3I", version, bank_id, language)
    return b"BKHD" + struct.pack("<I", len(header)) + header + b"HIRC" + struct.pack("<I", len(hirc)) + hirc


def package(path, language=honkai.MANDARIN, voice=True, dynamic=False, multi=False):
    # Language offsets precede numeric IDs; language strings are authoritative.
    text = (language + "\0").encode("utf-16-le")
    lang = struct.pack("<3I", 1, 12, 2) + text
    data = bank(language=nte.wwise_hash(language), dynamic=dynamic, multi=multi)
    wem = b"RIFF" + bytes(160)
    sizes = (len(lang), 24, 24 if voice else 4, 4)
    header_size = 20 + sum(sizes)
    bank_start, sound_start = header_size + 8, header_size + 8 + len(data)
    banks = struct.pack("<I5I", 1, 77, 1, len(data), bank_start, 2)
    sounds = struct.pack("<I5I", 1, 123, 1, len(wem), sound_start, 2) if voice else struct.pack("<I", 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"AKPK" + struct.pack("<6I", header_size, 1, *sizes) + lang + banks + sounds + bytes(4) + data + (wem if voice else b""))
    return wem


def catalog(multi=False, conflicting=False):
    return {"TextMap_en.json": [{"Hash": 1, "Text": "A synthetic greeting."}],
        "TextMap_cn.json": [{"Hash": 1, "Text": "测试问候。"}] + ([{"Hash": 1, "Text": "不同文本。"}] if conflicting else []),
        "DialogData.json": [{"dialogID": 9, "audioID": "VO_Synthetic_1", "content": [{"chatContent": {"hash": 1}}] * (2 if multi else 1)}],
        "StageDialogData.json": [], "InLevelDialog.json": []}


def test_honkai_maps_catalog_hash_to_exact_chinese_event_and_original_source(tmp_path, monkeypatch):
    install, cache = tmp_path / "game", tmp_path / "cache"
    wem = package(install / "BH3_Data/StreamingAssets/Audio/AUDIO_Default.pck")
    monkeypatch.setattr(honkai, "_load_catalog", lambda _: catalog())
    result = honkai.index_install(install, cache)
    assert len(result["records"]) == 1 and "4.7" in result["message"]
    record = result["records"][0]
    assert record["audio"]["event"] == nte.wwise_hash("VO_Synthetic_1")
    assert honkai.extract_voice(install, record["audio"], Path(), Path()) == wem
    cache.mkdir()
    (cache / "textmap.json").write_text(json.dumps(result), encoding="utf-8")
    index = LocalGameTextIndex("honkai3", cache)
    for subtitle in [record["english"], record["chinese"]]:
        assert index.match_lines([subtitle], exact_only=True).text_id == record["text_id"]
    assert index.match_lines(["unmapped new chapter"], exact_only=True) is None


@pytest.mark.parametrize("changes", [{"language": "japanese"}, {"voice": False}, {"dynamic": True}, {"multi": True}])
def test_honkai_never_falls_back_to_other_languages_missing_sources_or_dynamic_voices(tmp_path, monkeypatch, changes):
    package(tmp_path / "BH3_Data/StreamingAssets/Audio/AUDIO_Default.pck", **changes)
    monkeypatch.setattr(honkai, "_load_catalog", lambda _: catalog())
    with pytest.raises(ValueError, match="No verified Honkai"):
        honkai.index_install(tmp_path, tmp_path / "cache")


@pytest.mark.parametrize("changes", [{"multi": True}, {"conflicting": True}])
def test_honkai_rejects_ambiguous_dialogue_hashes_and_multi_page_voices(changes):
    assert honkai.catalog_links(catalog(**changes)) == []


def test_honkai_package_bounds_are_checked_before_audio_can_be_read(tmp_path):
    path = tmp_path / "AUDIO_Default.pck"
    package(path)
    data = bytearray(path.read_bytes())
    language_size = struct.unpack_from("<I", data, 12)[0]
    struct.pack_into("<I", data, 28 + language_size + 4 + 12, len(data) * 2)
    path.write_bytes(data)
    with pytest.raises(ValueError, match="bounds"):
        honkai.package_tables(path)


@pytest.mark.parametrize("version,language,multi,dynamic,bits", [(154,None,False,False,1), (135,nte.wwise_hash("japanese"),False,False,1),
    (135,None,True,False,1), (135,None,False,True,1), (135,None,False,False,0)])
def test_honkai_version_language_and_fixed_play_contract(version, language, multi, dynamic, bits):
    data = bank(version=version, language=language, multi=multi, dynamic=dynamic, bits=bits)
    if version != 135 or language is not None:
        with pytest.raises(ValueError):
            honkai.bank_sources(data, 77)
    else:
        assert honkai.bank_sources(data, 77)[0] == {}


def test_honkai_voice_reference_cannot_escape_game_or_select_another_source(tmp_path):
    path = tmp_path / "BH3_Data/StreamingAssets/Audio/AUDIO_Default.pck"
    package(path)
    audio = {"package": path.relative_to(tmp_path).as_posix(), "bank": 77, "event": nte.wwise_hash("VO_Synthetic_1"), "media": 999, "language": 2}
    with pytest.raises(ValueError, match="mapping changed"):
        honkai.extract_voice(tmp_path, audio, Path(), Path())
    with pytest.raises(ValueError, match="Invalid"):
        honkai.extract_voice(tmp_path, {**audio, "package": "../outside.pck"}, Path(), Path())


def nte_cache(path, wrong_language=False, wrong_bank=False, missing_media=False, ambiguous=False):
    event = "Play_Vo_Synthetic_1"
    row = {"ns": "Dialogue", "key": "Synthetic_1", "value": "A synthetic greeting."}
    zh = {**row, "value": "测试问候。"}
    all_rows = {"en": [row], "zh-CN": [zh]}
    if ambiguous:
        all_rows["en"].append({**row, "ns": "Other", "value": "Another greeting."})
        all_rows["zh-CN"].append({**zh, "ns": "Other", "value": "其他问候。"})
    (path / "banks").mkdir(parents=True)
    (path / "localization.json").write_text(json.dumps(all_rows), encoding="utf-8")
    (path / "media.json").write_text(json.dumps([] if missing_media else [nte.MEDIA_ROOT + "123.wem"]))
    (path / "banks" / (event + ".bnk")).write_bytes(bank(version=154,
        bank_id=0 if wrong_bank else nte.wwise_hash(event),
        language=nte.wwise_hash("English" if wrong_language else "Chinese"), event=nte.wwise_hash(event)))


def test_nte_joins_namespace_key_languages_event_hash_bank_language_and_media(tmp_path):
    nte_cache(tmp_path)
    rows = nte.build_records(tmp_path)
    assert len(rows) == 1 and rows[0]["text_id"] == "nte:Dialogue:Synthetic_1"
    path = next((tmp_path / "banks").glob("*.bnk"))
    with pytest.raises(ValueError, match="version"):
        read_bank_play_layers(path)  # PRAGMATA still accepts only its own version.


@pytest.mark.parametrize("changes", [{"wrong_language": True}, {"wrong_bank": True}, {"missing_media": True}, {"ambiguous": True}])
def test_nte_unverified_or_ambiguous_voice_links_are_excluded(tmp_path, changes):
    nte_cache(tmp_path, **changes)
    assert nte.build_records(tmp_path) == []


def test_nte_reader_errors_and_arguments_never_expose_archive_metadata(tmp_path, monkeypatch):
    tool = tmp_path / "tools/NteReader.dll"
    tool.parent.mkdir()
    tool.touch()
    monkeypatch.setattr(nte, "dotnet_sdk", lambda: Path("dotnet"))
    monkeypatch.setattr(nte, "_archive_metadata", lambda *_: "synthetic-private-metadata")
    calls = []
    def fail(args, **kwargs):
        calls.append((args, kwargs))
        raise subprocess.CalledProcessError(1, args, stderr=b"synthetic-private-metadata")
    monkeypatch.setattr(nte.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="could not complete") as error:
        nte.run_reader(tmp_path / "game", tool, tmp_path / "output", "index")
    assert "synthetic-private-metadata" not in str(error.value) and all("synthetic-private-metadata" not in arg for arg in calls[0][0])
    assert json.loads(calls[0][1]["input"])["archive_metadata"] == "synthetic-private-metadata"
    assert calls[0][1]["cwd"] == tool.parent / "upstream"


@pytest.mark.parametrize("depot", [nte.MEDIA_ROOT + "../a.wem", nte.MEDIA_ROOT.replace("Chinese", "English") + "1.wem", nte.MEDIA_ROOT + "1.wem.exe"])
def test_nte_voice_reference_only_accepts_chinese_numeric_media(depot):
    with pytest.raises(ValueError, match="Invalid"):
        nte.extract_voice(Path(), {"depot": depot}, Path(), Path())


def test_nte_outputs_and_mods_cannot_mutate_or_override_the_game(tmp_path, monkeypatch):
    install = tmp_path / "game"
    install.mkdir()
    with pytest.raises(ValueError, match="outside"):
        nte.run_reader(install, Path("reader"), install / "output", "index")
    mod = install / "Client/WindowsNoEditor/HT/Content/Paks/~mods/pakchunk99-Windows.pak"
    mod.parent.mkdir(parents=True)
    mod.touch()
    tool = tmp_path / "tools/reader.dll"
    tool.parent.mkdir()
    tool.touch()
    monkeypatch.setattr(nte, "dotnet_sdk", lambda: Path("dotnet"))
    with pytest.raises(ValueError, match="mod archives"):
        nte.run_reader(install, tool, tmp_path / "output", "index")


def test_honkai_changed_audio_pack_triggers_refresh_and_stale_source_cannot_play(tmp_path):
    path = tmp_path / "BH3_Data/StreamingAssets/Audio/AUDIO_Default.pck"
    package(path)
    old = honkai.fingerprint(tmp_path)
    package(path, voice=False)
    assert honkai.fingerprint(tmp_path) != old


def test_missing_sdk_is_reported_without_downloading_any_nte_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(nte, "dotnet_sdk", lambda: None)
    monkeypatch.setattr(nte, "install_archive", lambda *_: pytest.fail("Do not download tools without the SDK"))
    with pytest.raises(ValueError, match=".NET 10 SDK"):
        nte.ensure_extractor(tmp_path)


def test_honkai_authored_pages_identify_whole_bilingual_utterance_and_one_original_voice(tmp_path):
    data = catalog()
    data['TextMap_en.json'].append({'Hash': 2, 'Text': 'A second synthetic page.'})
    data['TextMap_cn.json'].append({'Hash': 2, 'Text': '第二段测试文本。'})
    data['DialogData.json'][0]['content'].append({'chatContent': {'hash': 2}})
    records = honkai.catalog_links(data)
    assert len(records) == 1
    row = records[0]
    assert row.pop('event') == 'VO_Synthetic_1'
    row['audio'] = {'file': 'one-complete-authored-performance'}
    (tmp_path / 'textmap.json').write_text(json.dumps({'records': records}), encoding='utf8')
    index = LocalGameTextIndex('honkai3', tmp_path)
    for page in row['ocr_english'] + row['ocr_chinese']:
        match = index.match_lines([page], exact_only=True)
        assert match.text_id == row['text_id']
        assert match.english == 'A synthetic greeting. A second synthetic page.'
        assert match.chinese == '测试问候。 第二段测试文本。'
    assert index.match_lines(['An invented second page.'], exact_only=True) is None


def test_authored_page_shared_by_different_performances_is_ambiguous(tmp_path):
    rows = [{'text_id': f'honkai3:{n}', 'english': f'Whole performance {n}.', 'chinese': f'完整文本{n}。',
             'ocr_english': ['A shared synthetic page.'], 'ocr_chinese': ['共同测试片段。'],
             'audio': {'file': f'original-{n}'}} for n in [1, 2]]
    (tmp_path / 'textmap.json').write_text(json.dumps({'records': rows}), encoding='utf8')
    index = LocalGameTextIndex('honkai3', tmp_path)
    assert index.match_lines(['A shared synthetic page.'], exact_only=True) is None
    assert index.match_lines(['共同测试片段。'], exact_only=True) is None


def test_ocr_compatibility_digits_preserve_distinct_exact_voice_identities(tmp_path):
    rows = [{'text_id': f'nte:{n}', 'english': f'Synthetic edition Q{glyph} is available.',
             'chinese': f'测试版本{n}已发布。', 'audio': {'file': f'original-{n}'}}
            for n, glyph in [(3, '³'), (4, '⁴')]]
    (tmp_path / 'textmap.json').write_text(json.dumps({'records': rows}), encoding='utf8')
    index = LocalGameTextIndex('nte', tmp_path)
    for number in [3, 4]:
        assert index.match_lines([f'Synthetic edition Q{number} is available.'], exact_only=True).text_id == f'nte:{number}'
    assert index.match_lines(['Synthetic edition Q5 is available.'], exact_only=True) is None
