"""Use a confirmed immediately preceding authored caption to distinguish a recording."""


class EndfieldCaptionContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.anchor = self.candidate = None
        self.candidate_predecessor = None
        self.count = 0
        self.last_seen = None

    def observe(self, index, groups, visible, *, channel, scope, now, stable_frames, kind=None):
        if scope != self.scope or self.last_seen is None or not 0 <= now - self.last_seen <= 3:
            self.reset()
            self.scope = scope
        kind = kind or ('radio' if channel == 'dialogue' else 'cinematic')
        visible = [hit for hit in visible if hit is not None]
        matches = {hit.text_id: hit for hit in visible if hit.kind == 'exact'
                   and hit.dialogue_kind == kind and hit.voice_status == 'voiced'}
        resolved = {}
        for group in groups:
            hit = None
            if self.candidate_predecessor:
                # A repeated observation can still be the same occurrence even
                # when its authored successor has exactly the same subtitle.
                repeat = index.match_lines([group], exact_only=True, channel=channel,
                                           previous_text_id=self.candidate_predecessor)
                if repeat and repeat.text_id == self.candidate:
                    hit = repeat
            if hit is None and self.anchor:
                hit = index.match_lines([group], exact_only=True, channel=channel, previous_text_id=self.anchor)
            if hit and hit.dialogue_kind == kind and hit.voice_status == 'voiced':
                resolved[hit.text_id] = hit
        matches.update(resolved)
        if len(matches) != 1 or any(hit.text_id not in matches for hit in visible):
            if groups or visible or self.candidate_predecessor or self.candidate != self.anchor:
                self.reset()
            return None
        identity, hit = next(iter(matches.items()))
        if self.candidate == identity:
            self.count += 1
        else:
            self.candidate_predecessor = self.anchor if identity in resolved else None
            self.candidate, self.count = identity, 1
            self.anchor = None
        self.last_seen = now
        if self.count >= max(2, stable_frames):
            self.anchor = identity
        return hit if identity in resolved else None
