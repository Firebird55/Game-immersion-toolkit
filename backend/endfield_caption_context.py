"""Use a confirmed immediately preceding Endfield radio or film caption."""


class EndfieldCaptionContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.anchor = self.candidate = None
        self.count = 0
        self.last_seen = None

    def observe(self, index, groups, visible, *, channel, scope, now, stable_frames):
        if scope != self.scope or self.last_seen is None or not 0 <= now - self.last_seen <= 3:
            self.reset()
            self.scope = scope
        kind = 'radio' if channel == 'dialogue' else 'cinematic'
        visible = [hit for hit in visible if hit is not None]
        matches = {hit.text_id: hit for hit in visible if hit.kind == 'exact'
                   and hit.dialogue_kind == kind and hit.voice_status == 'voiced'}
        resolved = {}
        if self.anchor:
            for group in groups:
                hit = index.match_lines([group], exact_only=True, channel=channel, previous_text_id=self.anchor)
                if hit and hit.dialogue_kind == kind and hit.voice_status == 'voiced':
                    resolved[hit.text_id] = hit
        matches.update(resolved)
        if len(matches) != 1 or any(hit.text_id not in matches for hit in visible):
            if groups or visible or self.candidate != self.anchor:
                self.reset()
            return None
        identity, hit = next(iter(matches.items()))
        if self.candidate == identity:
            self.count += 1
        else:
            self.candidate, self.count = identity, 1
            if identity not in resolved:
                self.anchor = None
        self.last_seen = now
        if self.count >= max(2, stable_frames):
            # Keep the predecessor for the whole visible run of a contextual
            # occurrence. Identical successive subtitles have no observable cut.
            if identity not in resolved:
                self.anchor = identity
        return hit if identity in resolved else None
