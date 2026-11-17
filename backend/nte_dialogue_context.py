"""Narrow-panel NTE context from one directly preceding original speech node.

This does not alter shared matching or the full-frame UI/unknown-text veto.
Only a stable independent exact voiced observation establishes an anchor.
Context-dependent observations cannot extend it or traverse another edge.
"""
from .languages import normalize_text, resolve_locale, study_language
from .models import TextMatch
from .textmaps import display_text


class NteDialogueContext:
    def __init__(self):
        self.reset()

    def reset(self):
        self.scope = None
        self.anchor = self.pending = None
        self.count = 0
        self.confirmed_at = self.last_seen = self.observed_at = None
        self.rows, self.next = {}, {}
        self.prepared = False

    def _prepare(self, index):
        by_id = {}
        for row in index._records:
            by_id.setdefault(row['text_id'], []).append(row)
        def eligible(row):
            return (row.get('voice_status') == 'voiced' and row.get('audio')
                    and row.get('dialogue_kind') == 'conversation'
                    and 'dialogue' in row.get('channels', ['dialogue'])
                    and not row.get('text_binding_unresolved')
                    and (not row.get('player_voice') or row['player_voice'] == index.player_voice))
        self.rows = {key: values[0] for key, values in by_id.items() if len(values) == 1 and eligible(values[0])}
        for row in self.rows.values():
            previous = row.get('previous_text_id')
            if previous not in self.rows:
                continue
            text = normalize_text(row['texts'].get(index.source_locale, ''), index.source_locale)
            preceding = normalize_text(self.rows[previous]['texts'].get(index.source_locale, ''), index.source_locale)
            if text and preceding and text != preceding:
                self.next.setdefault(previous, {}).setdefault(text, []).append(row)

    def match(self, index, lines, default, *, enabled, scope, now, stable_frames):
        if not enabled or getattr(index, 'game', None) != 'nte' or not hasattr(index, '_records'):
            self.reset()
            return default
        if not self.prepared or scope != self.scope or self.observed_at is not None and now < self.observed_at:
            self.reset(); self.scope = scope
            with index.lock:
                self._prepare(index)
            self.prepared = True
        caption = display_text(' '.join(lines)).strip()
        key = normalize_text(caption, index.source_locale)
        if (self.confirmed_at is not None and not 0 <= now-self.confirmed_at <= 12
                or self.last_seen is not None and not 0 <= now-self.last_seen <= 3):
            self.anchor = None
        if not key:
            self.pending, self.count = None, 0
            self.observed_at = now
            return default
        row = self.rows.get(default.text_id) if default is not None and default.kind == 'exact' else None
        independent = row is not None and default.voice_status == 'voiced' and key == normalize_text(
            row['texts'].get(index.source_locale, ''), index.source_locale)
        if independent:
            token = row['text_id']
            self.count = self.count+1 if self.pending == token and self.observed_at is not None and now-self.observed_at <= 2 else 1
            self.pending, self.observed_at, self.last_seen = token, now, now
            # Every independently seen caption replaces the previous anchor;
            # an unrelated line cannot leave old context armed in the panel.
            self.anchor = None
            if self.count >= max(2, stable_frames) and token in self.next:
                self.anchor, self.confirmed_at = token, now
            return default
        values = self.next.get(self.anchor, {}).get(key, []) if self.anchor else []
        self.pending, self.count, self.observed_at = None, 0, now
        if len(values) != 1 or default is not None:
            self.anchor = None
            return default
        row = values[0]
        self.last_seen = now
        target = resolve_locale(index.target_locale, row['texts'])
        return TextMatch(game='nte', text_id=row['text_id'], english=row.get('english') or row['source_text'],
            chinese=row.get('chinese', ''), source_ocr=caption, score=100., kind='exact',
            source_language=study_language(index.source_locale), source_locale=index.source_locale,
            source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
            translation_locale=target or index.target_locale, translation_text=row['texts'].get(target, '') if target else '',
            speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese'),
            voice_status='voiced', dialogue_kind='conversation', audio_scope=row.get('audio_scope', 'line'))
