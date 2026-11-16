"""Use a confirmed immediately preceding authored caption to distinguish a recording."""


class EndfieldCaptionContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.anchor = self.candidate = None
        self.candidate_predecessor = None
        self.possible = frozenset()
        self.possible_count = 0
        self.count = 0
        self.last_seen = None

    def observe(self, index, groups, visible, *, channel, scope, now, stable_frames, kind=None,
                prefer_authored_occurrence=False):
        if scope != self.scope or self.last_seen is None or not 0 <= now - self.last_seen <= 3:
            self.reset()
            self.scope = scope
        kind = kind or ('radio' if channel == 'dialogue' else 'cinematic')
        visible = [hit for hit in visible if hit is not None]
        def eligible(hit):
            return hit.voice_status == 'voiced' or (
                getattr(index, 'capture_unvoiced', False) and hit.voice_status == 'unvoiced') or (
                getattr(index, 'capture_missing_audio', False) and hit.is_verified_missing_audio)
        mission_text = groups[0] if kind == 'conversation' and getattr(index, 'game', None) == 'endfield' and len(groups) == 1 else None
        matches = {hit.text_id: hit for hit in visible if hit.kind == 'exact'
                   and hit.dialogue_kind == kind and eligible(hit)}
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
            if (hit is None and mission_text and self.possible_count >= max(2, stable_frames)
                    and not self.possible.intersection(index.mission_anchor_ids(mission_text))):
                # The preceding subtitle can be ambiguous. Only a unique
                # consecutive pair may select the current line's recording.
                found = {}
                for previous in self.possible:
                    choice = index.match_lines([group], exact_only=True, channel=channel, previous_text_id=previous)
                    if choice and choice.dialogue_kind == kind and eligible(choice):
                        found[choice.text_id] = (choice, previous)
                if len(found) == 1:
                    hit, self.anchor = next(iter(found.values()))
            if hit and hit.dialogue_kind == kind and eligible(hit):
                resolved[hit.text_id] = hit
        if prefer_authored_occurrence and len(resolved) == 1:
            preferred = next(iter(resolved.values()))
            # The index coalesces identical source/voice/translation identities
            # to their first row. A single-caption presentation can retain its
            # actual later occurrence when the authored observed pair proves it.
            # Every other complete source field must still agree exactly,
            # including audio, all translations, branch, kind and capture scope.
            equivalent_rows = getattr(index, 'equivalent_caption_occurrence', None)
            equivalent = {hit.text_id for hit in visible if hit.kind == 'exact'
                          and hit.source_ocr == preferred.source_ocr and equivalent_rows
                          and equivalent_rows(hit, preferred)}
            for identity in equivalent:
                matches.pop(identity, None)
            visible = [hit for hit in visible if hit.text_id not in equivalent]
        matches.update(resolved)
        if not matches and not visible and mission_text and (possible := index.mission_anchor_ids(mission_text)):
            count = self.possible_count + 1 if self.possible == possible else 1
            self.reset()
            self.scope, self.last_seen = scope, now
            self.possible, self.possible_count = possible, count
            return None
        self.possible, self.possible_count = frozenset(), 0
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
