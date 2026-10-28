"""Synthetic Persona fixtures; no game files, account, network or native tools."""
from pathlib import Path
import struct
from types import SimpleNamespace
import wave

import pytest

from backend import persona5_assets as assets
from backend.persona_cri import Cpk, Entry, awb_entries, crilayla, read_acb, utf
from backend.persona_message import package_members, read_messages, tokens
from backend.preparation_errors import PreparationFailure


def table(columns, rows):
    strings, blobs = bytearray(b'\0'), bytearray()

    def string(value):
        at = len(strings)
        strings.extend(value.encode() + b'\0')
        return at

    schema = b''.join(bytes([0x50 | kind]) + struct.pack('>I', string(name)) for name, kind in columns)
    body = bytearray()
    for row in rows:
        for name, kind in columns:
            value = row[name]
            if kind == 10:
                body.extend(struct.pack('>I', string(value)))
            elif kind == 11:
                body.extend(struct.pack('>II', len(blobs), len(value)))
                blobs.extend(value)
            else:
                body.extend(struct.pack('>' + {0: 'B', 2: 'H', 4: 'I', 6: 'Q', 8: 'f'}[kind], value))
    rows_at = 32 + len(schema)
    strings_at, blobs_at = rows_at + len(body), rows_at + len(body) + len(strings)
    size = blobs_at + len(blobs)
    return b'@UTF' + struct.pack('>IIIIIHHI', size - 8, 0x10000 | (rows_at - 8), strings_at - 8,
                                 blobs_at - 8, 0, len(columns), len(body) // max(1, len(rows)), len(rows)) + schema + body + strings + blobs


def voice_command(cue):
    values = (8, 0, 0, cue, 65535, 0)
    return b'\xf7\x61' + b''.join(bytes([((v & 255) + 1) & 255, ((v >> 8) + 1) & 255]) for v in values)


def message(pages, choice=False, endian='>'):
    content = [b'\xf1\x41' + page + b'\xf1\x21\0' for page in pages]
    start = 56
    header_size = 32 if choice else 28
    page_start = start + header_size + len(pages) * 4 + 4
    offsets, at = [], page_start
    for page in content:
        offsets.append(at - 32)
        at += len(page)
    name = b'TEST_MESSAGE'.ljust(24, b'\0')
    header = struct.pack(endian + 'HHI', 0, len(pages), 0) if choice else struct.pack(endian + 'HH', len(pages), 65535)
    row = name + header + struct.pack(endian + 'I' * len(pages), *offsets) + struct.pack(endian + 'I', sum(map(len, content))) + b''.join(content)
    data = bytearray(56)
    data[:4] = b'\7\0\0\0'
    data[8:12] = b'1GSM' if endian == '>' else b'MSG1'
    struct.pack_into(endian + 'I', data, 24, 1)
    struct.pack_into(endian + 'II', data, 32, int(choice), start - 32)
    data.extend(row)
    struct.pack_into(endian + 'I', data, 4, len(data))
    return bytes(data)


def adx(silent=False):
    header = bytearray(40)
    header[:8] = b'\x80\0\0\x24\3\x12\4\1'
    struct.pack_into('>II', header, 8, 24000, 32)
    header[18:20] = b'\4\x09'
    return bytes(header) + b'\0\0' + bytes([0 if silent else 17]) * 16


def awb(data):
    header = b'AFS2\2\4\2\0' + struct.pack('<IHHHII', 1, 32, 0, 0, 26, 32 + len(data))
    return header, header.ljust(32, b'\0') + data


def cue_bank(header, cue=4, complex_event=False):
    waves = table([('Streaming', 0), ('EncodeType', 0), ('StreamAwbId', 2), ('MemoryAwbId', 2),
                   ('SamplingRate', 4), ('NumSamples', 4), ('NumChannels', 0)],
                  [dict(Streaming=1, EncodeType=0, StreamAwbId=0, MemoryAwbId=65535, SamplingRate=24000, NumSamples=32, NumChannels=1)])
    synths = table([('Type', 0), ('ReferenceItems', 11)], [dict(Type=0, ReferenceItems=b'\0\1\0\0')])
    tracks = table([('EventIndex', 2)], [dict(EventIndex=0)])
    events = table([('Command', 11)], [dict(Command=b'\x07\xd0\x04\0\2\0\0\0\0\0' + (b'\0' if complex_event else b''))])
    sequences = table([('NumTracks', 2), ('TrackIndex', 11)], [dict(NumTracks=1, TrackIndex=b'\0\0')])
    cues = table([('CueId', 4), ('ReferenceType', 0), ('ReferenceIndex', 2), ('Length', 4)],
                 [dict(CueId=cue, ReferenceType=3, ReferenceIndex=0, Length=1)])
    headers = table([('Header', 11)], [dict(Header=header)])
    values = dict(CueTable=cues, WaveformTable=waves, SynthTable=synths, TrackTable=tracks,
                  TrackEventTable=events, SequenceTable=sequences, StreamAwbAfs2Header=headers)
    return table([(key, 11) for key in values], [values])


def test_message_pages_and_choice_schema():
    charset = list(map(chr, range(128)))
    for endian in ('<', '>'):
        row = read_messages(message([voice_command(4) + b'First page.', voice_command(9) + b'Second page.'], endian=endian), charset)[0]
        assert [page['voices'][0][3] for page in row['pages']] == [4, 9]
        assert [page['text'] for page in row['pages']] == ['First page.', 'Second page.']
    assert read_messages(message([b'Choose this.'], choice=True), charset)[0]['kind'] == 1
    with pytest.raises(PreparationFailure):
        read_messages(message([b'Broken'])[:-1], charset)
    with pytest.raises(PreparationFailure):
        tokens(b'\xf7\x61\1', charset)


def test_utf_cue_graph_and_bounds():
    header, data = awb(adx())
    bank = read_acb(cue_bank(header))
    assert bank['bindings'][4]['id'] == 0
    assert awb_entries(header, len(data)) == {0: (32, len(adx()))}
    assert read_acb(cue_bank(header, complex_event=True))['unresolved'] == {4}
    with pytest.raises(PreparationFailure):
        awb_entries(header, len(data) - 1)
    with pytest.raises(PreparationFailure):
        utf(cue_bank(header)[:-1])
    assert assets.silent_adx(adx(True))
    assert not assets.silent_adx(adx(False))
    assert not assets.silent_adx(None)


def test_crilayla_and_named_package_bounds():
    # Four reverse-order literal bytes, with MSB-first flag/data bits.
    bits = ''.join('0' + f'{byte:08b}' for byte in b'dcba')
    bits += '0' * (-len(bits) % 8)
    compressed = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))[::-1]
    packed = b'CRILAYLA' + struct.pack('<II', 4, len(compressed)) + compressed + b'X' * 256
    assert crilayla(packed) == b'X' * 256 + b'abcd'
    with pytest.raises(PreparationFailure):
        crilayla(packed, 259)
    package = struct.pack('>I', 1) + b'fixture.bmd'.ljust(32, b'\0') + struct.pack('>I', 3) + b'abc'
    assert package_members(package) == [('fixture.bmd', b'abc')]
    old = b'fixture.bmd'.ljust(252, b'\0') + struct.pack('<I', 3) + b'abc'
    assert package_members(old.ljust(320, b'\0') + bytes(256)) == [('fixture.bmd', b'abc')]
    with pytest.raises(PreparationFailure):
        package_members(package.replace(b'fixture.bmd', b'../evil.bmd'))


