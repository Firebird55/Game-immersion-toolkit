import pytest

from backend.prepared_library import write_prepared_library
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_audio_omission import TEXT, record, snapshot


@pytest.mark.parametrize('status', ['voiced', 'unknown'])
def test_real_writer_import_capture_sqlite_reopen_never_fetches_or_relabels_audio(tmp_path, status):
    payload = snapshot([record(status=status)])
    archive = tmp_path / 'authored-text.zip'
    write_prepared_library(payload, archive, {})
    session = PreparedCaptureSession(tmp_path / 'profile')
    session.import_library(archive)
    generation = session.start()
    assert session.observe(generation, 1, [TEXT], now=1) == []
    lines = session.observe(generation, 2, [TEXT], now=1.1)
    assert len(lines) == 1 and lines[0]['voice_status'] == status
    assert lines[0]['audio_omitted_by_request'] is True and not lines[0]['has_audio']
    assert session.audio_path(lines[0]['id']) is None
    assert session.history.purge_unvoiced() == []
    reopened = PreparedCaptureSession(tmp_path / 'profile')
    stored = reopened.history.get(lines[0]['id'])
    assert stored.is_requested_text_only and stored.voice_status == status and not stored.has_audio
    assert stored.source_voice_binding == payload['records'][0]['source_voice_binding']
