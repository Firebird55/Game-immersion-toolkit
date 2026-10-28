"""Decode local bank voices and build a resumable audio fingerprint index."""
from backend.runtime_paths import data_root as runtime_data_root
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import wave
from datetime import datetime

import numpy as np

from backend.agent_fingerprint import landmarks, mono_audio
from backend.voice_assets import VoiceEntry


def index_matches_library(database: sqlite3.Connection, clips: dict, pcm_dir: Path) -> bool:
    """A moved game path does not require rebuilding unchanged audio hashes."""
    indexes = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    if not {'idx_hashes_hash', 'idx_hashes_asset'} <= indexes:
        return False
    done = {asset: (stamp, duration) for asset, stamp, duration in
            database.execute('SELECT asset_id, fingerprint, duration FROM clips')}
    if len(done) != len(clips):
        return False
    for asset, entry in clips.items():
        legacy = f"{entry['package_size']}:{entry['package_mtime_ns']}:{entry['offset']}:{entry['size']}"
        stamp, duration = done.get(asset, (None, 0.))
        if stamp not in (entry.get('sha256', legacy), legacy) or duration <= 0:
            return False
        if .3 <= duration <= 120 and not (pcm_dir / f'{asset}.npy').exists():
            return False
    return True


def main():
    root = Path(__file__).resolve().parents[1]
    folder = runtime_data_root(root) / 'agent-voices'
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, default=folder/'library.json')
    parser.add_argument('--database', type=Path, default=folder/'fingerprints.db',
                        help='Optional temporary build database; copy back only after a successful run')
    args = parser.parse_args()
    library = json.loads(args.library.read_text(encoding='utf-8'))
    decoder = runtime_data_root(root) / 'voice-assets/vgmstream/vgmstream-cli.exe'
    pcm_dir = folder / 'pcm'
    pcm_dir.mkdir(exist_ok=True)
    database_path = args.database
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(database_path)
    try:
        if database.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise sqlite3.DatabaseError('fingerprint index failed integrity check')
    except sqlite3.DatabaseError:
        database.close()
        archived = database_path.with_name(f'fingerprints-corrupt-{datetime.now():%Y%m%d-%H%M%S}.db')
        database_path.replace(archived)
        print(f'Archived unreadable fingerprint index as {archived.name}; rebuilding.', flush=True)
        database = sqlite3.connect(database_path)
    database.execute('PRAGMA journal_mode=WAL')
    database.execute('PRAGMA synchronous=NORMAL')
    database.execute('CREATE TABLE IF NOT EXISTS clips (asset_id TEXT PRIMARY KEY, duration REAL, fingerprint TEXT)')
    database.execute('CREATE TABLE IF NOT EXISTS hashes (hash INTEGER, asset_id TEXT, frame INTEGER)')
    if index_matches_library(database, library['clips'], pcm_dir):
        database.close()
        print(f'Complete ({len(library["clips"])} existing clip fingerprints reused)', flush=True)
        return
    # Maintaining two large B-trees for every inserted landmark is extremely
    # slow on USB storage. Recognition is paused during this rebuild, so make
    # the search indexes once after the data is complete.
    database.execute('DROP INDEX IF EXISTS idx_hashes_hash')
    database.execute('DROP INDEX IF EXISTS idx_hashes_asset')
    done = {asset: (stamp, duration) for asset, stamp, duration in database.execute('SELECT asset_id, fingerprint, duration FROM clips')}
    old_library = folder / 'library.json'
    old_clips = json.loads(old_library.read_text(encoding='utf-8')).get('clips', {}) if old_library.exists() else {}
    def decode(pair):
        asset_id, entry = pair
        legacy = f"{entry['package_size']}:{entry['package_mtime_ns']}:{entry['offset']}:{entry['size']}"
        stamp = entry.get('sha256', legacy)
        prior_stamp, duration = done.get(asset_id, (None, 0.))
        if prior_stamp in (stamp, legacy) and duration > 0:
            if (pcm_dir/f'{asset_id}.npy').exists() or not .3 <= duration <= 120:
                return asset_id, duration, None, stamp
        cached_pcm = pcm_dir/f'{asset_id}.npy'
        if prior_stamp is None and old_clips.get(asset_id, {}).get('sha256') == stamp and cached_pcm.exists():
            try:
                samples = np.load(cached_pcm, allow_pickle=False)
                duration = len(samples) / 8000
                if .3 <= duration <= 120:
                    return asset_id, duration, landmarks(samples), stamp
            except (OSError, ValueError):
                pass
        try:
            voice = VoiceEntry(Path(entry['package']), entry['offset'], entry['size'], entry['file_id'])
            with tempfile.TemporaryDirectory(prefix='zzz-agent-') as temp:
                wem, wav = Path(temp) / 'voice.wem', Path(temp) / 'voice.wav'
                wem.write_bytes(voice.read())
                subprocess.run([str(decoder), '-o', str(wav), str(wem)], capture_output=True,
                               check=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
                with wave.open(str(wav)) as audio:
                    if audio.getsampwidth() != 2:
                        return asset_id, 0., [], stamp
                    rate, channels = audio.getframerate(), audio.getnchannels()
                    samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32).reshape(-1, channels) / 32768
            samples = mono_audio(samples, rate)
            duration = len(samples) / 8000
            if not .3 <= duration <= 120:
                return asset_id, duration, [], stamp
            temporary = pcm_dir/f'{asset_id}.pending'
            with temporary.open('wb') as output:
                np.save(output, samples, allow_pickle=False)
            temporary.replace(pcm_dir/f'{asset_id}.npy')
            return asset_id, duration, landmarks(samples), stamp
        except Exception as error:
            print(f'Could not index {asset_id}: {error}', flush=True)
            return asset_id, 0., None, None
    failures = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        for index, result in enumerate(pool.map(decode, library['clips'].items()), 1):
            if result:
                asset_id, duration, hashes, stamp = result
                if stamp is None:
                    failures += 1
                    continue  # not marked done: automatically retry next run
                if hashes is not None and asset_id in done:
                    database.execute('DELETE FROM hashes WHERE asset_id = ?', (asset_id,))
                database.execute('INSERT OR REPLACE INTO clips VALUES (?, ?, ?)', (asset_id, duration, stamp))
                if hashes is not None:
                    database.executemany('INSERT INTO hashes VALUES (?, ?, ?)', [(h, asset_id, t) for h,t in hashes])
            if index % 200 == 0:
                database.commit()
                print(f'{index}/{len(library["clips"])} clips indexed', flush=True)
        database.commit()
    database.execute('CREATE TEMP TABLE active_assets (asset_id TEXT PRIMARY KEY)')
    database.executemany('INSERT INTO active_assets VALUES (?)', [(asset,) for asset in library['clips']])
    database.execute('DELETE FROM hashes WHERE asset_id IN (SELECT asset_id FROM clips WHERE asset_id NOT IN (SELECT asset_id FROM active_assets))')
    database.execute('DELETE FROM clips WHERE asset_id NOT IN (SELECT asset_id FROM active_assets)')
    database.commit()
    database.execute('CREATE INDEX IF NOT EXISTS idx_hashes_hash ON hashes(hash)')
    database.execute('CREATE INDEX IF NOT EXISTS idx_hashes_asset ON hashes(asset_id)')
    database.commit()
    print('Complete', database.execute('SELECT COUNT(*) FROM hashes').fetchone(), flush=True)
    database.close()
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
