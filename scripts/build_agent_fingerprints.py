"""Decode local bank voices and build a resumable audio fingerprint index."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import wave

import numpy as np

from backend.agent_fingerprint import landmarks, mono_audio
from backend.voice_assets import VoiceEntry


def main():
    root = Path(__file__).resolve().parents[1]
    folder = root / 'data/agent-voices'
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, default=folder/'library.json')
    args = parser.parse_args()
    library = json.loads(args.library.read_text(encoding='utf-8'))
    decoder = root / 'data/voice-assets/vgmstream/vgmstream-cli.exe'
    pcm_dir = folder / 'pcm'
    pcm_dir.mkdir(exist_ok=True)
    database = sqlite3.connect(folder / 'fingerprints.db')
    database.execute('PRAGMA journal_mode=WAL')
    database.execute('CREATE TABLE IF NOT EXISTS clips (asset_id TEXT PRIMARY KEY, duration REAL, fingerprint TEXT)')
    database.execute('CREATE TABLE IF NOT EXISTS hashes (hash INTEGER, asset_id TEXT, frame INTEGER)')
    database.execute('CREATE INDEX IF NOT EXISTS idx_hashes_hash ON hashes(hash)')
    database.execute('CREATE INDEX IF NOT EXISTS idx_hashes_asset ON hashes(asset_id)')
    done = {asset: (stamp, duration) for asset, stamp, duration in database.execute('SELECT asset_id, fingerprint, duration FROM clips')}
    def decode(pair):
        asset_id, entry = pair
        legacy = f"{entry['package_size']}:{entry['package_mtime_ns']}:{entry['offset']}:{entry['size']}"
        stamp = entry.get('sha256', legacy)
        prior_stamp, duration = done.get(asset_id, (None, 0.))
        if prior_stamp in (stamp, legacy) and duration > 0:
            if (pcm_dir/f'{asset_id}.npy').exists() or not .3 <= duration <= 120:
                return asset_id, duration, None, stamp
        try:
            voice = VoiceEntry(Path(entry['package']), entry['offset'], entry['size'], entry['file_id'])
            with tempfile.TemporaryDirectory(prefix='zzz-agent-') as temp:
                wem, wav = Path(temp) / 'voice.wem', Path(temp) / 'voice.wav'
                wem.write_bytes(voice.read())
                subprocess.run([str(decoder), '-o', str(wav), str(wem)], capture_output=True,
                               check=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
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
                if hashes is not None:
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
    print('Complete', database.execute('SELECT COUNT(*) FROM hashes').fetchone(), flush=True)
    database.close()
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