def test_cpk_directory_read_and_traversal_are_bounded(tmp_path):
    def build(name, length=3):
        main = table([('TocOffset', 6), ('ContentOffset', 6)], [dict(TocOffset=2048, ContentOffset=4096)])
        toc = table([('DirName', 10), ('FileName', 10), ('FileOffset', 6), ('FileSize', 4), ('ExtractSize', 4)],
                    [dict(DirName='event', FileName=name, FileOffset=2048, FileSize=length, ExtractSize=length)])
        packet = lambda magic, data: magic + bytes(4) + struct.pack('<Q', len(data)) + data
        return packet(b'CPK ', main).ljust(2048, b'\0') + packet(b'TOC ', toc).ljust(2048, b'\0') + b'abc'
    path = tmp_path / 'fixture.cpk'
    path.write_bytes(build('fixture.bmd'))
    archive = Cpk(path)
    assert archive.read('event/fixture.bmd') == b'abc'
    with pytest.raises(PreparationFailure):
        archive.read('event/fixture.bmd', 2)
    path.write_bytes(build('../escape.bmd'))
    with pytest.raises(PreparationFailure):
        Cpk(path)
    path.write_bytes(build('fixture.bmd', length=4))
    with pytest.raises(PreparationFailure):
        Cpk(path)


