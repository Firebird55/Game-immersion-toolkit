"""Platform-independent capture confirmation used by every toolkit host."""


class StableMatchTracker:
    def __init__(self, required_frames: int = 2, blank_reset_frames: int = 2):
        self.required_frames = required_frames
        self.blank_reset_frames = blank_reset_frames
        self.candidate: str | None = None
        self.count = 0
        self.blank_count = 0
        self.emitted = False

    def configure(self, required_frames: int) -> None:
        self.required_frames = max(1, required_frames)

    def observe(self, key: str | None) -> bool:
        if key is None:
            self.blank_count += 1
            if self.blank_count >= self.blank_reset_frames:
                self.candidate = None
                self.count = 0
                self.emitted = False
            return False
        self.blank_count = 0
        if key != self.candidate:
            self.candidate = key
            self.count = 1
            self.emitted = False
        else:
            self.count += 1
        if self.count >= self.required_frames and not self.emitted:
            self.emitted = True
            return True
        return False


def capture_match_eligible(match, *, capture_unvoiced, capture_missing_audio, mapped_voice):
    """Keep explicit silent/missing opt-ins separate from original voice mapping."""
    if match is None:
        return False
    if match.voice_status == 'unvoiced':
        return capture_unvoiced and match.kind == 'exact'
    if match.voice_status in {'unknown', 'unavailable'} and match.text_capture_verified:
        return capture_missing_audio and match.kind == 'exact'
    return mapped_voice(match)
