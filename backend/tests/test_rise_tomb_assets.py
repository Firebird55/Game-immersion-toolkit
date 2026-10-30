"""Synthetic multiplexed dialogue: language isolation, paging and safe playback."""
from pathlib import Path
import struct
import wave

import pytest

from backend import rise_tomb_assets as assets
from backend.tests.test_tiger_archive import write_tiger


def fsb(label=b'synthetic', payload=b'encoded test audio'):
    header = struct.pack('<4s5I', b'FSB4', 1, 80, len(payload), 0x40000, 0).ljust(48, b'\0')
    sample = struct.pack('<H', 80) + label[:30].ljust(30, b'\0')
    return header + sample.ljust(80, b'\0') + payload


def mul(*, languages=(('0', 'Synthetic line.'), ('13', '合成的句子。')),
        channels=1, audio_data=None, extra_pages=()):
    header = bytearray(8192)
    struct.pack_into('<4i', header, 0, 44100, -1, 44100, channels)
    struct.pack_into('<i', header, 36, 1)
    for channel in range(channels):
        struct.pack_into('<f', header, 60 + channel * 4, 1.0)
        struct.pack_into('<f', header, 108 + channel * 4, 1.0 if channel == 0 else 0.0)
    packets = bytearray()
    cine_header = bytearray(108)
    struct.pack_into('<4sII', cine_header, 0, b'ENIC', 14, 100)
    for index, text_pairs in enumerate((languages, *extra_pages)):
        text = ''.join(f'{locale}\r{value}\r' for locale, value in text_pairs).encode()
        packet = (cine_header if index == 0 else b'') + struct.pack('<iii', len(text) + 8, index * 30, len(text)) + text
        packets.extend(struct.pack('<4I', 1, len(packet), 0, 0) + packet)
        packets.extend(b'\0' * (-len(packets) % 16))
    if channels:
        sound = b''
        for channel in range(channels):
            encoded = audio_data or fsb()
            sound += struct.pack('<4I', len(encoded), channel, 0, 0) + encoded
        packets.extend(struct.pack('<4I', 0, len(sound), 0, 0) + sound)
        packets.extend(b'\0' * (-len(packets) % 16))
    return bytes(header + packets)


def test_pages_and_original_fsb_binding(tmp_path):
    data = mul(languages=(('0', '[c1i0b1d2.5]Synthetic first page.'), ('13', '合成第一页。')),
               extra_pages=((('0', 'Synthetic second page.'), ('13', '合成第二页。')),))
    write_tiger(tmp_path, 'bigfile_ENGLISH.000.tiger', records=((42, 0xFFFF0001, data),))
    index = assets.index_language(tmp_path, tmp_path / 'cache', 'en', ['zh-Hans'])
    record, = index['records']
    assert record['voice_status'] == 'voiced'
    assert record['source_text'] == 'Synthetic first page. Synthetic second page.'
    assert record['ocr_english'] == ['Synthetic first page.', 'Synthetic second page.']
    assert assets.extract_voice(tmp_path, record['audio'], Path(), tmp_path) == fsb()
    with pytest.raises(ValueError, match='language'):
        assets.extract_voice(tmp_path, {**record['audio'], 'locale_name': 'zh-Hans'}, Path(), tmp_path)
    with pytest.raises(ValueError):
        assets.extract_voice(tmp_path, {**record['audio'], 'archive': '../other.tiger'}, Path(), tmp_path)


def test_missing_pack_never_uses_english_recording_or_implies_silence(tmp_path):
    write_tiger(tmp_path, 'bigfile_ENGLISH.000.tiger', records=((42, 0xFFFFC401, mul()),))
    row, = assets.index_language(tmp_path, tmp_path / 'cache', 'zh-Hans', ['en'])['records']
    assert row['voice_status'] == 'unavailable'
    assert row['audio'] is None
    assert row['source_text'] == '合成的句子。'


