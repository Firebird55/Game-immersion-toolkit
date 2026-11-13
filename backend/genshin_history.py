"""Keep earlier published performances for identical dialogue in subsequent releases."""
import hashlib
import json
import sqlite3

from . import genshin_publisher as publisher
from .hoyo_dialogue import audio_locale
from .voice_assets import voice_hash


def _source_names(source):
    if source.startswith('Chinese\\'):
        return (source, 'Chinese(PRC)' + source[len('Chinese'):])
    return (source,)


def _identity(row, source):
    # Genshin's Talk IDs, WEM names and text hashes can each survive a rewrite.
    # Check the actual displayed study-language text as well as the exact take.
    return hashlib.sha256(json.dumps([row['text_id'], row['source_text'], row['player_voice'], source],
                                     ensure_ascii=False, separators=(',', ':')).encode()).digest()


def retained_performances(data_dir, stamp, region, locale, links, rows, ambiguous):
    tools = data_dir / 'tools'
    path = tools / 'sophon' / f'genshin-history-{region}-{locale}.sqlite3'
    sources = {'genshin:' + link['id']: link for link in links if link.get('source')}
    current = []
    missing = []
    for row in rows:
        link = sources.get(row['text_id'])
        if not link and row['player_voice'] and row['text_id'].startswith('genshin:fetter-'):
            link = sources.get(row['text_id'].removesuffix(':' + row['player_voice']))
        if not link:
            continue
        names = _source_names(link['source'])
        audio = row.get('audio')
        if audio and audio.get('publisher') == stamp and audio['source'] in names:
            current.append((_identity(row, audio['source']), stamp, audio['package']))
        elif row['voice_status'] == 'unavailable' and all(voice_hash(name) not in ambiguous for name in names):
            missing.extend((_identity(row, name), row, name, link) for name in names)

    with sqlite3.connect(path, timeout=60) as database:
        database.execute('CREATE TABLE IF NOT EXISTS performances '
                         '(identity BLOB PRIMARY KEY, publisher TEXT NOT NULL, package TEXT NOT NULL) WITHOUT ROWID')
        database.executemany('INSERT OR REPLACE INTO performances VALUES (?, ?, ?)', current)
        valid = {}
        recovered = 0
        for identity, row, source, link in missing:
            old = database.execute('SELECT publisher, package FROM performances WHERE identity=?', (identity,)).fetchone()
            if not old or old[0] == stamp or row['audio']:
                continue
            previous, package = old
            if previous not in valid:
                valid[previous] = publisher.voices.snapshot_available(tools, previous, 'genshin')
                if valid[previous]:
                    descriptor = json.loads((tools / 'sophon' / 'releases' / previous).read_bytes())
                    valid[previous] = descriptor['channel'] == publisher.CHANNELS[region]
            if valid[previous]:
                row['audio'] = {'publisher': stamp, 'original_publisher': previous, 'package': package, 'source': source,
                                'file_id': f'{voice_hash(source):016x}', 'locale': audio_locale(locale)}
                if link.get('gameplay_triggers'):
                    row['audio']['gameplay_triggers'] = link['gameplay_triggers']
                row['voice_status'] = 'voiced'
                recovered += 1
    return recovered
