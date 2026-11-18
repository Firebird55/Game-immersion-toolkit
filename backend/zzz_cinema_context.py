"""Forward-only authored cinema context, guarded by actual fresh capture frames."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from .languages import normalize_text, resolve_locale, study_language
from .models import TextMatch
from .textmaps import display_text


@dataclass(frozen=True)
class CinemaFrame:
    sequence: int
    started: float
    finished: float
    trusted_capture: bool

    def valid(self, now):
        return (type(self.sequence) is int and self.sequence > 0 and self.trusted_capture is True
            and all(type(value) in (int, float) and math.isfinite(value) for value in (self.started, self.finished, now))
            and 0 <= self.started <= self.finished <= now and self.finished - self.started <= .25
            and now - self.finished <= 1.)


def proxy_source_scope(index, owner, configured):
    generation = getattr(index, 'publisher_generation', None)
    request = getattr(index, 'publisher_request_sha256', None)
    if not generation or not request:
        return None
    return hashlib.sha256(json.dumps([owner, generation, request, index.source_locale,
        index.target_locale, configured], separators=(',', ':')).encode()).hexdigest()


def _player_voice(row):
    # Ordinary sibling voices also occur in NPC dialogue.
    if row.get('text_binding_unresolved') or row.get('dialogue_kind') in {'choice', 'narration'}:
        return None
    player = row.get('player_voice')
    if player in {'male', 'female'}:
        return player
    event = (row.get('audio') or {}).get('event') or ''
    match = re.search(r'_Bangboo(Wise|Belle)(?:_|$)', event, re.I)
    if match:
        return 'male' if match[1].casefold() == 'wise' else 'female'
    return None


class ProxyEvidence:
    """Keep fresh protagonist confirmation separate from the previous capture's hint."""
    def __init__(self):
        self.prepare(None, None)

    def prepare(self, scope, previous):
        self.scope = scope
        self.previous = previous if previous in {'male', 'female'} else None
        self.clear()

    def clear(self):
        self.confirmed = self.pending = self.frame = None
        self.count = 0
        self.conflict = False

    def voice(self, configured):
        if self.conflict:
            return None
        return self.confirmed or (configured if configured in {'male', 'female'} else self.previous)

    def observe(self, index, groups, *, frame, now, stable_frames):
        if not isinstance(frame, CinemaFrame) or not frame.valid(now):
            self.clear()
            return None
        if self.frame and (frame.sequence != self.frame.sequence + 1
                or not 0 <= frame.started - self.frame.finished <= 1.):
            self.clear()
        self.frame = frame
        tokens = set()
        compiled = getattr(index, '_zzz_cinema_occurrences', None)
        with index.lock:
            for caption in groups:
                minimum = 6 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', caption) else 12
                for locale, lookup in index._lookup.items():
                    key = normalize_text(display_text(caption), locale)
                    if len(key) < minimum or key in index._full_frame_veto.get(locale, ()):
                        continue
                    rows = (*lookup.get(key, ()), *index._unvoiced_lookup.get(locale, {}).get(key, ()),
                            *index._missing_audio_lookup.get(locale, {}).get(key, ()))
                    exact = {(row['text_id'], _player_voice(row)) for row in rows
                        if normalize_text(row['texts'].get(locale, ''), locale) == key}
                    if len(exact) != 1 or len({row['text_id'] for row in rows}) != 1:
                        continue
                    identity, player = next(iter(exact))
                    if player is None and compiled:
                        anchors = compiled['anchors'].get((locale, key), ())
                        if len(anchors) == 1:
                            variant, ordinal = anchors[0]
                            branch = compiled['variants'][variant]
                            if branch['captions'][ordinal]['text_id'] == identity:
                                player = branch['player']
                    if player:
                        tokens.add((identity, player))
        players = {player for _, player in tokens}
        if len(players) > 1:
            self.confirmed = self.pending = self.previous = None
            self.count, self.conflict = 0, True
            return None
        token = min(tokens) if tokens else None
        self.count = self.count + 1 if token and token == self.pending else 1
        self.pending = token
        if token:
            player = token[1]
            if (self.confirmed or self.previous) not in (None, player):
                self.confirmed = self.previous = None
                self.conflict = True
            if self.count >= max(2, stable_frames):
                self.confirmed, self.conflict = player, False
                return player
        return None


