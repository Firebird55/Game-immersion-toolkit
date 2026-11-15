"""Synthetic CRI audio and metadata: no game media, real format keys or network."""
import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_movie_audio as audio, starrail_movie_metadata as metadata
from backend.local_voice import _source_suffix
# Reuse the existing typed UTF fixture instead of introducing another writer.
from backend.tests.test_persona5_assets import table


def chunk(kind, track, data, content=0):
    header = bytearray(32)
    header[:4] = kind
    struct.pack_into('>I', header, 4, 24 + len(data))
    header[9], header[12], header[15] = 24, track, content
    return bytes(header) + data


def adx(marker=3):
    header = bytearray(32)
    header[:4] = b'\x80\x00\x00\x1c'
    struct.pack_into('>BBBBIIH', header, 4, 3, 18, 4, 2, 48000, 2048, 500)
    header[18] = 4
    header[26:32] = b'(c)CRI'
    return bytes(header) + (b'\0\x02' + bytes([marker]) * 16) * 128 + b'\x80\x01' + bytes(16)


def movie(*, masked=True, duplicate=False):
    en, ja = adx(3), adx(5)
    rows = [{'stmid': int.from_bytes(b'@SFA', 'big'), 'chno': ch, 'filename': f'mix_{dub}#{ch:02}.sfa'}
            for dub, ch in [('EN', 7), ('JP', 2)]]
    if duplicate:
        rows.append({'stmid': int.from_bytes(b'@SFA', 'big'), 'chno': 5, 'filename': 'other_EN#05.sfa'})
    result = chunk(b'CRID', 3, table([('stmid', 4), ('chno', 2), ('filename', 10)], rows), 1)
    # Independent fixed reference vector for the deliberately synthetic key 7.
    mask = [248, 85, 255, 82, 6, 85, 158, 67, 255, 85, 0, 82, 248, 85, 52, 67,
            255, 85, 0, 82, 56, 85, 109, 67, 7, 85, 228, 82, 223, 85, 126, 67]
    for number, track in [(7, en), (2, ja)]:
        for start, end in [(0, 501), (501, len(track))]:
            packet = track[start:end]
            if masked:
                packet = packet[:320] + bytes(value ^ mask[i % 32] for i, value in enumerate(packet[320:]))
            result += chunk(b'@SFA', number, packet)
    return result, en, ja


def asset(body, name='Scene.usm'):
    reads = []
    def read(directory, start, size):
        reads.append((start, size))
        return body[start:start + size]
    return SimpleNamespace(name=name, size=len(body), digest=hashlib.md5(body).hexdigest(), read=read, reads=reads)


def catalog(a, *, revision='1' * 40, key=7, previous=None, variants=None):
    history = {'path/' + a.name: {'versions': [*(previous or []), {'version': '1.1.0', 'md5': a.digest, 'size': a.size}]}}
    return metadata.Catalog(revision, 'a' * 64, history, {a.name[:-4]: f'{key:016x}'}, variants or {})


@pytest.mark.parametrize('masked', [False, True])
def test_reads_named_dub_with_packet_reset_and_complete_samples(tmp_path, masked):
    body, en, ja = movie(masked=masked)
    path = tmp_path / 'movie.usm'
    path.write_bytes(body)
    key = 7 if masked else 0
    selected = audio.read_track(path, 'en', key)
    assert selected.data == en and selected.samples == 2048 and selected.channels == 2 and selected.rate == 48000
    assert audio.read_track(path, 'ja', key).data == ja
    assert _source_suffix(selected.data, {'movie': 'Scene.usm'}, 'starrail') == '.adx'
    with pytest.raises(ValueError):
        audio.read_track(path, 'ko', key)
    path.write_bytes(movie(masked=masked, duplicate=True)[0])
    with pytest.raises(ValueError):
        audio.read_track(path, 'en', key)


def test_refuses_truncated_or_premature_eof_instead_of_accepting_decoder_success(tmp_path):
    body, en, _ = movie()
    path = tmp_path / 'movie.usm'
    path.write_bytes(body[:-5])
    with pytest.raises(ValueError):
        audio.read_track(path, 'en', 7)
    broken = bytearray(en)
    broken[32 + 18 * 6] = 128
    with pytest.raises(ValueError):
        audio._adx(broken)
    with pytest.raises(ValueError):
        audio._adx(en[:-40])


def test_changed_movie_needs_exact_metadata_and_historical_key_selection():
    body, _, _ = movie()
    before = asset(body)
    old = catalog(before)
    changed = asset(body + b'new generation')
    with pytest.raises(ValueError):
        old.key_for(changed)
    previous = [{'version': '1.0.0', 'md5': before.digest, 'size': before.size}]
    new = catalog(changed, key=9, previous=previous)
    assert new.key_for(changed) == 9 and old.key_for(before) == 7
    with pytest.raises(ValueError):
        new.key_for(before)
    new = catalog(changed, key=9, previous=previous, variants={'Scene': {'1.0.0': f'{7:016x}', '1.1.0': f'{9:016x}'}})
    assert new.key_for(before) == 7 and new.key_for(changed) == 9


def test_verified_original_audio_replays_offline_and_failed_update_keeps_it(tmp_path):
    body, en, ja = movie()
    before = asset(body)
    source = catalog(before)
    assert audio.recording(tmp_path, before, 'en', source).data == en
    before.reads.clear()
    assert audio.recording(tmp_path, before, 'en', source, hashlib.sha256(en).hexdigest()).data == en
    assert not before.reads
    assert audio.recording(tmp_path, before, 'ja', source).data == ja
    changed = asset(body)
    changed.digest = 'b' * 32
    with pytest.raises(ValueError):
        audio.recording(tmp_path, changed, 'en', catalog(changed))
    before.read = lambda *_: pytest.fail('Old recording must remain playable offline')
    assert audio.recording(tmp_path, before, 'en', source).data == en


def test_pinned_metadata_cache_validates_complete_digest_and_never_executes_data(tmp_path, monkeypatch):
    body, _, _ = movie()
    a = asset(body)
    c = catalog(a)
    documents = dict(zip(metadata.FILES, map(json.dumps, [c.history, c.keys, c.variants])))
    monkeypatch.setattr(metadata, 'latest_revision', lambda: c.revision)
    monkeypatch.setattr(metadata, 'download', lambda url, **_: documents[url.rsplit('/', 1)[1]].encode())
    first = metadata.load(tmp_path)
    assert first.key_for(a) == 7
    monkeypatch.setattr(metadata, 'download', lambda *_a, **_k: pytest.fail('Pinned offline metadata read'))
    assert metadata.load(tmp_path, first.revision, first.digest).key_for(a) == 7
    with pytest.raises(ValueError):
        metadata.load(tmp_path, first.revision, 'b' * 64)
