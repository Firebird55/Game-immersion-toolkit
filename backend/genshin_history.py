"""Keep earlier published performances for identical dialogue in subsequent releases."""
import hashlib
from http.client import IncompleteRead
import json
import sqlite3
from subprocess import SubprocessError
from tarfile import TarError
from urllib.error import URLError

from . import genshin_publisher as publisher
from .hoyo_dialogue import audio_locale
from .voice_assets import voice_hash

ARCHIVE_READER = 'v2:'

ARCHIVES = {
    '5.5.0': {
        'metadata': 'dcf2fa8cccfe7bdc70797d1cfce79f6907806835',
        'global': 'sophon-c7feb6296ad1acb66b9c50e16f2fcd6810f3cb361e958e530f2c53cb16b7ef3d',
        'cn': 'sophon-ae2aaab9e1962e56f11a5a877bee07946f0bcca10649fc336d638b2a8b4b4679',
    },
    '4.8.0': {
        'metadata': '411376ae92931a04d41ae5a9386d45c0d2deb8a8',
        'global': 'sophon-0918403364ba1098b33d74abb39909a31ff1bf12b48d2f936d4e8735d1ccc70e',
        'cn': 'sophon-f1b4e8a7917a99da22b9fa9c82dadff74499b8de31be81afd9c64f0fd83a8988',
    },
}


def _archived_build(data_dir, region, version):
    from . import sophon_assets as sophon
    from .game_tools import _atomic_file, download
    stamp = ARCHIVES[version][region]
    tools = data_dir / 'tools'
    path = tools / 'sophon' / 'releases' / stamp
    if publisher.voices.snapshot_available(tools, stamp, 'genshin'):
        return stamp
    channel = publisher.CHANNELS[region]
    if region == 'global':
        url = 'https://raw.githubusercontent.com/umaichanuwu/meta/9019bb94f6dccb62bd11be734599644ed20e73b3/hoyodata.json'
        record = json.loads(download(url, limit=8 * 1024**2))['hk4e']['sophonInfos']
        main = {'tag': version, 'branch': 'main', 'package_id': record['package'], 'password': record['password']}
    else:
        url = f'https://raw.githubusercontent.com/kuaichu/game-cdn-archive/58fb1715ce2f891e9873741c66700817d9552cda/docs/data/hoyo/versions/hk4e/{version}.json'
        main = json.loads(download(url, limit=1024**2))['chunk']
    build = sophon.released_build(channel, main)
    identity, raw = publisher.voices.descriptor(build)
    if identity != stamp:
        raise ValueError('The archived Genshin release differs from the verified publisher descriptor.')
    _atomic_file(path, raw)
    return stamp


def _seed_archive(data_dir, region, locale, version, *, mirror=False):
    from . import genshin_assets as game, hoyo_dialogue as common
    from .dialogue_catalog import DialogueCatalog, selected_tables
    revision = ARCHIVES[version]['metadata']
    stamp = _archived_build(data_dir, region, version)
    archive = DialogueCatalog('genshin-archive', data_dir, revision=revision)
    if mirror:
        from .genshin_archive_mirror import fetch_trees
        fetch_trees(archive)
    translations = DialogueCatalog('genshin-archive-mirror', data_dir, revision=revision) if mirror else archive
    tables = selected_tables(translations, game.TEXT_LOCALES, locale, ())
    hashes = game.dialogue_hashes(archive.directory_json('BinOutput/Talk'))
    links = game.dialogue_links(archive.directory_json('BinOutput/Voice'), hashes, locale)
    if not hashes or not links:
        raise ValueError('The archived Genshin narrative tables are incomplete.')
    entries = publisher.inventory(data_dir, stamp, locale)
    rows = game._render_player_text(common.records('genshin', links, tables, locale, entries), locale)
    if not any(row['audio'] for row in rows):
        raise ValueError('The archived Genshin narrative audio is unavailable.')
    retained_performances(data_dir, stamp, region, locale, links, rows, set(), archive=revision)


def prepare_archive(data_dir, region, locale, version):
    path = _database_path(data_dir, region, locale)
    with sqlite3.connect(path, timeout=60) as database:
        database.execute('CREATE TABLE IF NOT EXISTS archives (revision TEXT PRIMARY KEY) WITHOUT ROWID')
        if database.execute('SELECT 1 FROM archives WHERE revision=?', (ARCHIVE_READER + ARCHIVES[version]['metadata'],)).fetchone():
            return True
    try:
        try:
            _seed_archive(data_dir, region, locale, version)
        except (URLError, TimeoutError, ConnectionError, IncompleteRead):
            _seed_archive(data_dir, region, locale, version, mirror=True)
    except (URLError, TimeoutError, ConnectionError, IncompleteRead, SubprocessError, TarError, EOFError, ValueError, KeyError):
        return False
    return True


def _source_names(source):
    if source.startswith('Chinese\\'):
        return (source, 'Chinese(PRC)' + source[len('Chinese'):])
    return (source,)


def _identity(row, source):
    # Genshin's Talk IDs, WEM names and text hashes can each survive a rewrite.
    # Check the actual displayed study-language text as well as the exact take.
    return hashlib.sha256(json.dumps([row['text_id'], row['source_text'], row['player_voice'], source],
                                     ensure_ascii=False, separators=(',', ':')).encode()).digest()


def _database_path(data_dir, region, locale):
    return data_dir / 'tools' / 'sophon' / f'genshin-history-{region}-{locale}.sqlite3'


def retained_performances(data_dir, stamp, region, locale, links, rows, ambiguous, *, archive=None):
    tools = data_dir / 'tools'
    path = _database_path(data_dir, region, locale)
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
        if archive:
            database.executemany('INSERT OR IGNORE INTO performances VALUES (?, ?, ?)', current)
            database.execute('INSERT OR IGNORE INTO archives VALUES (?)', (ARCHIVE_READER + archive,))
            return 0
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
