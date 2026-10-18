"""Locale-tagged official text matching with one verified source performance."""
from __future__ import annotations

import json
from pathlib import Path
import re
import threading

from rapidfuzz import fuzz, process

from .languages import audio_locale, normalize_text, resolve_locale, study_language
from .models import TextMatch, is_comic_text_id
from .textmaps import display_text


def candidates(lines):
    cleaned = [display_text(line) for line in lines if display_text(line)]
    rows = [display_text(part) for line in cleaned for part in re.split(r'\s*[~～]\s*|(?<=[.!?。！？])\s+(?=[^\W\d_])|(?<=[。！？])\s*(?=[A-Za-z])|(?<=[.!?])\s*(?=[\u3400-\u9fff])', line) if display_text(part)]
    values = [' '.join(cleaned)] if cleaned else []
    for first in range(len(rows)):
        for last in range(first + 1, min(len(rows), first + 8) + 1):
            value = ' '.join(rows[first:last])
            values.append(value)
            if re.search(r'[:：]', value):
                values.append(re.split(r'[:：]', value, maxsplit=1)[1].strip())
    return list(dict.fromkeys(values))


class MultilingualTextIndex:
    def __init__(self, game: str, directory: Path):
        self.game, self.path = game, directory / 'textmap.json'
        self.ready = False
        self.player_voice = 'unconfigured'
        self.target_locale = 'en'
        self.source_locale = ''
        self.entry_count = self.audio_count = 0
        self.message, self.state = 'Prepare this game language in Setup', 'not_ready'
        self.lock = threading.RLock()
        self._records, self._lookup, self._context_pairs, self._context_firsts = [], {}, {}, {}
        self._signature = None
        self.load()

    def load(self):
        try:
            info = self.path.stat()
            signature = (info.st_size, info.st_mtime_ns)
            if signature == self._signature:
                return True
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            if payload.get('format') != 2 or payload.get('game') != self.game:
                raise ValueError('Unsupported game language snapshot')
            locale = payload['source_locale']
            study_language(locale)
            lookup, context_pairs = {}, {}
            for row in payload['records']:
                if row.get('source_locale') != locale or not isinstance(row.get('source_text'), str) or not row['source_text']:
                    raise ValueError('Incomplete game study text')
                if not isinstance(row.get('texts'), dict) or row['texts'].get(locale) != row['source_text']:
                    raise ValueError('Official text locales do not agree')
                if row.get('audio_locale') != audio_locale(locale):
                    raise ValueError('Original voice locale does not match study text')
                if not row.get('audio') and not (self.game == 'zzz' and is_comic_text_id(row['text_id'])):
                    continue
                for language, text in row['texts'].items():
                    for value in [text, *row.get('ocr_texts', {}).get(language, [])]:
                        key = normalize_text(display_text(value), language)
                        if len(key) >= 2:
                            lookup.setdefault(language, {}).setdefault(key, []).append(row)
                    if row.get('member_text_ids') and (anchors := row.get('ocr_texts', {}).get(language)):
                        last = anchors[0]
                        if last and text.endswith(' ' + last):
                            first = text[:-len(last)-1]
                            pair = (language, normalize_text(first, language), normalize_text(last, language))
                            context_pairs.setdefault(pair, []).append(row)
            with self.lock:
                self.source_locale, self._records, self._lookup = locale, payload['records'], lookup
                self._context_pairs = context_pairs
                self._context_firsts = {}
                for language, first, _ in context_pairs:
                    self._context_firsts.setdefault(language, set()).add(first)
                self.entry_count = len(payload['records'])
                self.audio_count = sum(bool(r.get('audio')) for r in self._records)
                self.ready = True
                self.state = 'ready' if self.audio_count else 'missing_voice'
                self.message = payload.get('message', f'{self.entry_count:,} official lines; {self.audio_count:,} original voices')
                self._signature = signature
            return True
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.message = 'Previous complete language snapshot retained' if self.ready else str(error)
            return False

    def status(self):
        return {'ready': self.ready, 'state': self.state, 'message': self.message,
                'entry_count': self.entry_count, 'audio_count': self.audio_count, 'source_locale': self.source_locale}

    @staticmethod
    def authored_scene(text_id):
        return text_id.rsplit(':', 1)[0] if re.fullmatch(r'heavyrain:\d+:[a-f0-9]{8}', text_id) else None

    def match_lines(self, lines, threshold=88, exact_only=False, channel='dialogue', context_groups=()):
        hits, ambiguous = [], []
        with self.lock:
            for source in candidates(lines):
                for locale, lookup in self._lookup.items():
                    key, score = normalize_text(source, locale), 100.
                    rows = lookup.get(key, [])
                    # HEAVY RAIN paginates some authored paragraphs at runtime.
                    # A sufficiently long, exact contiguous page can identify
                    # the whole bound performance; never infer page audio cuts.
                    minimum = 12 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', key) else 24
                    if self.game == 'heavyrain' and channel == 'dialogue' and len(key) >= minimum:
                        rows = [row for text, matches in lookup.items() if key in text for row in matches]
                    if not rows and not exact_only and len(key) >= 8:
                        matches = process.extract(key, lookup.keys(), scorer=fuzz.ratio, score_cutoff=max(88, threshold), limit=2)
                        if matches and (len(matches) == 1 or matches[1][1] < matches[0][1] - 2):
                            rows, score = lookup[matches[0][0]], matches[0][1]
                        elif matches:
                            ambiguous.append(source)
                    rows = [r for r in rows if channel in r.get('channels', ['dialogue', 'tip', 'cinematic', 'gameplay'])]
                    # ZZZ's authored M/F subtitles can themselves identify a
                    # performance. Use the configured Proxy only when the
                    # observed caption leaves more than one variant possible.
                    if self.game != 'zzz' or len(rows) > 1:
                        rows = [r for r in rows if not r.get('player_voice') or r['player_voice'] == self.player_voice]
                    identities = {(json.dumps(r.get('audio'), sort_keys=True), r['source_text']) for r in rows}
                    if self.game == 'heavyrain' and len(identities) > 1 and score == 100 and context_groups:
                        rows = [row for row in rows if self.authored_scene(row['text_id']) in context_groups]
                        identities = {(json.dumps(row.get('audio'), sort_keys=True), row['source_text']) for row in rows}
                    if len(identities) != 1:
                        if len(identities) > 1:
                            ambiguous.append(source)
                        continue
                    row = rows[0]
                    target = resolve_locale(self.target_locale, row['texts'])
                    hits.append(TextMatch(game=self.game, text_id=row['text_id'], english=row.get('english') or row['source_text'],
                        chinese=row.get('chinese', ''), source_ocr=source, score=score, kind='exact' if score == 100 else 'fuzzy',
                        source_language=study_language(self.source_locale), source_locale=self.source_locale,
                        source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
                        translation_locale=target or self.target_locale, translation_text=row['texts'].get(target, '') if target else '',
                        speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese')))
        if not hits:
            return None
        best = max(hits, key=lambda hit: (hit.score, len(normalize_text(hit.source_ocr))))
        key = normalize_text(best.source_ocr, 'zh-Hans')
        longer = [hit for hit in hits if hit.score >= max(92, threshold)
                  and len(normalize_text(hit.source_ocr, 'zh-Hans')) >= max(len(key) * 1.5, len(key) + 8)
                  and key in normalize_text(hit.source_ocr, 'zh-Hans')]
        if longer:
            best = max(longer, key=lambda hit: (len(normalize_text(hit.source_ocr)), hit.score))
        key = normalize_text(best.source_ocr, 'zh-Hans')
        if any(len(normalize_text(text, 'zh-Hans')) >= len(key)
               and key in normalize_text(text, 'zh-Hans') for text in ambiguous):
            return None
        peers = [hit for hit in hits if hit.score == best.score and len(normalize_text(hit.source_ocr)) == len(normalize_text(best.source_ocr))]
        if len({hit.text_id for hit in peers}) != 1:
            return None
        return best

    def context_fragments(self, lines):
        """Recognize an observed first cue without choosing its performance."""
        result = set()
        with self.lock:
            for text in candidates(lines):
                for locale, firsts in self._context_firsts.items():
                    key = normalize_text(text, locale)
                    if key in firsts:
                        result.add((locale, key))
        return tuple(sorted(result))

    def match_context(self, previous, lines):
        """Resolve two exact observed cues only through an authored context pair."""
        hits = {}
        with self.lock:
            for text in candidates(lines):
                for locale, first in previous:
                    for row in self._context_pairs.get((locale, first, normalize_text(text, locale)), []):
                        hit = self.match_lines([row['texts'][locale]], exact_only=True)
                        if hit and hit.text_id == row['text_id']:
                            hits[hit.text_id] = hit.model_copy(update={'source_ocr': first + ' ' + text})
        return next(iter(hits.values())) if len(hits) == 1 else None

    def match_line_groups(self, groups, threshold=88, channel='cinematic', context_groups=()):
        result = {}
        for group in groups:
            hit = self.match_lines([group], threshold, channel=channel, context_groups=context_groups)
            if hit:
                result.setdefault(hit.text_id, hit)
        return list(result.values())

    def match_text(self, text, threshold=88, channel='dialogue'):
        return self.match_lines([text], threshold, channel=channel)

    def is_capture_text(self, text_id, _english, channel):
        return any((r['text_id'] == text_id or text_id in (r.get('member_text_ids') or []))
                   and channel in r.get('channels', ['dialogue', 'tip', 'cinematic', 'gameplay']) for r in self._records)

    def resolve_display_name(self, _candidates):
        return None