@pytest.mark.parametrize('locale', assets.SUPPORTED_LOCALES)
def test_every_voice_pack_uses_its_explicit_language_archive(tmp_path, locale):
    language = str(assets.TEXT_LOCALES[locale])
    write_tiger(tmp_path, f'bigfile_{assets.PACK_NAMES[locale]}.000.tiger',
                records=((42, 0xFFFF0000 | (1 << int(language)), mul(languages=((language, 'Synthetic localized line.'),))),))
    row, = assets.index_language(tmp_path, tmp_path, locale, [])['records']
    assert row['audio_locale'] == locale
    assert row['audio']['locale_name'] == locale
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == fsb()


def test_explicit_no_audio_and_incomplete_audio_are_distinct(tmp_path):
    write_tiger(tmp_path, 'bigfile_ENGLISH.000.tiger', records=(
        (1, 0xFFFF0001, mul(channels=0)), (2, 0xFFFF0001, mul(audio_data=b'incomplete'))))
    records = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert {record['voice_status'] for record in records} == {'unvoiced', 'unavailable'}


def test_multichannel_retains_every_stem_and_authored_mix(tmp_path):
    data = mul(channels=3)
    write_tiger(tmp_path, 'bigfile_ENGLISH.000.tiger', records=((42, 0xFFFF0001, data),))
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert row['dialogue_kind'] == 'cinematic'
    assert row['audio']['decoder_format'] == 'mul'
    assert row['audio']['channel_mix'] == [[1.0, 1.0], [1.0, 0.0], [1.0, 0.0]]
    assert assets.extract_voice(tmp_path, row['audio'], Path(), tmp_path) == data
    with pytest.raises(ValueError, match='mix'):
        assets.extract_voice(tmp_path, {**row['audio'], 'channel_mix': [[1, 1]]}, Path(), tmp_path)


def test_simultaneous_captions_are_retained_and_bad_packets_rejected():
    result = assets.read_mul(mul(languages=(('0', 'One speaker.'), ('0', 'Second speaker.'))))
    assert result['pages'][0]['texts']['en'] == 'One speaker. Second speaker.'
    data = bytearray(mul())
    struct.pack_into('<I', data, 8196, 0x7FFFFFFF)
    with pytest.raises(ValueError):
        assets.read_mul(bytes(data))


def test_shared_frame_cuts_preserve_staggered_language_pages():
    stream = {'duration_ms': 10000, 'pages': [
        {'frame': 0, 'texts': {'en': 'One.', 'zh-Hans': '一。'}},
        {'frame': 30, 'texts': {'en': 'Two.'}},
        {'frame': 32, 'texts': {'zh-Hans': '二。'}},
        {'frame': 90, 'texts': {'en': 'Three.', 'zh-Hans': '三。'}}]}
    groups = list(assets._subtitle_groups(stream, {'en', 'zh-Hans'}, 'en'))
    assert groups == [(0, 3000, {'en': ['One.', 'Two.'], 'zh-Hans': ['一。', '二。']}, True),
                      (90, 10000, {'en': ['Three.'], 'zh-Hans': ['三。']}, True)]
    data = bytearray(mul())
    struct.pack_into('<f', data, 60, float('nan'))
    with pytest.raises(ValueError, match='mix'):
        assets.read_mul(bytes(data))


def test_locals_bounds_and_unknown_voice_inventory(tmp_path):
    text = b'Synthetic readable\0'
    locals_data = struct.pack('<3IQ', 0, 0, 1, 20) + text
    write_tiger(tmp_path, records=((assets._LOCALS_HASH, 0xFFFF0001, locals_data),))
    row, = assets.index_language(tmp_path, tmp_path, 'en', [])['records']
    assert row['voice_status'] == 'unknown'
    assert row['dialogue_kind'] == 'unclassified_localization'
    with pytest.raises(ValueError):
        assets.read_locals(struct.pack('<3IQ', 0, 0, 1, 0xFFFFFFFF))


