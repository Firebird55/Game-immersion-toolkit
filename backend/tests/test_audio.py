from backend.audio import AudioCaptureService
import numpy as np
import threading
from collections import deque


NANSON = "我来交涉吧，蕾，我曾有幸查阅过面前这位绳匠的资料。哲先生你好，我叫南升，看起来我们殊途同归，都在寻找这「迷宫萝卜」呢…"


def adaptive_service():
    service = object.__new__(AudioCaptureService)
    service._pending = []
    service._lock = threading.RLock()
    service._last_committed_end = float("-inf")
    service._voice_validation_error = None
    service.sample_rate = 100
    return service


def test_speech_group_nearest_subtitle_boundary_is_selected() -> None:
    segments = [(0.8, 1.5), (1.8, 4.4), (8.0, 9.0)]
    assert AudioCaptureService._select_speech_group(segments, 4.0) == (0.8, 4.4)
    assert AudioCaptureService._select_speech_group(segments, 8.5) == (8.0, 9.0)
    assert AudioCaptureService._select_speech_group([], 4.0) is None


def test_back_to_back_clips_have_no_shared_audio() -> None:
    service = adaptive_service()
    callback = lambda *_: None
    service.schedule_clip(1, 100.0, callback)
    service.schedule_clip(2, 102.0, callback)
    first, second = service._pending
    assert first.end == 101.4
    assert second.start == first.end
    assert first.forced_end


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


def test_multi_sentence_line_keeps_all_phrases_and_internal_pauses() -> None:
    spans = [(1.0, 2.7), (3.6, 7.0), (8.2, 10.4), (11.6, 18.5)]
    assert AudioCaptureService._utterance_bounds(spans, 1.5) == (1.0, 18.5)
    assert AudioCaptureService._utterance_bounds([(5.0, 6.0)], 1.0) is None


def test_long_line_is_not_capped_at_five_seconds() -> None:
    service = adaptive_service()
    service.schedule_clip(917, 100.7, lambda *_: None, observed_at=100.0, chinese=NANSON)
    clip = service._pending[0]
    assert clip.start == 98.0
    assert clip.end > 120.0
    clip.voice_end = 105.5
    assert not service._clip_complete(clip, 106.0)
    clip.voice_end = 117.0
    assert not service._clip_complete(clip, 118.0)
    assert service._clip_complete(clip, 119.1)


def test_typewriter_upgrade_extends_budget_without_restarting_clip() -> None:
    service = adaptive_service()
    service.schedule_clip(1, 100.5, lambda *_: None, observed_at=100.0, chinese="我来交涉吧。")
    start = service._pending[0].start
    service.schedule_clip(1, 102.0, lambda *_: None, observed_at=101.0, chinese=NANSON)
    assert len(service._pending) == 1
    assert service._pending[0].start == start
    assert service._pending[0].end > 120


def test_adaptive_replay_waits_for_last_phrase_and_trims_music(tmp_path) -> None:
    service = adaptive_service()
    service.output_dir = tmp_path
    service.channels = 2
    # Seconds relative to the two-second pre-roll; includes sentence pauses.
    spans = [(2.0, 3.7), (4.6, 8.0), (9.2, 11.4), (12.6, 19.5)]
    class ScriptedVad:
        def segments(self, samples, sample_rate):
            duration = len(samples) / sample_rate
            return [(start, min(end, duration)) for start, end in spans if start + 0.2 < duration]
    service._voice_vad = ScriptedVad()
    service._samples_between = lambda start, end: np.zeros((max(0, round((end-start)*100)), 2))
    saved = []
    service._finalize = lambda clip: saved.append((clip.voice_start, clip.voice_end))
    service.schedule_clip(917, 100.5, lambda *_: None, observed_at=100.0, chinese=NANSON)
    for now in (101.0, 103.0, 105.0, 109.0, 111.0, 114.0, 118.0):
        service._process_pending(now)
        assert not saved, f"Premature clip at {now}"
    service._process_pending(120.0)
    assert saved == [(100.0, 117.5)]
    assert not service._pending


def test_next_subtitle_closes_long_recording_at_first_seen_time() -> None:
    service = adaptive_service()
    service.schedule_clip(1, 101.0, lambda *_: None, observed_at=100.0, chinese=NANSON)
    service.schedule_clip(2, 113.0, lambda *_: None, observed_at=112.0, chinese="你好。")
    first, second = service._pending
    assert first.end == second.start == 111.9
    assert service._clip_complete(first, 113.0)


def test_silent_candidate_times_out_without_waiting_for_long_text() -> None:
    service = adaptive_service()
    service.schedule_clip(1, 100.0, lambda *_: None, observed_at=100.0, chinese=NANSON)
    assert service._clip_complete(service._pending[0], 103.0)


def test_recording_loop_submits_analysis_without_running_it() -> None:
    service = adaptive_service()
    service._chunks = deque()
    service._analysis_future = None
    service._last_analysis_at = 0.0
    submitted = []
    class Executor:
        def submit(self, function, now):
            submitted.append(function.__name__)
            return None
    service._analysis_executor = Executor()
    service.schedule_clip(1, 100.0, lambda *_: None, chinese=NANSON)
    service._append_samples(np.zeros((25, 2)))
    assert submitted == ["_process_pending"]
    assert len(service._chunks) == 1
    assert len(service._pending) == 1


def test_final_clip_has_small_padding_not_trailing_music() -> None:
    service = adaptive_service()
    service.schedule_clip(1, 100.5, lambda *_: None, observed_at=100.0, chinese=NANSON)
    clip = service._pending[0]
    clip.voice_start, clip.voice_end = 100.0, 117.5
    requested = []
    def samples_between(start, end):
        requested.append((start, end))
        return np.empty((0, 2))
    service._samples_between = samples_between
    service._finalize(clip)
    assert requested == [(99.8, 117.75)]
