from backend.audio import AudioCaptureService
import numpy as np


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


def test_unrelated_later_voice_is_not_attached_to_silent_notice() -> None:
    assert AudioCaptureService._select_speech_group([(4.0, 5.0)], 1.3) is None
    assert AudioCaptureService._select_speech_group([(0.0, 0.3)], 3.0) is None


def test_voice_validation_does_not_fall_back_to_music_sensitive_detector() -> None:
    service = object.__new__(AudioCaptureService)
    service._voice_vad = None
    service._has_speech = lambda _: True
    samples = np.ones((48000, 2), dtype=np.float32) * 0.1
    trimmed, voiced = service._trim_to_voice(samples, 0.5)
    assert not voiced and trimmed.size == 0


def test_voice_validation_errors_fail_closed() -> None:
    class BrokenVad:
        def segments(self, *_):
            raise RuntimeError("model error")
    service = object.__new__(AudioCaptureService)
    service._voice_vad = BrokenVad()
    service.sample_rate = 48000
    service._has_speech = lambda _: True
    trimmed, voiced = service._trim_to_voice(np.ones((48000, 2)), 0.5)
    assert not voiced and trimmed.size == 0
    assert service._voice_validation_error == "model error"
