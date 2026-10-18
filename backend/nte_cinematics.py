"""Authored movie bindings; text, cues and Mandarin media remain installed locally."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import re

from .game_tools import download
from .bilingual import contains_han
from .textmaps import display_text

CATALOG_REVISION = 'cef09a29d4d92c7b1e0b950d89ba8c75b1c529e7'
CATALOG_BASE = f'https://raw.githubusercontent.com/Waifus-Grace/NTE_Assets/{CATALOG_REVISION}/'
CATALOG_FILES = ('DataTable/Skill/DT_MediaFFmpegInfo.json', 'DataTable/Skill/DT_MediaFFmpegInfo_Quest.json')
SRT_ROOT = 'HT/Content/SrtFile/FFMpeg/Story/'


def load_catalog(directory: Path) -> list[dict]:
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for relative in CATALOG_FILES:
        path = directory / Path(relative).name
        if not path.is_file():
            data = download(CATALOG_BASE + relative)
            value = json.loads(data)
            if not isinstance(value, list) or len(value) != 1 or value[0].get('Type') != 'DataTable':
                raise ValueError('NTE movie binding catalog is incomplete')
            temporary = path.with_suffix('.pending')
            temporary.write_bytes(data)
            temporary.replace(path)
        rows.extend(json.loads(path.read_text(encoding='utf8'))[0]['Rows'].values())
    return rows


def catalog_rows(catalog: dict) -> list[dict]:
    rows = []
    for relative in CATALOG_FILES:
        table = catalog[Path(relative).name]
        if (not isinstance(table, list) or len(table) != 1 or not isinstance(table[0], dict) or
                table[0].get('Type') != 'DataTable' or not isinstance(table[0].get('Rows'), dict) or
                len(table[0]['Rows']) > 100_000 or not all(isinstance(r, dict) for r in table[0]['Rows'].values())):
            raise ValueError('Unsupported NTE movie catalog schema')
        rows.extend(table[0]['Rows'].values())
    if not movie_bindings(rows):
        raise ValueError('NTE catalog has no supported authored movie voice bindings')
    return rows


def movie_bindings(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        # The reviewed Sequence table explicitly supplies namespace/key text.
        # Other tables need their own reviewed namespace mapping before capture.
        if row.get('StringTableID') != 'Sequence':
            continue
        movie = row.get('Path', {}).get('FilePath', '')
        prefix = '../../../Projects/HT/Content/Movies/FFMpeg/Story/'
        if not movie.startswith(prefix) or not movie.endswith('.mp4'):
            continue
        relative = movie[len(prefix):-4]
        if not re.fullmatch(r'[A-Za-z0-9_/-]+', relative):
            continue
        reference = row.get('PlayVoice', {}).get('AssetPathName', '')
        match = re.fullmatch(r'/Game/WwiseAudio/Events/CG/[A-Za-z0-9_/]+/(Play_Vo_CG_[A-Za-z0-9_]+)\.\1', reference)
        if match:
            result.append({'subtitle': SRT_ROOT + relative + '.srt', 'event': match[1], 'namespace': 'ST_Sequence'})
    return result


def subtitle_cues(text: str) -> list[dict]:
    result = []
    text = text.lstrip('\ufeff').replace('\r\n', '\n')
    timestamp = r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})'
    for block in re.split(r'\n\s*\n', text.strip()):
        rows = block.strip().splitlines()
        if len(rows) != 3 or not rows[0].isdigit() or not re.fullmatch(r'[A-Za-z0-9_]+', rows[2].strip()):
            raise ValueError('Unsupported NTE subtitle cue layout')
        match = re.fullmatch(r'\s*' + timestamp + r'\s*-->\s*' + timestamp + r'\s*', rows[1])
        if not match:
            raise ValueError('Invalid NTE subtitle timestamp')
        values = list(map(int, match.groups()))
        if any(v >= 60 for v in [values[1], values[2], values[5], values[6]]):
            raise ValueError('Invalid NTE subtitle timestamp')
        start, end = [(h*3600+m*60+s)*1000+ms for h, m, s, ms in [values[:4], values[4:]]]
        if not 0 <= start < end <= 30*60*1000:
            raise ValueError('NTE subtitle timing exceeds supported bounds')
        result.append({'key': rows[2].strip(), 'start_ms': start, 'end_ms': end})
    return result


def movie_records(bindings, subtitles, english, chinese, events, *, require_han=True) -> list[dict]:
    result = []
    for binding in bindings:
        variants = events.get(binding['event'].lower())
        text = subtitles.get(binding['subtitle'])
        if not variants or not text:
            continue
        try:
            cues = subtitle_cues(text)
        except ValueError:
            continue
        counts = Counter(cue['key'] for cue in cues)
        for cue in cues:
            key = (binding['namespace'], cue['key'])
            en, zh = display_text(english.get(key, '')), display_text(chinese.get(key, ''))
            if not en or not zh or (require_han and not contains_han(zh)) or counts[cue['key']] != 1:
                continue
            for variant in variants:
                gender = variant['player_voice']
                suffix = ':' + gender if gender else ''
                result.append({'text_id': f"nte:{key[0]}:{key[1]}{suffix}", 'english': en, 'chinese': zh,
                               'player_voice': gender,
                               'audio': {**variant['audio'], 'start_ms': cue['start_ms'], 'end_ms': cue['end_ms']}})
    # A cue reused with different film timings/performances is unresolved.
    by_id = {}
    for record in result:
        by_id.setdefault(record['text_id'], []).append(record)
    return [rows[0] for rows in by_id.values() if len({json.dumps(r['audio'], sort_keys=True) for r in rows}) == 1]
