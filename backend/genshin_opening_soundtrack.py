"""Identify the original Japanese opening soundtrack across publisher releases."""
import hashlib

MOVIE = 'MDAQ001_OPNew_Part1'
TRACKS = {
    (76360448, '1da5ed67345e03d16c9e85f55b581f72'): 'f2897a060e562344ed1c84c57070025ac8dac87055faf3d33b8fbf4899ae6542',
    (76356000, '08762616a03ea6bb6e1d6109da4c4184'): '41818fb0c11491309ebfa08d2762ac7e2cbe98ccb33ae3a305f8daf51cc4b086',
}
MAX_MOVIE = 128 * 1024**2
MAX_TRACK = 8 * 1024**2
JAPANESE_LINES = {
    'genshin:3500404': (24100, 28844, '余所者 お前たちの旅はここまでだ'),
    'genshin:3500405': (30781, 31725, '誰っ！？'),
    'genshin:3500406': (32025, 36986, 'この「天理」の調停者が ここで「人の子」の驕りに終焉を'),
}


def verified_track(asset, directory, expected=None):
    """Read CRI USM audio payloads and require the actual reviewed Japanese HCA."""
    if not 32 <= asset.size <= MAX_MOVIE:
        raise ValueError('Unsupported Genshin opening movie size.')
    movie = b''.join(asset.read(directory, i, min(16 * 1024**2, asset.size - i))
                     for i in range(0, asset.size, 16 * 1024**2))
    if len(movie) != asset.size or movie[:4] != b'CRID' or hashlib.md5(movie).hexdigest() != asset.digest:
        raise ValueError('The Genshin opening movie does not match its publisher manifest.')
    tracks = {}
    pos = 0
    while pos < len(movie):
        if len(movie) - pos < 32:
            raise ValueError('Truncated Genshin movie chunk.')
        end = pos + 8 + int.from_bytes(movie[pos + 4:pos + 8], 'big')
        start = pos + 8 + movie[pos + 9]
        payload_end = end - int.from_bytes(movie[pos + 10:pos + 12], 'big')
        if not pos + 32 <= start <= payload_end <= end <= len(movie):
            raise ValueError('Invalid Genshin movie chunk range.')
        if movie[pos:pos + 4] == b'@SFA' and movie[pos + 15] == 0:
            track = tracks.setdefault(movie[pos + 12], bytearray())
            if len(tracks) > 16 or len(track) + payload_end - start > MAX_TRACK:
                raise ValueError('Unsupported Genshin movie audio layout.')
            track.extend(movie[start:payload_end])
        pos = end
    matches = []
    for track in tracks.values():
        digest = hashlib.sha256(track).hexdigest()
        if track[:4] == b'HCA\0' and digest in TRACKS.values() and (expected is None or digest == expected):
            matches.append((digest, bytes(track)))
    if len(matches) != 1:
        raise ValueError('The verified Japanese opening soundtrack is unavailable.')
    return matches[0]


def binding(asset, directory, stamp):
    if asset is None:
        return None
    digest = TRACKS.get((asset.size, asset.digest))
    if digest is None:
        try:
            digest, _ = verified_track(asset, directory)
        except (OSError, ValueError):
            return None
    return {'publisher': stamp, 'movie': MOVIE, 'locale': 'ja', 'track_sha256': digest}
