"""Publisher file selection regressions using authored containers and checksums."""
import hashlib
import io
import struct

import pytest

from backend import nte_release, wuthering_release as live
from backend import wuthering_release_pak as pak


def test_downloaded_pak_directory_selects_exact_wem_and_detects_changed_data(tmp_path, monkeypatch):
    def i(value):
        return struct.pack('<i', value)

    def string(text):
        value = text.encode() + b'\0'
        return i(len(value)) + value

    audio = b'RIFF' + i(6) + b'WAVEok'
    member_offset = 32
    header = struct.pack('<QQQI', 0, len(audio), len(audio), 0) + hashlib.sha1(audio).digest() + bytes(5)
    directory = i(1) + string('voices/') + i(1) + string('a.wem') + i(0)
    dir_offset = 300
    encoded = struct.pack('<IBII', 0xa0000000, 0, len(audio), member_offset)
    main = (string('../../../Client/') + i(1) + bytes(8) + i(1) + bytes(36) + i(1)
            + struct.pack('<QQ', dir_offset, len(directory)) + hashlib.sha1(directory).digest() + i(len(encoded)) + encoded)
    index_offset = 128
    data = bytearray(1024)
    data[member_offset:member_offset+len(header+audio)] = header + audio
    data[dir_offset:dir_offset+len(directory)] = directory
    data[index_offset:index_offset+len(main)] = main
    footer = pak.MAGIC + struct.pack('<IQQ', 12, index_offset, len(main)) + hashlib.sha1(main).digest()
    data[820:820+len(footer)] = footer
    monkeypatch.setattr(pak, 'block', lambda url, total, pos, length: bytes(data[pos:pos+length]))
    reader = pak.Package('publisher', len(data), 'generation1', tmp_path, ())
    assert reader.member('Client/voices/other.wem') is None
    assert reader.member('Client/voices/a.wem') == audio
    data[member_offset + len(header)] ^= 1
    with pytest.raises(ValueError):
        reader.member('Client/voices/a.wem')


def test_publisher_overlay_wins_and_a_corrupt_replacement_cannot_fall_back(monkeypatch, tmp_path):
    data = b'RIFF\x06\0\0\0WAVEok'
    seen = []
    class Reader:
        def __init__(self, url, *_):
            seen.append(url)
            self.url = url
        def member(self, path):
            assert path.endswith('/en_vo_demo.wem')
            return data if self.url == 'update' else None
    monkeypatch.setattr(live.pak, 'Package', Reader)
    products = {'en/BaseFiles/base.pak': ('base', 10, 'b'), 'en/PatchFiles/extra.pak': ('update', 12, 'u')}
    assert live.voice(tmp_path, products, 'en', 'vo_demo', ()) == data
    assert seen == ['update']
    data = b'broken'
    with pytest.raises(ValueError):
        live.voice(tmp_path, products, 'en', 'vo_demo', ())
    assert seen == ['update', 'update']


def test_embedded_updater_file_requires_correct_range_and_content_before_replacement(monkeypatch, tmp_path):
    media = b'abc'
    item = nte_release.File(3, hashlib.md5(media).hexdigest(), 15, '1'*32, 6)
    output = tmp_path / 'result'
    output.write_bytes(b'older')
    url = 'https://ntecdn1.perfectworld.com/clientRes/PC_140/Res/1/' + '1'*32 + '.15'
    class Reply(io.BytesIO):
        status = 206
        headers = {'Content-Range': 'bytes 6-8/15'}
        def geturl(self):
            return url
    monkeypatch.setattr(nte_release.urllib.request, 'urlopen', lambda request, timeout: Reply(media))
    media = b'bad'
    with pytest.raises(ValueError, match='checksum'):
        nte_release.save_file('nte-global', 'PC_140', item, output)
    assert output.read_bytes() == b'older'
    media = b'abc'
    nte_release.save_file('nte-global', 'PC_140', item, output)
    assert output.read_bytes() == media


def test_publisher_manifest_hash_precedes_parsing_and_a_changed_pointer_requires_retry(monkeypatch):
    blob = b'{"Version":"2.0.1"}'
    monkeypatch.setattr(live, 'download', lambda url, limit: blob)
    assert live._manifest('publisher', hashlib.sha1(blob).hexdigest())['Version'] == '2.0.1'
    with pytest.raises(ValueError):
        live._manifest('publisher', '0'*40)
    with pytest.raises(ValueError, match='Retry'):
        live.verify_pointers({'publisher': b'older'})


def test_checked_nte_envelope_rejects_another_digest_or_advertised_size(monkeypatch):
    import zlib
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    expected = b'<ResList/>'
    metadata = bytes(range(16)), bytes(reversed(range(16)))
    monkeypatch.setattr(nte_release, '_parameters', lambda region: metadata)
    cipher = AES.new(metadata[0], AES.MODE_CBC, metadata[1])
    body = cipher.encrypt(pad(zlib.compress(expected), 16))
    head = b'PatcherXML0\0' + struct.pack('<I', len(expected))
    md5 = hashlib.md5(expected).hexdigest()
    assert nte_release._xml(head + body, 'nte-cn', md5).tag == 'ResList'
    with pytest.raises(ValueError):
        nte_release._xml(head + body, 'nte-cn', '0' * 32)
    with pytest.raises(ValueError):
        nte_release._xml(head[:12] + struct.pack('<I', 1) + body, 'nte-cn', md5)
