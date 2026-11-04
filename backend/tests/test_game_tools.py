import hashlib
import io
import json
from types import SimpleNamespace
import zipfile

import pytest

from backend import game_tools as tools
from backend import media_tools


@pytest.mark.parametrize('platform', ['win32', 'linux', 'darwin'])
def test_node_reader_dependencies_belong_to_active_code_not_preserved_data(tmp_path, monkeypatch, platform):
    source, root = tmp_path / 'active-code', tmp_path / 'preserved-install'
    monkeypatch.setattr(tools, 'CODE_ROOT', source)
    monkeypatch.setattr(media_tools, 'sys', SimpleNamespace(platform=platform))
    decoder = root / 'data/voice-assets/vgmstream' / ('vgmstream-cli.exe' if platform == 'win32' else 'vgmstream-cli')
    paths = [decoder,
             root / 'work/voice-assets/galgame-perform.ts',
             *(root / 'work/voice-assets' / name for name in tools.METADATA_FILES),
             *(source / 'node_modules' / name / 'package.json' for name in ('ooz-wasm', 'xxhash-wasm'))]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture', encoding='utf-8')
    assert tools.missing_tools(root, 'zzz') == []
    assert media_tools.vgmstream_executable(root) == decoder
    decoder.unlink()
    foreign = decoder.with_name('vgmstream-cli' if platform == 'win32' else 'vgmstream-cli.exe')
    foreign.write_text('wrong-platform fixture', encoding='utf-8')
    assert tools.missing_tools(root, 'zzz') == ['Voice decoder']
    decoder.write_text('fixture', encoding='utf-8')
    stale = root / 'node_modules/ooz-wasm/package.json'
    stale.parent.mkdir(parents=True)
    stale.write_text('old version', encoding='utf-8')
    (source / 'node_modules/ooz-wasm/package.json').unlink()
    assert tools.missing_tools(root, 'zzz') == ['ooz-wasm']


def bundle(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


def test_verified_tools_keep_notices_and_reuse_unchanged_cache(tmp_path, monkeypatch):
    data = bundle({"decoder.exe": b"synthetic tool", "COPYING": b"synthetic license"})
    calls = []
    monkeypatch.setattr(tools, "download", lambda url: calls.append(url) or data)
    digest = hashlib.sha256(data).hexdigest()
    target = tmp_path / "tools"
    tools.install_archive("https://example.test/tool.zip", digest, target, ("decoder.exe", "COPYING"))
    tools.install_archive("https://example.test/tool.zip", digest, target, ("decoder.exe", "COPYING"))
    assert len(calls) == 1
    assert (target / "COPYING").read_bytes() == b"synthetic license"
    (target / "decoder.exe").write_bytes(b"corrupt")
    tools.install_archive("https://example.test/tool.zip", digest, target, ("decoder.exe", "COPYING"))
    assert len(calls) == 2
    assert (target / "decoder.exe").read_bytes() == b"synthetic tool"


@pytest.mark.parametrize("bad_name", ["../outside.exe", "C:/outside.exe", "..\\outside.exe"])
def test_unsafe_or_corrupt_tool_download_cannot_replace_working_tool(tmp_path, monkeypatch, bad_name):
    target = tmp_path / "tools"
    target.mkdir()
    (target / "decoder.exe").write_bytes(b"working")
    data = bundle({bad_name: b"unsafe", "decoder.exe": b"new"})
    monkeypatch.setattr(tools, "download", lambda _: data)
    with pytest.raises(ValueError):
        tools.install_archive("https://example.test/tool.zip", hashlib.sha256(data).hexdigest(), target, ("decoder.exe",))
    assert (target / "decoder.exe").read_bytes() == b"working"
    with pytest.raises(ValueError, match="checksum"):
        tools.install_archive("https://example.test/tool.zip", "0" * 64, target, ("decoder.exe",))
    assert (target / "decoder.exe").read_bytes() == b"working"
    assert not (tmp_path / "outside.exe").exists()


def test_metadata_refresh_validates_entire_download_and_preserves_unchanged_times(tmp_path, monkeypatch):
    data = {"PerformTemplateTb.json": {"rows": [1]}, "OngoingTipsConfigTemplateTb.json": {"rows": [2]},
            "AudioResourceData.json": {"eventReferenceBanks": [1, 2, 0]},
            "VoiceData.json": {"allPrefixes": ["synthetic/"]}}
    def download(url):
        return json.dumps(data[url.rsplit("/", 1)[1]]).encode()
    monkeypatch.setattr(tools, "download", download)
    digest, changed = tools.refresh_zzz_metadata(tmp_path)
    directory = tmp_path / "work/voice-assets"
    stamps = {file.name: file.stat().st_mtime_ns for file in directory.iterdir()}
    assert changed
    assert tools.refresh_zzz_metadata(tmp_path) == (digest, False)
    assert stamps == {file.name: file.stat().st_mtime_ns for file in directory.iterdir()}
    data["PerformTemplateTb.json"] = {"rows": [9]}
    data["VoiceData.json"] = {"incomplete": True}
    with pytest.raises(ValueError):
        tools.refresh_zzz_metadata(tmp_path)
    assert json.loads((directory / "PerformTemplateTb.json").read_text())["rows"] == [1]
