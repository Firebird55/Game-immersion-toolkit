from backend.audio import AudioCaptureService


def test_speech_group_nearest_subtitle_boundary_is_selected() -> None:
    segments = [(0.8, 1.5), (1.8, 4.4), (8.0, 9.0)]
    assert AudioCaptureService._select_speech_group(segments, 4.0) == (0.8, 4.4)
    assert AudioCaptureService._select_speech_group(segments, 8.5) == (8.0, 9.0)
    assert AudioCaptureService._select_speech_group([], 4.0) is None


def test_back_to_back_clips_use_a_tight_shared_boundary(tmp_path) -> None:
    service = AudioCaptureService(tmp_path)
    callback = lambda *_: None
    service.schedule_clip(1, 100.0, callback)
    service.schedule_clip(2, 102.0, callback)
    first, second = service._pending
    assert first.end == 101.65
    assert second.start == 101.25
    assert second.start > 100.0