def test_install_validation_and_fingerprint_change(tmp_path, monkeypatch):
    write_tiger(tmp_path)
    (tmp_path / 'ROTTR.exe').write_bytes(b'synthetic executable marker')
    assert assets.discover_install([tmp_path]) == tmp_path
    write_tiger(tmp_path, 'bigfile_ENGLISH.000.tiger', identity=2, records=((42, 0xFFFF0001, mul()),))
    stamps = iter(('before', 'after'))
    monkeypatch.setattr(assets, 'fingerprint', lambda _: next(stamps))
    with pytest.raises(ValueError, match='changed'):
        assets.index_language(tmp_path, tmp_path, 'en', [])


def _large_mul():
    payload = bytearray(fsb())
    struct.pack_into('<I', payload, 80, 4)
    struct.pack_into('<I', payload, 100, 44100)
    struct.pack_into('<H', payload, 110, 1)
    data = bytearray(mul(channels=9, audio_data=bytes(payload)))
    struct.pack_into('<I', data, 8, 4)
    return bytes(data)


def test_large_mul_interleaves_every_original_channel_without_padding(tmp_path, monkeypatch):
    # Make the shared budget independent of the runner clock's float rounding.
    clock = [0.0]
    monkeypatch.setattr(assets.time, 'monotonic', lambda: clock[0])
    data = _large_mul()
    stream = assets.read_mul(data)
    audio = {'decoder_format': 'mul', 'channel_mix': stream['channel_mix']}
    calls = []
    def decode(command, **options):
        calls.append(options['timeout'])
        clock[0] += 1
        index = int(Path(command[-1]).stem.rsplit('-', 1)[1])
        with wave.open(command[3], 'wb') as handle:
            handle.setparams((1, 2, 44100, 4, 'NONE', 'not compressed'))
            handle.writeframes(struct.pack('<4h', *([index + 1] * 4)))
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    assets.decode_voice_source(data, audio, tmp_path / 'out.wav', Path('decoder'), tmp_path)
    with wave.open(str(tmp_path / 'out.wav')) as handle:
        assert handle.getnchannels() == 9
        assert handle.getnframes() == 4
        assert struct.unpack('<36h', handle.readframes(4)) == tuple(range(1, 10)) * 4
    assert calls == list(range(90, 81, -1))


def test_large_mul_rejects_decoder_duration_disagreement(tmp_path, monkeypatch):
    data = _large_mul()
    audio = {'decoder_format': 'mul', 'channel_mix': assets.read_mul(data)['channel_mix']}
    def decode(command, **_options):
        with wave.open(command[3], 'wb') as handle:
            handle.setparams((1, 2, 44100, 3, 'NONE', 'not compressed'))
            handle.writeframes(b'\0' * 6)
    monkeypatch.setattr(assets.subprocess, 'run', decode)
    with pytest.raises(ValueError, match='differ'):
        assets.decode_voice_source(data, audio, tmp_path / 'out.wav', Path('decoder'), tmp_path)


def test_large_mul_shares_one_decode_deadline(tmp_path, monkeypatch):
    data = _large_mul()
    audio = {'decoder_format': 'mul', 'channel_mix': assets.read_mul(data)['channel_mix']}
    ticks = iter((0, 91))
    monkeypatch.setattr(assets.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(ValueError, match='time bound'):
        assets.decode_voice_source(data, audio, tmp_path / 'out.wav', Path('decoder'), tmp_path)


def test_cheap_pack_probe_distinguishes_base_and_partial_dlc(tmp_path):
    assert assets.probe_voice_pack(tmp_path, 'en') == 'missing'
    assert assets.probe_voice_pack(tmp_path, 'nl') == 'unknown'
    write_tiger(tmp_path, 'bigfile.dlc.mode.bloodties.000_ENGLISH.000.tiger')
    assert assets.probe_voice_pack(tmp_path, 'en') == 'incomplete'
    write_tiger(tmp_path, 'bigfile_ENGLISH.000.tiger', identity=2)
    assert assets.probe_voice_pack(tmp_path, 'en') == 'present'
    (tmp_path / 'bigfile_ENGLISH.000.tiger').write_bytes(b'partial launcher download')
    assert assets.probe_voice_pack(tmp_path, 'en') == 'incomplete'
