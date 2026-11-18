"""The shared validated snapshot retains its bytes and atomic publication."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import pytest

from backend import language_worker, zzz_assets
from backend.game_data_protocol import GameDataError


def authored_snapshot(text):
    return {
        'format': 2, 'game': 'zzz', 'source_locale': 'ja',
        'records': [{
            'text_id': 'Synthetic_line', 'source_locale': 'ja', 'source_text': text,
            'texts': {'en': 'Authored translation', 'ja': text, 'zh-Hans': '合成字幕'},
            'english': 'Authored translation', 'chinese': '合成字幕',
            'audio_locale': 'ja', 'dialogue_kind': 'conversation', 'voice_status': 'unvoiced',
        }],
        'coverage': {'clock': -0.0, 'empty': [], 'missing': None},
    }


def write(payload, destination, *, check=None):
    language_worker.write_payload('zzz', payload, 'ja', ('zh-Hans', 'en'), destination, check=check)


def observe_stage(monkeypatch, write_chunk, *, closed=None):
    original_open = Path.open

    @contextmanager
    def observed(stream):
        class Observed:
            def write(self, chunk):
                return write_chunk(stream, chunk)

        with stream:
            yield Observed()
        if closed is not None:
            closed()

    def open_stage(path, mode='r', *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return observed(stream) if mode == 'wb' and path.name == 'download' else stream

    monkeypatch.setattr(Path, 'open', open_stage)


def test_streaming_write_matches_the_previous_snapshot_bytes(tmp_path):
    payload = authored_snapshot('台詞𠮷\n"引用"\\')
    destination = tmp_path / 'textmap.json'
    write(payload, destination)
    counts = {'voiced': 0, 'unvoiced': 1, 'unavailable': 0, 'unknown': 0}
    expected = authored_snapshot('台詞𠮷\n"引用"\\')
    expected['dialogue_inventory'] = {'voice_counts': counts, 'categories': {'conversation': counts}}
    expected['reader_revision'] = zzz_assets.LANGUAGE_INDEX_VERSION
    expected['targets_requested'] = ['en', 'zh-Hans']
    expected_bytes = json.dumps(expected, ensure_ascii=False).encode('utf-8')
    assert destination.read_bytes() == expected_bytes
    with destination.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').digest() == hashlib.sha256(expected_bytes).digest()


def test_large_multilingual_token_uses_bounded_utf8_writes(tmp_path, monkeypatch):
    writes = []

    def record_size(stream, chunk):
        writes.append(len(chunk))
        return stream.write(chunk)

    observe_stage(monkeypatch, record_size)
    payload = authored_snapshot(('台詞𠮷' * 53_000) + '\n"終わり"')
    destination = tmp_path / 'textmap.json'
    write(payload, destination)
    assert len(writes) > 8
    assert max(writes) <= 64 * 1024
    assert destination.read_bytes() == json.dumps(payload, ensure_ascii=False).encode('utf-8')


def test_partial_write_removes_only_the_new_temporary_file(tmp_path, monkeypatch):
    directory = tmp_path / 'library'
    directory.mkdir()
    destination = directory / 'textmap.json'
    destination.write_bytes(b'prior snapshot')
    unrelated = directory / 'other.json'
    unrelated.write_bytes(b'retained companion data')

    def partial_write(stream, chunk):
        return stream.write(chunk[:len(chunk) // 2])

    observe_stage(monkeypatch, partial_write)
    with pytest.raises(OSError, match='Incomplete prepared language snapshot write'):
        write(authored_snapshot('新しい台詞'), destination)
    assert destination.read_bytes() == b'prior snapshot'
    assert unrelated.read_bytes() == b'retained companion data'
    assert set(directory.iterdir()) == {destination, unrelated}


@pytest.mark.parametrize('cancel_after_close', [False, True])
def test_cancellation_preserves_previous_snapshot(tmp_path, monkeypatch, cancel_after_close):
    destination = tmp_path / 'textmap.json'
    destination.write_bytes(b'prior snapshot')
    cancelled = False

    def cancel():
        nonlocal cancelled
        cancelled = True

    def check():
        if cancelled:
            raise GameDataError('preparation_cancelled', 'Game preparation stopped.', 409)

    def write_chunk(stream, chunk):
        count = stream.write(chunk)
        if not cancel_after_close:
            cancel()
        return count

    observe_stage(monkeypatch, write_chunk, closed=cancel if cancel_after_close else None)
    with pytest.raises(GameDataError) as error:
        write(authored_snapshot('日本語𠮷' * 17_000), destination, check=check)
    assert error.value.code == 'preparation_cancelled'
    assert destination.read_bytes() == b'prior snapshot'
    assert list(tmp_path.iterdir()) == [destination]
