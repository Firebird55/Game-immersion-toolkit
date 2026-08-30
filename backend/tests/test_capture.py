from backend.capture import CaptureService, StableMatchTracker


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


def test_phone_screen_is_explicitly_excluded() -> None:
    lines = ["Knock Knock", "Anton", "[Completed] The prototype", "REPLY", "Daily Info"]
    assert CaptureService._is_phone_screen(lines) is True
    assert CaptureService._is_phone_screen(
        ["Fairy", "Oh, thanks!", "Daily Info - Latest messages displayed above -"]
    ) is True
    assert CaptureService._is_phone_screen(["Anby", "Stay close to me."]) is False


def test_same_textmap_id_has_emission_cooldown() -> None:
    service = object.__new__(CaptureService)
    service._last_emitted_at = {}
    service._last_emitted_key_by_channel = {}
    assert service._can_emit("dialogue\0line-a", 100.0) is True
    assert service._can_emit("dialogue\0line-a", 110.0) is False
    assert service._can_emit("cinematic\0line-a", 120.0) is False
    assert service._can_emit("dialogue\0line-b", 150.0) is True
    assert service._can_emit("dialogue\0line-a", 161.0) is True


def test_screen_header_classifier_excludes_history_interfaces() -> None:
    assert CaptureService._classify_screen_header(["51 FPS", "Story Recap"]) == "story_recap"
    assert CaptureService._classify_screen_header(["Knock Knock", "Anton"]) == "phone"
    assert CaptureService._classify_screen_header(["NEW!", "Story Commission", "70%"]) == "hdd"
    assert CaptureService._classify_screen_header(["Belobog Industries", "Ben"]) is None
