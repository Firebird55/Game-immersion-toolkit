"""Resolve complete ZZZ dialogue captions using authored speakers and scenes.

This path is restricted to the narrow dialogue panel. It never weakens the
ordinary matcher or its full-frame silent/UI ambiguity veto.
"""
from __future__ import annotations

import json
import re

from .languages import normalize_text, resolve_locale, study_language
from .models import TextMatch
from .speakers import _humanize_token, _voice_token
from .textmaps import display_text


def authored_scene(text_id):
    # Keep the entire authored scene prefix, not just its chapter. Do not infer
    # scene membership for Tips, chat choices, comics, or unknown ID formats.
    match = re.fullmatch(r'((?:Main_|PartnerTalk_)?GalGame_[A-Za-z0-9_]+)_\d{3}(?::[MF])?', text_id)
    return match.group(1) if match else None


def speaker_names(row):
    names = [row.get('speaker_english'), row.get('speaker_chinese')]
    token = _voice_token((row.get('audio') or {}).get('source', ''))
    if token:
        names.extend(_humanize_token(token))
        # These authored protagonist folders distinguish otherwise identical
        # captions, including snapshots made before player_voice was populated.
        names.append({'wise': '哲', 'belle': '铃'}.get(token.casefold()))
    return {normalize_text(name) for name in names if name}


def caption_pairs(lines):
    """A verified speaker must lead the entire remaining caption.

    Clothing and scenery can produce unrelated OCR rows above the nameplate.
    Those rows are not part of the caption; text after the speaker is never
    truncated or searched for a shorter dialogue fragment.
    """
    cleaned = [display_text(line).strip() for line in lines if display_text(line).strip()]
    if not cleaned:
        return []
    pairs = []
    for position, first in enumerate(cleaned):
        rest = cleaned[position + 1:]
        if rest:
            pairs.append((first.rstrip(':：'), ' '.join(rest)))
        explicit = re.match(r'^([^:：]{1,48})[:：]\s*(.+)$', first)
        if explicit:
            pairs.append((explicit[1], ' '.join([explicit[2], *rest])))
        words = first.split()
        # OCR may join a decorative glyph left of a centered nameplate to the
        # speaker row. Only its short trailing name is eligible, and the whole
        # following caption must still agree with that authored speaker.
        if rest and len(words) <= 6:
            for start in range(max(1, len(words) - 4), len(words)):
                pairs.append((' '.join(words[start:]).rstrip(':：'), ' '.join(rest)))
        for count in range(1, min(4, len(words) - 1) + 1):
            pairs.append((' '.join(words[:count]).rstrip(':：'), ' '.join([*words[count:], *rest])))
    return list(dict.fromkeys(pairs))


class ZzzDialogueContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.scene = None
        self.confirmed_at = 0.
        self.pending = None
        self.count = 0
        self.observed_at = 0.

    def _observe(self, match, now, stable_frames):
        # Only an independently unique exact match may establish/refresh scene
        # context. A match that needed the old scene cannot keep itself alive.
        scene = authored_scene(match.text_id) if match and match.kind == 'exact' else None
        token = (scene, match.text_id) if scene else None
        self.count = self.count + 1 if token and token == self.pending and now - self.observed_at <= 2 else 1
        self.pending, self.observed_at = token, now
        if token and self.count >= max(2, stable_frames):
            self.scene, self.confirmed_at = scene, now

    def match(self, index, lines, default, *, enabled, scope, now, stable_frames):
        if not enabled or getattr(index, 'game', None) != 'zzz' or not hasattr(index, '_lookup'):
            self.reset()
            return default
        if scope != self.scope:
            self.reset()
            self.scope = scope
        if now - self.confirmed_at > 30:
            self.scene = None

        pairs = caption_pairs(lines)
        matches = {}
        with index.lock:
            for speaker, caption in pairs:
                speaker_key = normalize_text(speaker)
                minimum = 6 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', caption) else 12
                for locale, lookup in index._lookup.items():
                    key = normalize_text(caption, locale)
                    if len(key) < minimum:
                        continue
                    # Exact complete official text only: never fuzzy matches,
                    # fragments, alternatives, or authored partial-page anchors.
                    for row in lookup.get(key, ()):
                        if (not row.get('audio') or row.get('voice_status', 'voiced') != 'voiced'
                                or row.get('dialogue_kind', 'conversation') not in (None, 'conversation')
                                or 'dialogue' not in row.get('channels', ('dialogue',))
                                or normalize_text(row['texts'].get(locale, ''), locale) != key
                                or speaker_key not in speaker_names(row)):
                            continue
                        matches[row['text_id']] = (row, caption, speaker)

            def identities(values):
                return {(authored_scene(row['text_id']), json.dumps(row['audio'], sort_keys=True),
                         row['source_text'], json.dumps(row['texts'], sort_keys=True))
                        for row, _, _ in values}

            values = list(matches.values())
            independent = len(identities(values)) == 1
            if not independent and self.scene:
                values = [value for value in values if authored_scene(value[0]['text_id']) == self.scene]
            if len(identities(values)) != 1:
                # A confirmed speaker with multiple performances is still
                # ambiguous. Do not fall back to an arbitrary voice selection.
                self._observe(None, now, stable_frames)
                return None if matches else default
            row, caption, speaker = values[0]
            target = resolve_locale(index.target_locale, row['texts'])
            english_name = row.get('speaker_english')
            chinese_name = row.get('speaker_chinese')
            if re.search(r'[\u3400-\u9fff]', speaker):
                chinese_name = chinese_name or speaker
            else:
                english_name = english_name or speaker
            result = TextMatch(game='zzz', text_id=row['text_id'],
                english=row.get('english') or row['source_text'], chinese=row.get('chinese', ''),
                source_ocr=caption, score=100., kind='exact',
                source_language=study_language(index.source_locale), source_locale=index.source_locale,
                source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
                translation_locale=target or index.target_locale,
                translation_text=row['texts'].get(target, '') if target else '',
                speaker_english=english_name, speaker_chinese=chinese_name,
                voice_status='voiced', dialogue_kind=row.get('dialogue_kind'))
        self._observe(result if independent else None, now, stable_frames)
        return result
