from backend.capture import StableMatchTracker


def test_stable_tracker_emits_once_per_visible_line() -> None:
    tracker = StableMatchTracker(required_frames=2)
    assert tracker.observe("line-a") is False
    assert tracker.observe("line-a") is True
    assert tracker.observe("line-a") is False
    assert tracker.observe("line-a") is False


def test_stable_tracker_allows_same_line_after_it_disappears() -> None:
    tracker = StableMatchTracker(required_frames=2, blank_reset_frames=2)
    tracker.observe("line-a")
    assert tracker.observe("line-a") is True
    tracker.observe(None)
    tracker.observe(None)
    assert tracker.observe("line-a") is False
    assert tracker.observe("line-a") is True


def test_single_blank_frame_does_not_duplicate_line() -> None:
    tracker = StableMatchTracker(required_frames=2, blank_reset_frames=2)
    tracker.observe("line-a")
    assert tracker.observe("line-a") is True
    tracker.observe(None)
    assert tracker.observe("line-a") is False
