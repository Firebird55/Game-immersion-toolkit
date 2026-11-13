"""Verified Mandarin soundtrack for the Technical Test's Talos-II briefing."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

from .game_tools import _atomic_file, download
from .media_tools import ffmpeg_executable


FILM = 'fmv_e0m1_4'
VIDEO = 'https://web.hycdn.cn/upload/video/20251030/d836cdada37b16eabbbdd372ed3cf809.mp4'
SIZE = 196340927
SHA256 = '11dfb2ff2735668f570e3b030b50cd3b18aaf7e14e274684ddc8fb76e405914f'
SUBTITLES = ('https://raw.githubusercontent.com/lsy-404/EndfieldGameData/'
             '89ba7929f7fa64579852326b2bed0e679c3ccf49/TableCfg/SubtitleTable.json')
TEXT_SHA256 = '20161d77128e3c6a06a3c53fbad3a0bd94f26322e0d333b5aa2185aae12282cd'
TEXT_SIZE = 14970

# Recording-relative export windows including the spoken lead-in and decay.
# The public film redistributes words across display cues in 03 and 09. Its
# two caption fragments for 04-2 and 10 each belong to one game sentence.
CUTS = {
    '01': (4450, 8050), '02': (8500, 15800),
    '03-1': (17300, 22900), '03-2': (23000, 30500),
    '04-1': (31000, 36200), '04-2': (36400, 45600),
    '05': (47300, 57400), '06-1': (57800, 66000),
    '06-2': (66500, 72300), '07': (72700, 78300), '08': (78400, 84200),
    '09-1': (86500, 90600), '09-2': (90900, 97560), '09-3': (97560, 99600),
    '10': (100400, 109300), '11': (110600, 118000),
    '13': (119900, 124300), '14': (124400, 132700),
    '15-1': (133600, 138600), '15-2': (138700, 145000), '16': (145700, 149400),
}


def lines(cache):
    path = cache / 'endfield-history' / (TEXT_SHA256 + '.json')
    data = path.read_bytes() if path.is_file() and path.stat().st_size == TEXT_SIZE else b''
    if hashlib.sha256(data).hexdigest() != TEXT_SHA256:
        data = download(SUBTITLES, limit=TEXT_SIZE)
        if hashlib.sha256(data).hexdigest() != TEXT_SHA256:
            raise ValueError('The archived Endfield subtitles changed.')
        _atomic_file(path, data)
    source = json.loads(data)
    rows = {}
    for suffix, (start, end) in CUTS.items():
        key = FILM + '_' + suffix
        rows[key] = {'text': source[key]['subtitleText']['text'], 'start_ms': start, 'end_ms': end}
    return rows


def _movie(cache):
    root = cache / 'endfield-history'
    root.mkdir(parents=True, exist_ok=True)
    path = root / (SHA256 + '.mp4')
    if path.is_file() and path.stat().st_size == SIZE:
        with path.open('rb') as saved:
            if hashlib.file_digest(saved, 'sha256').hexdigest() == SHA256:
                return path
    with tempfile.TemporaryDirectory(dir=root) as folder:
        temp = Path(folder) / 'movie.mp4'
        digest = hashlib.sha256()
        count = 0
        with urllib.request.urlopen(VIDEO, timeout=90) as stream, temp.open('wb') as out:
            while chunk := stream.read(min(1024 * 1024, SIZE + 1 - count)):
                count += len(chunk)
                if count > SIZE:
                    raise ValueError('The publisher briefing exceeds its verified size.')
                digest.update(chunk)
                out.write(chunk)
        if count != SIZE or digest.hexdigest() != SHA256:
            raise ValueError('The publisher briefing does not match the Technical Test gameplay.')
        temp.replace(path)
    return path


def export(cache, caption, destination):
    if caption not in {FILM + '_' + suffix for suffix in CUTS}:
        raise ValueError('Unknown Technical Test caption for this recording.')
    record = lines(cache)[caption]
    movie = _movie(cache)
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise ValueError('Prepare FFmpeg to export the original film mix.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        clip = Path(folder) / 'clip.mp3'
        start, end = record['start_ms'], record['end_ms']
        subprocess.run([str(ffmpeg), '-v', 'error', '-nostdin', '-ss', str(start / 1000),
                        '-i', str(movie), '-map', '0:a:0', '-t', str((end - start) / 1000),
                        '-codec:a', 'libmp3lame', '-q:a', '2', str(clip)], check=True, timeout=90)
        if clip.stat().st_size < 100:
            raise ValueError('The publisher briefing yielded no audio.')
        clip.replace(destination)
    return record
