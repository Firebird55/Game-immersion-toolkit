"""Replay locally acquired gameplay through production OCR/capture, off screen.

Usage: python scripts/replay-video-ocr.py MANIFEST --resolution 1920x1080
Manifest clips contain game, path, start, duration, player_voice and manually
reviewed expected/excluded text IDs. Media/indexes stay on the owner's machine.
Only the frame source and audio job sink are replaced: native OneOCR, matching,
confirmation, freshness, deduplication and transcript storage are production.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from oneocr import OcrEngine
from backend.capture import CaptureService
from backend.config import SettingsStore
from backend.local_game import LocalGameTextIndex
from backend.media_tools import ffmpeg_executable
from backend.models import AppSettings
from backend.storage import TranscriptStore
from backend.windows import WindowInfo


class ReplayStore(TranscriptStore):
    @contextmanager
    def _connect(self):
        # Explicitly close each temporary SQLite handle on Windows. Production
        # persistence and transaction behavior remain in TranscriptStore.
        connection = super()._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def replay(clip, resolution, data_dir, fps=2):
    game = clip['game']
    index = LocalGameTextIndex(game, data_dir / game)
    index.player_voice = clip.get('player_voice', 'unconfigured')
    assert index.ready and index.audio_count, f'{game}: installed Mandarin index required'
    payload = json.loads(index.path.read_text(encoding='utf-8'))
    mapped = {r['text_id'] for r in payload['records'] if r.get('audio')}
    scheduled = []
    with tempfile.TemporaryDirectory(prefix='game-video-ocr-') as scratch:
        folder = Path(scratch)
        command = [str(ffmpeg_executable()), '-hide_banner', '-loglevel', 'error',
                   '-ss', str(clip.get('start', 0)), '-i', str(Path(clip['path']).resolve()),
                   '-t', str(clip['duration']), '-vf', f'fps={fps}', str(folder / 'frame-%05d.png')]
        subprocess.run(command, check=True, capture_output=True, timeout=120)
        settings = SettingsStore(folder / 'settings.json')
        settings.save(AppSettings(auto_start=False, stable_frames=2,
                                  **clip.get('settings', {})))
        async def ignore(*_):
            pass
        service = CaptureService(settings, index, None, ReplayStore(folder / 'transcript.db'),
                                 ignore, ignore, ignore, folder / 'audio',
                                 game_indexes={game: index},
                                 game_voice_assets={game: SimpleNamespace(has_variant=lambda text_id, *_: text_id in mapped)})
        # Collect original-asset requests; never record sound or write an account.
        service._schedule_line_audio = lambda line, *_args, **_kwargs: scheduled.append(line)
        engine = OcrEngine()
        window = WindowInfo(0, clip['game'], '', (0, 0, *resolution))
        origin = datetime.now(timezone.utc)
        frame_count = 0
        emitted = []
        try:
            for n, path in enumerate(sorted(folder.glob('frame-*.png'))):
                with Image.open(path) as original:
                    screen = original.convert('RGB').resize(resolution, Image.Resampling.LANCZOS)
                service._capture = lambda bounds: screen.crop((bounds[0], bounds[1], bounds[0]+bounds[2], bounds[1]+bounds[3]))
                # Replay time rather than CPU speed controls freshness/cooldown.
                with patch('backend.capture.time.monotonic', return_value=n / fps):
                    outcome = service._scan_pragmata(window, getattr(settings.get(), f'{game}_region'),
                                                    engine, 0, origin + timedelta(seconds=n / fps), game=game)
                emitted.extend(outcome.emitted_lines)
                frame_count += 1
        finally:
            service._executor.shutdown()
        actual = {line.text_id for line in emitted}
        assert set(clip.get('expected', [])) <= actual, f"{clip['name']}: missed {set(clip.get('expected', []))-actual}"
        assert not set(clip.get('excluded', [])) & actual, f"{clip['name']}: false voice {set(clip.get('excluded', [])) & actual}"
        assert all(line.text_id in mapped for line in scheduled)
        assert len(scheduled) == len(emitted), 'Each accepted line queues its own original asset'
        if 'allowed_channels' in clip:
            assert {line.channel for line in emitted} <= set(clip['allowed_channels'])
        return {'name': clip['name'], 'game': game, 'source_url': clip.get('source_url'),
                'resolution': resolution, 'fps': fps, 'frames': frame_count, 'emitted': len(emitted),
                'ids': sorted(actual), 'channels': sorted({line.channel for line in emitted})}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--resolution', default='1920x1080')
    parser.add_argument('--fps', type=int, choices=[2, 4], default=2)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, default=Path('output/video-ocr.json'))
    args = parser.parse_args()
    resolution = tuple(map(int, args.resolution.split('x')))
    assert len(resolution) == 2 and min(resolution) > 0
    results = []
    for clip in json.loads(args.manifest.read_text(encoding='utf-8'))['clips']:
        result = replay(clip, resolution, args.data_dir, args.fps)
        results.append(result)
        print(json.dumps(result), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
