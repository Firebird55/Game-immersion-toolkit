import time


class VoiceActivity:
    """A separate event from row edits, favorite toggles, and browser playback."""
    def __init__(self):
        self.latest = None

    def record(self, kind, phase):
        if kind == 'agents' and phase != 'agents':
            return None
        if kind == 'history' and phase in {'agents','stopped','waiting_for_game','excluded_screen'}:
            return None
        previous = self.latest['occurred_at'] if self.latest else 0
        self.latest = {'kind': kind, 'occurred_at': max(time.time_ns()//1_000_000, previous+1)}
        return self.latest
