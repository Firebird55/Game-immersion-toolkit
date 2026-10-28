"""Authored synthetic Valve resources exercise bounds and cross-file identities."""
import struct
import zlib

import pytest

from backend.preparation_errors import PreparationFailure
from backend.source_formats import VpkArchive, compiled_captions, keyvalues, safe_name


def vpk(root, *, version=2, archive=0x7fff, crc=None, length=None):
    prefix, payload = b'RI', b'FFsample'
    tree = (b'wav\0sound/dialogue\0line\0'
            + struct.pack('<IHHIIH', zlib.crc32(prefix + payload) if crc is None else crc,
                          len(prefix), archive, 0, len(payload) if length is None else length, 0xffff)
            + prefix + b'\0\0\0')
    inline = payload if archive == 0x7fff else b''
    header = struct.pack('<3I', 0x55aa1234, version, len(tree))
    if version == 2:
        header += struct.pack('<4I', len(inline), 0, 0, 0)
    path = root / 'test_dir.vpk'
    path.write_bytes(header + tree + inline)
    if archive != 0x7fff:
        (root / f'test_{archive:03d}.vpk').write_bytes(payload)
    return path


@pytest.mark.parametrize('version,archive', [(1, 0x7fff), (2, 0x7fff), (1, 0), (2, 3)])
def test_vpk_preload_inline_and_numbered_chunks(tmp_path, version, archive):
    reader = VpkArchive(vpk(tmp_path, version=version, archive=archive))
    assert reader.read('Sound/Dialogue/LINE.wav') == b'RIFFsample'
    with pytest.raises(PreparationFailure, match='size limit'):
        reader.read('sound/dialogue/line.wav', maximum=4)


def test_vpk_checksums_and_truncated_chunk_are_not_missing_voice(tmp_path):
    reader = VpkArchive(vpk(tmp_path, archive=0, crc=0))
    with pytest.raises(PreparationFailure, match='checksum'):
        reader.read('sound/dialogue/line.wav')
    reader = VpkArchive(vpk(tmp_path, archive=0, length=100))
    with pytest.raises(PreparationFailure, match='bounds'):
        reader.read('sound/dialogue/line.wav')
    with pytest.raises(PreparationFailure, match='bounds'):
        VpkArchive(vpk(tmp_path, length=100))


@pytest.mark.parametrize('path', ['../escape', 'sound//line', '/absolute', 'c:/line', 'sound\\line'])
def test_archive_paths_cannot_escape_or_alias(path):
    with pytest.raises(PreparationFailure):
        safe_name(path)


def test_keyvalues_retains_authored_variants_and_windows_conditions():
    data = '''// synthetic sound event
    "Dialogue.Line" { "rndwave" { "wave" "voice/a.wav" "wave" "voice/b.wav" }
        "caption" "a \\"quote\\" and {brace}" "platform" "windows" [$WIN32]
        "platform" "console" [$X360] "manifest" "desktop" [!$GAMECONSOLE]
        "manifest" "console" [$GAMECONSOLE] }
    '''.encode()
    rows = keyvalues(data)
    assert rows[0][1][0] == ('rndwave', [('wave', 'voice/a.wav'), ('wave', 'voice/b.wav')])
    assert rows[0][1][1] == ('caption', 'a "quote" and {brace}')
    assert rows[0][1][2:] == [('platform', 'windows'), ('manifest', 'desktop')]
    assert keyvalues('"tokens" { "test" "字幕" }'.encode('utf-16')) == [('tokens', [('test', '字幕')])]
    for invalid in (b'"a" {', b'"a" }', b'"a" "b" [$NEWPLATFORM]', b'"unterminated'):
        with pytest.raises(PreparationFailure):
            keyvalues(invalid)


def test_compiled_caption_directory_and_utf16_bounds():
    text = 'An authored test caption.'
    encoded = (text + '\0').encode('utf-16-le')
    token = zlib.crc32(b'dialogue.line')
    data = (struct.pack('<4s5I', b'VCCD', 1, 1, 128, 1, 36)
            + struct.pack('<IIHH', token, 0, 0, len(encoded)) + encoded.ljust(128, b'\0'))
    assert compiled_captions(data) == {token: text}
    for offset, value in ((28, struct.pack('<I', 1)), (32, struct.pack('<H', 127)), (34, struct.pack('<H', 3))):
        broken = bytearray(data)
        broken[offset:offset+len(value)] = value
        with pytest.raises(PreparationFailure):
            compiled_captions(broken)
