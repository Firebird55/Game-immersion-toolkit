"""Explicit, credential-free import of the retired browser's saved transcript.

This consumes an authored whitelist export, never a browser database or vault.
It does not run matching, infer an absent recording, or change capture settings.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import get_args

from .languages import study_language
from .models import GameId, TranscriptLine

FORMAT = 'toolkit-browser-history-v1'
MAX_BYTES = 64 * 1024**2
MAX_ROWS = 12000
FIELDS = frozenset(('source', 'id', 'game', 'createdAt', 'favorite', 'textId', 'english', 'chinese',
    'sourceText', 'sourceLocale', 'sourceLanguage', 'translationText', 'translationLocale', 'audioLocale',
    'audioScope', 'voiceStatus', 'textCaptureVerified', 'textTruncated', 'speakerEnglish', 'speakerChinese',
    'matching', 'score', 'hadAudio', 'audioSha256', 'playerVoice'))


def _check(condition):
    if not condition:
        raise ValueError('Invalid browser history backup; use the toolkit history-only exporter.')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _check(key not in result)
        result[key] = value
    return result


def parse_backup(raw):
    _check(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES)
    value = json.loads(raw, object_pairs_hook=_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid browser history number')))
    _check(isinstance(value, dict) and set(value) == {'format', 'rows'} and value['format'] == FORMAT
        and isinstance(value['rows'], list) and 0 < len(value['rows']) <= MAX_ROWS)
    result, identities = [], set()
    for original in value['rows']:
        _check(isinstance(original, dict) and not set(original) - FIELDS)
        row = dict(original)
        _check(row.get('game') in get_args(GameId))
        _check(isinstance(row.get('source'), str) and (row['source'] == 'mobile-ocr'
            or re.fullmatch(r'pc-[A-Za-z0-9-]{16,64}', row['source'])))
        _check(type(row.get('id')) in (str, int) and 0 < len(str(row['id'])) <= 512
            and (type(row['id']) is not int or 0 < row['id'] < 2**53))
        _check(type(row.get('createdAt')) is int and 0 <= row['createdAt'] <= 253402300799000)
        for key in ('favorite', 'hadAudio', 'textCaptureVerified', 'textTruncated'):
            _check(type(row.get(key, False)) is bool)
        for key in ('english', 'chinese', 'sourceText', 'translationText'):
            _check(key not in row or isinstance(row[key], str) and len(row[key]) <= 8000 and '\0' not in row[key])
        _check(isinstance(row.get('english'), str) and isinstance(row.get('chinese'), str))
        source = row.get('sourceText', row['chinese'])
        _check(bool(source.strip()))
        for key in ('sourceLocale', 'sourceLanguage', 'translationLocale', 'audioLocale'):
            _check(key not in row or isinstance(row[key], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,23}', row[key]))
        for key in ('speakerEnglish', 'speakerChinese', 'textId', 'matching'):
            _check(key not in row or isinstance(row[key], str) and len(row[key]) <= (512 if key == 'textId' else 128)
                and '\0' not in row[key])
        _check(isinstance(row.get('audioScope', 'line'), str) and row.get('audioScope', 'line') in {'line', 'context', 'paragraph'})
        _check(isinstance(row.get('voiceStatus', 'unknown'), str) and row.get('voiceStatus', 'unknown') in {'voiced', 'unvoiced', 'unavailable', 'unknown'})
        _check(row.get('playerVoice') in (None, 'unconfigured', 'male', 'female'))
        _check(row.get('audioSha256') is None or isinstance(row['audioSha256'], str)
            and re.fullmatch(r'[0-9a-f]{64}', row['audioSha256']))
        score = row.get('score', 0)
        _check(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100)
        # Favorite changes can promote an existing imported line, never produce
        # a duplicate or clear an independently favorited native line.
        identity = hashlib.sha256(json.dumps({k: v for k, v in row.items() if k != 'favorite'},
            sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()
        _check(identity not in identities)
        identities.add(identity)
        locale = row.get('sourceLocale', 'zh-Hans')
        status = row.get('voiceStatus', 'unknown')
        if row.get('hadAudio') or row.get('audioSha256') or status == 'voiced':
            status = 'unavailable'  # A history export carries no audio bytes.
        line = TranscriptLine(id=0, created_at=datetime.fromtimestamp(row['createdAt'] / 1000, timezone.utc),
            session_id='browser-migration', game=row['game'], source_ocr=source,
            english=row['english'], chinese=row['chinese'], text_id=row.get('textId') or 'browser-history:' + identity,
            score=score, match_kind='browser_migration', source_language=row.get('sourceLanguage', study_language(locale)),
            source_locale=locale, source_text=source, translation_locale=row.get('translationLocale', 'en'),
            translation_text=row.get('translationText', row['english']), audio_locale=row.get('audioLocale', locale),
            audio_scope=row.get('audioScope', 'line'), voice_status=status,
            dialogue_kind='browser_history_excerpt' if row.get('textTruncated') else 'browser_history',
            text_capture_verified=bool(row.get('textCaptureVerified') and not row.get('textTruncated')),
            speaker_english=row.get('speakerEnglish'), speaker_chinese=row.get('speakerChinese'),
            favorite=row.get('favorite', False))
        result.append((identity, line))
    return result


def summary(rows):
    return {'rows': len(rows), 'favorites': sum(line.favorite for _, line in rows),
        'games': sorted({line.game for _, line in rows}),
        'study_locales': sorted({line.source_locale for _, line in rows}),
        'audio_included': False,
        'excerpts': sum(line.dialogue_kind == 'browser_history_excerpt' for _, line in rows),
        'message': 'History and favorites only. Original recordings and credentials remain in the old browser.'}