class CinemaContext:
    """An anchor certifies only its continuous capture segment and authored clock.

    An independently matched branch or a previously confirmed player can
    select a verified performance. Frame loss or incompatible clocks end the
    conditional path before another recording can win.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.variant = None
        self.ordinal = -1
        self.origin = None
        self.last_frame = None
        self.pending = None
        self.count = 0
        self.accepted = set()
        self.role_bound = None

    @property
    def active(self):
        return self.variant is not None or self.pending is not None

    def accepts(self, hit):
        return hit.text_id in self.accepted

    @staticmethod
    def _interval(frame, caption):
        # Frame acquisition is bounded independently of OCR completion. A small
        # render-boundary margin never becomes a 30-second last-caption hint.
        return (frame.started - caption['start'] - caption['duration'] - .1,
                frame.finished - caption['start'] + .1)

    def _intersect(self, value):
        if self.origin is None:
            return value
        return max(value[0], self.origin[0]), min(value[1], self.origin[1])

    def observe(self, index, groups, *, scope, frame, now, stable_frames, player=None):
        compiled = getattr(index, '_zzz_cinema_occurrences', None)
        source_scope = (scope, getattr(index, 'publisher_generation', None),
            getattr(index, 'publisher_request_sha256', None), getattr(index, '_signature', None),
            getattr(index, 'source_locale', None), getattr(index, 'target_locale', None))
        if self.scope != source_scope:
            self.reset()
            self.scope = source_scope
        self.accepted.clear()
        if (not compiled or not isinstance(frame, CinemaFrame) or not frame.valid(now)
                or index.publisher_generation != compiled['metadata']['generation']
                or index.publisher_request_sha256 != compiled['request_sha256']):
            self.reset()
            return []
        if self.last_frame and (frame.sequence != self.last_frame.sequence + 1
                or frame.started < self.last_frame.finished
                or frame.started - self.last_frame.finished > 1.):
            self.reset()
            self.scope = source_scope
        if self.role_bound is not None and self.role_bound != player:
            self.reset()
            self.scope = source_scope
        self.last_frame = frame
        observations = []
        shared = []
        for text in groups:
            for locale in {variant['locale'] for variant in compiled['variants'].values()}:
                key = normalize_text(text, locale)
                anchors = compiled['anchors'].get((locale, key), ()) if key else ()
                if len(anchors) == 1:
                    observations.append((locale, *anchors[0], text))
                elif player and self.variant is None:
                    paired = compiled['player_anchors'].get((locale, key), {}).get(player)
                    if paired:
                        shared.append((locale, *paired, text))
        unique = {(locale, variant, ordinal) for locale, variant, ordinal, _ in observations + shared}
        if len(unique) > 1:
            self.reset()
            return []
        if unique:
            locale, variant_key, ordinal = next(iter(unique))
            variant = compiled['variants'][variant_key]
            token = variant_key, ordinal
            caption = variant['captions'][ordinal]
            if self.variant not in (None, variant_key) or self.pending not in (None, token):
                self.reset()
                self.scope, self.last_frame = source_scope, frame
            origin = self._intersect(self._interval(frame, caption))
            if origin[0] > origin[1]:
                self.reset()
                return []
            self.origin = origin
            self.count = self.count + 1 if self.pending == token else 1
            self.pending = token
            if shared:
                self.role_bound = player
            if self.count >= max(2, stable_frames):
                self.variant, self.ordinal = variant_key, ordinal
                if shared:
                    return self._emit(index, variant, ordinal, shared[0][3])
                self.role_bound = None
            # The ordinary index owns the independently voiced anchor.
            return []
        if self.variant is None:
            # An anchor must be observed on consecutive actual frames.
            self.pending, self.count, self.origin = None, 0, None
            return []
        variant = compiled['variants'][self.variant]
        if frame.started - self.origin[1] > max(c['start'] + c['duration'] for c in variant['captions']) + .1:
            self.reset()
            return []
        if not groups:
            return []
        locale, captions = variant['locale'], variant['captions']
        matches = [(ordinal, text) for text in groups for ordinal, caption in enumerate(captions)
            if normalize_text(text, locale) and normalize_text(text, locale) ==
                normalize_text(compiled['texts'][caption['text_id']][locale], locale)]
        if not matches or len({ordinal for ordinal, _ in matches}) != 1:
            self.reset()
            return []
        ordinal, observed = matches[0]
        if ordinal not in (self.ordinal, self.ordinal + 1):
            self.reset()
            return []
        origin = self._intersect(self._interval(frame, captions[ordinal]))
        if origin[0] > origin[1]:
            self.reset()
            return []
        self.origin, self.ordinal = origin, ordinal
        return self._emit(index, variant, ordinal, observed)

    def _emit(self, index, variant, ordinal, observed):
        row = variant['rows'].get(ordinal)
        if row is None:
            return []
        target = resolve_locale(index.target_locale, row['texts'])
        hit = TextMatch(game='zzz', text_id=row['text_id'], english=row.get('english') or row['source_text'],
            chinese=row.get('chinese', ''), source_ocr=observed, score=100., kind='exact',
            source_language=study_language(index.source_locale), source_locale=index.source_locale,
            source_text=row['source_text'], audio_locale=row['audio_locale'], audio_scope='context',
            texts=row['texts'], translation_locale=target or index.target_locale,
            translation_text=row['texts'].get(target, '') if target else '',
            voice_status='voiced', dialogue_kind='cutscene', text_capture_verified=True,
            speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese'),
            **index._publisher_context(row))
        self.accepted.add(hit.text_id)
        return [hit]
