from backend.audio import AudioCaptureService


def test_all_speech_segments_in_a_subtitle_window_are_retained() -> None:
    segments = [(0.8, 1.5), (1.8, 4.4), (8.0, 9.0)]
    assert AudioCaptureService._select_speech_group(segments, 4.0) == (0.8, 9.0)
    assert AudioCaptureService._select_speech_group([], 4.0) is None
