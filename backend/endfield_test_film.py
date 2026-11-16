"""Verified Mandarin caption exports from the original Technical Test mixes."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request

from .game_tools import _atomic_file, download
from .media_tools import ffmpeg_executable, vgmstream_executable
from . import endfield_alpha_archive


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

# Each archived WEM has its own time origin, separate from the publisher film.
# Adjacent speech uses shared boundaries, preserving each complete utterance.
ARCHIVE_CUTS = {
    'fmv_e0m1_1_01': (2450, 5050),
    'fmv_e0m1_1_02': (5250, 11900),
    'fmv_e0m1_1_03': (12750, 16150),
    'fmv_e0m1_1_04': (18300, 20550),
    'fmv_e0m1_1_05': (20550, 22300),
    'fmv_e0m1_1_06': (23250, 27600),
    'fmv_e0m1_3_01': (55400, 58200),
    'fmv_e0m1_3_02': (61700, 62550),
    'fmv_e0m1_3_03': (63000, 65400),
    'fmv_e0m1_3_04': (66350, 68250),
    'fmv_e0m1_3_05-1': (68400, 70050),
    'fmv_e0m1_3_05-2': (70050, 75100),
    'fmv_e0m1_3_05-3': (75200, 77250),
    'fmv_e0m1_3_06': (80000, 87400),
    'fmv_e0m1_3_07': (88750, 90550),
    'fmv_e0m1_3_08': (90550, 94650),
    'fmv_e0m1_3_09': (94900, 100800),
    'fmv_e0m1_3_10': (100800, 104000),
    'fmv_e0m1_3_11-1': (104350, 109750),
    'fmv_e0m1_3_11-2': (109950, 112750),
    'fmv_e0m1_3_12': (113450, 118750),
    'fmv_e0m1_3_13': (118900, 119850),
    'fmv_e0m1_3_14': (120100, 124800),
    'fmv_e0m1_3_15': (126200, 131900),
    'timeline_e1m1_1_01': (0, 2400),
    'timeline_e1m1_1_03': (18700, 22400),
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
    for key, (start, end) in ARCHIVE_CUTS.items():
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
    if caption not in {FILM + '_' + suffix for suffix in CUTS} | set(ARCHIVE_CUTS):
        raise ValueError('Unknown Technical Test caption for this recording.')
    record = lines(cache)[caption]
    ffmpeg = ffmpeg_executable()
    if not ffmpeg:
        raise ValueError('Prepare FFmpeg to export the original film mix.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        if caption in ARCHIVE_CUTS:
            decoder = vgmstream_executable()
            if not decoder:
                raise ValueError('Prepare the original voice decoder in Setup to export archived film captions.')
            _, audio = endfield_alpha_archive.recording(cache, caption.rsplit('_', 1)[0], 'zh-Hans')
            wem = Path(folder) / 'original.wem'
            wem.write_bytes(audio)
            movie = Path(folder) / 'original.wav'
            subprocess.run([str(decoder), '-o', str(movie), '-i', str(wem)], check=True, timeout=90,
                           stdout=subprocess.DEVNULL)
        else:
            movie = _movie(cache)
        clip = Path(folder) / 'clip.mp3'
        start, end = record['start_ms'], record['end_ms']
        subprocess.run([str(ffmpeg), '-v', 'error', '-nostdin', '-ss', str(start / 1000),
                        '-i', str(movie), '-map', '0:a:0', '-t', str((end - start) / 1000),
                        '-codec:a', 'libmp3lame', '-q:a', '2', str(clip)], check=True, timeout=90)
        if clip.stat().st_size < 100:
            raise ValueError('The publisher briefing yielded no audio.')
        clip.replace(destination)
    return record