def test_official_locales_missing_pack_and_metadata_cache(tmp_path, monkeypatch):
    assert assets.SUPPORTED_LOCALES == ('en', 'ja')
    assert set(assets.TEXT_LOCALES) == {'en', 'ja', 'fr', 'de', 'it', 'es-ES', 'ko', 'zh-Hans', 'zh-Hant'}
    assert assets.probe_voice_pack(tmp_path, 'ja') == 'missing'
    with pytest.raises(PreparationFailure, match='text pack is missing'):
        assets.index_language(tmp_path, tmp_path, 'ja', [])
    monkeypatch.setattr(assets.urllib.request, 'urlopen', lambda *_a, **_kw: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(PreparationFailure, match='not cached'):
        assets._metadata(tmp_path / 'table.tsv', 'not-fetched', '0' * 64)
    assert assets._bank_path('event_data/message/e000/e001_002.bmd', (8, 2, 1, 4, 0, 0)) is None
    assert assets._bank_path('field/npc/actor.bf', (8, 0, 0, 4, 0, 0)) is None


def test_index_separates_silent_missing_unknown_and_original_voice(tmp_path, monkeypatch):
    (tmp_path / 'CPK').mkdir()
    for name in ('EN', 'SOUND_E'):
        (tmp_path / 'CPK' / (name + '.CPK')).touch()
    header, wavebank = awb(adx())
    source = message([voice_command(4) + b'Voiced line.', voice_command(99) + b'Missing cue.', b'Unknown line.'])
    files = {'event_data/message/e000/e001_002.bmd': source,
             'event_data/message/e000/e001_003.bmd': message([b'Choice.'], choice=True),
             'sound/event/e001_002.acb': cue_bank(header), 'sound/event/e001_002.awb': wavebank}

    class FakeCpk:
        def __init__(self, path):
            self.entries = {key: Entry(key, 0, len(value), len(value)) for key, value in files.items()
                            if key.startswith('sound/') == (Path(path).stem in ('SOUND_E', 'BASE'))}

        def read(self, name, *_args):
            return files[name]

        def read_at(self, offset, size, *_args):
            return wavebank[offset:offset + size]

    monkeypatch.setattr(assets, 'Cpk', FakeCpk)
    monkeypatch.setattr(assets, 'load_charset', lambda *_args: list(map(chr, range(128))))
    result = assets.index_language(tmp_path, tmp_path, 'en', ['ja'])
    assert [r['voice_status'] for r in result['records']] == ['voiced', 'unavailable', 'unknown', 'unvoiced']
    audio = result['records'][0]['audio']
    assert assets.extract_voice(tmp_path, audio, Path(), Path()) == adx()
    with pytest.raises(PreparationFailure):
        assets.extract_voice(tmp_path, {**audio, 'cue': 99}, Path(), Path())
    with pytest.raises(PreparationFailure):
        assets.extract_voice(tmp_path, {**audio, 'bank': '../other.acb'}, Path(), Path())
    assert result['missing_translation_locales'] == ['ja']
    (tmp_path / 'CPK/SOUND_E.CPK').unlink()
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    assert result['records'][0]['voice_status'] == 'unavailable'
    assert result['records'][-1]['voice_status'] == 'unvoiced'
    # An installed common archive can establish explicit silent cue zero even
    # with a missing dub. It must never lend its nonzero speech to that dub.
    (tmp_path / 'CPK/BASE.CPK').touch()
    files['event_data/message/e000/e001_002.bmd'] = message([voice_command(0) + b'Silent authored line.'])
    header, wavebank = awb(adx(True))
    files['sound/event/e001_002.acb'] = cue_bank(header, cue=0)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    assert result['records'][0]['voice_status'] == 'unvoiced'
    files['event_data/message/e000/e001_002.bmd'] = message([voice_command(4) + b'Absent dub.'])
    files['sound/event/e001_002.acb'] = cue_bank(header, cue=4)
    result = assets.index_language(tmp_path, tmp_path, 'en', [])
    assert result['records'][0]['voice_status'] == 'unavailable'


def test_decoder_uses_adx_and_verifies_authored_dimensions(tmp_path, monkeypatch):
    def decode(command, **_kwargs):
        assert Path(command[-1]).suffix == '.adx'
        with wave.open(command[command.index('-o') + 1], 'wb') as output:
            output.setparams((1, 2, 24000, 0, 'NONE', ''))
            output.writeframes(bytes(64))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    ref = dict(channels=1, rate=24000, samples=32)
    assets.decode_voice_source(adx(), ref, tmp_path / 'out.wav', Path('decoder'), tmp_path)
    assert (tmp_path / 'out.wav').is_file()
    with pytest.raises(PreparationFailure):
        assets.decode_voice_source(adx(), {**ref, 'samples': 33}, tmp_path / 'out.wav', Path('decoder'), tmp_path)
