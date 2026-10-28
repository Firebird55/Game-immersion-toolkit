"""Exact cinematic captions scoped to a confirmed authored ZZZ scene."""
from __future__ import annotations

import json
import re

from .languages import normalize_text, resolve_locale, study_language
from .models import TextMatch
from .textmaps import display_text


def cutscene_scene(text_id):
    match = re.fullmatch(r'(CS_[A-Za-z0-9_]+)_(\d+)(?::[MF])?', text_id)
    return match.group(1) if match else None


def protagonist(row):
    # These are authored player-controlled Bangboo performances. Ordinary Belle
    # or Wise dialogue can be the sibling NPC and must not select the player.
    event = (row.get('audio') or {}).get('event') or ''
    match = re.search(r'_Bangboo(Wise|Belle)(?:_|$)', event, re.I)
    if match:
        return 'male' if match.group(1).casefold() == 'wise' else 'female'
    return row.get('player_voice') if row.get('player_voice') in {'male', 'female'} else None


def performance(row):
    return (cutscene_scene(row['text_id']), json.dumps(row['audio'], sort_keys=True), row['source_text'])


def subtitle_rows(response, image_size):
    """Only centered rows in the lower subtitle band can establish a movie."""
    width, height = image_size
    result = []
    for row in response.get('lines', []):
        bounds = row.get('bounding_rect') or {}
        try:
            xs = [float(bounds[f'x{i}']) / width for i in range(1, 5)]
            ys = [float(bounds[f'y{i}']) / height for i in range(1, 5)]
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
        if (.22 <= (min(xs) + max(xs)) / 2 <= .78
                and .60 <= min(ys) < max(ys) <= 1.0 and max(ys) - min(ys) < .10):
            result.append(row)
    return {**response, 'lines': result}


class ZzzCutsceneContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.proxy = None
        self.clear_scene()

    def clear_scene(self):
        self.scene = None
        self.seen_at = 0.
        self.position = -1
        self.pending = None
        self.count = 0
        self.observed_at = 0.

    def prepare(self, index, scope, recent, session_id):
        self.reset()
        self.scope = scope
        if not hasattr(index, '_lookup'):
            return
        # Restore only player evidence, not a stale movie scene, after restart.
        # An exact caption with different Wise/Belle wording proves the branch.
        with index.lock:
            for line in recent:
                if (line.session_id != session_id or line.game != 'zzz' or line.channel != 'cinematic'
                        or line.source_locale != index.source_locale or line.score != 100):
                    continue
                rows = index._lookup.get('en', {}).get(normalize_text(line.english, 'en'), ())
                players = {protagonist(row) for row in rows if cutscene_scene(row['text_id']) and protagonist(row)}
                matched = next((row for row in rows if row['text_id'] == line.text_id), None)
                if (matched and len(players) == 1 and protagonist(matched) in players
                        and normalize_text(line.source_ocr, 'en') == normalize_text(line.english, 'en')):
                    self.proxy = protagonist(matched)
                    break

    def accepts(self, match):
        return bool(self.scene and cutscene_scene(match.text_id) == self.scene)

    def match(self, index, groups, defaults, *, now, stable_frames, configured):
        if getattr(index, 'game', None) != 'zzz' or not hasattr(index, '_lookup'):
            return [hit for hit in defaults if cutscene_scene(hit.text_id)]
        if self.scene and now - self.seen_at > 30:
            self.clear_scene()
        proxy = configured if configured in {'male', 'female'} else self.proxy
        observations = []
        anchors = []
        eligible_default_ids = set()
        normal_ids = {hit.text_id for hit in defaults if hit.kind == 'exact'}
        with index.lock:
            # Keep the ordinary matcher's safe OCR-tolerant movie matches, but
            # only when its complete observation is in the subtitle band and
            # the recording agrees with the selected/inferred protagonist.
            for hit in defaults:
                if not cutscene_scene(hit.text_id):
                    continue
                if normalize_text(hit.source_ocr) not in {normalize_text(group) for group in groups}:
                    continue
                authored = next((row for locale, text in hit.texts.items()
                    for row in index._lookup.get(locale, {}).get(normalize_text(text, locale), ())
                    if row['text_id'] == hit.text_id), None)
                if authored and (not proxy or not protagonist(authored) or protagonist(authored) == proxy):
                    eligible_default_ids.add(hit.text_id)
            for caption in groups:
                for locale, lookup in index._lookup.items():
                    key = normalize_text(display_text(caption), locale)
                    all_rows = lookup.get(key, ())
                    rows = {row['text_id']: row for row in all_rows
                        if (cutscene_scene(row['text_id']) and row.get('audio')
                            and 'cinematic' in row.get('channels', ('cinematic',))
                            and normalize_text(row['texts'].get(locale, ''), locale) == key)}
                    # Unique alternate wording may identify the player even if
                    # an earlier session hint disagrees. Never infer from a pair
                    # whose identical caption belongs to both performances.
                    players = {protagonist(row) for row in rows.values() if protagonist(row)}
                    independent_player = next(iter(players)) if len(players) == 1 else None
                    selected = [row for row in rows.values() if not protagonist(row)
                                or protagonist(row) == (configured if configured in {'male', 'female'}
                                                        else independent_player or proxy)]
                    eligible_default_ids.update(row['text_id'] for row in selected)
                    minimum = 6 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', caption) else 12
                    unique = len({performance(row) for row in selected}) == 1
                    veto = key in getattr(index, '_full_frame_veto', {}).get(locale, set())
                    if unique and len(key) >= minimum and (selected[0]['text_id'] in normal_ids or (
                            not veto and all(cutscene_scene(row['text_id']) for row in all_rows))):
                        anchors.append((selected[0], caption, independent_player, len(key)))
                    if selected:
                        observations.append((selected, caption, len(key)))

            anchor = max(anchors, key=lambda value: value[3]) if anchors else None
            token = anchor[0]['text_id'] if anchor else None
            self.count = self.count + 1 if token and token == self.pending and now - self.observed_at <= 2 else 1
            self.pending, self.observed_at = token, now
            if anchor and self.count >= max(2, stable_frames):
                scene = cutscene_scene(anchor[0]['text_id'])
                if scene != self.scene:
                    self.scene, self.position = scene, -1
                self.seen_at = now
                if anchor[2] and configured not in {'male', 'female'}:
                    self.proxy = anchor[2]

            hits = []
            for rows, caption, length in observations:
                rows = [row for row in rows if self.scene and cutscene_scene(row['text_id']) == self.scene]
                if len({performance(row) for row in rows}) != 1:
                    continue
                row = rows[0]
                number = int(row['text_id'].split(':')[0].rsplit('_', 1)[1])
                if number < self.position:
                    continue
                target = resolve_locale(index.target_locale, row['texts'])
                hit = TextMatch(game='zzz', text_id=row['text_id'], english=row.get('english') or row['source_text'],
                    chinese=row.get('chinese', ''), source_ocr=caption, score=100., kind='exact',
                    source_language=study_language(index.source_locale), source_locale=index.source_locale,
                    source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
                    translation_locale=target or index.target_locale,
                    translation_text=row['texts'].get(target, '') if target else '',
                    speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese'),
                    voice_status='voiced', dialogue_kind='cutscene')
                hits.append((length, number, hit))
            if hits:
                _, number, hit = max(hits, key=lambda value: value[0])
                # Only forward dialogue progress refreshes a scene; a lingering
                # short HUD word cannot hold the context open indefinitely.
                if number > self.position:
                    self.position, self.seen_at = number, now
                return [hit]
        # Preserve existing long, globally unambiguous movie matches while the
        # first scene anchor stabilizes. Gameplay length filtering still applies.
        return [hit for hit in defaults if hit.text_id in eligible_default_ids and (
            not self.scene or (cutscene_scene(hit.text_id) == self.scene
                and int(hit.text_id.split(':')[0].rsplit('_', 1)[1]) >= self.position))]
