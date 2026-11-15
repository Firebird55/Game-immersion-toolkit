"""Acquire verified original Technical Alpha film recordings without a client."""
import hashlib
from pathlib import Path
import tempfile
import urllib.request
import zlib

from .agent_bank import package_table


URL = ('https://archive.org/download/arknights-endfield-technical-alphawith-hotfix/'
       'Arknights_Endfield_Technical_Alpha%28with_hotfix%29.zip')
ARCHIVE_SIZE = 12047240068
PACKAGES = {
    'en': {'offset': 8038341195, 'compressed': 119094478, 'size': 120034944,
           'sha256': '8e1869fc60779648084aa2337d484f67e8710e77e3a2f822e217e03d4b890a6e'},
    'zh-Hans': {'offset': 2844293546, 'compressed': 105051365, 'size': 105863503,
                'sha256': '51be530994d9bbc2f6e8253a63f9129a4477a6510a3c8b112b59b8b95bfed1eb'},
}
RECORDINGS = {
    'en': {
        'fmv_e0m1_1': (575989014, 'b3044d65ddbb58041382d868fe4df4421fb2f49be9b5a0ba289595b253bf0377'),
        'fmv_e0m1_3': (646125757, '40d8055a4eba246962f2f052941df42c768c9cea2958c86befb4fe0715b58c55'),
        'fmv_e0m1_4': (351625180, '710760c0684563f5169ece2c1cec6daed5b78cbb70452b4ba9a4d0f65fe83ab4'),
    },
    'zh-Hans': {
        'fmv_e0m1_1': (1046408181, 'cc5acb17c7789874963fc93ef5d1fddd8aed90b9aaed2b15ef4dd5b53ad7bccc'),
        'fmv_e0m1_3': (945985728, 'b98ebbf70afbdea8785362a189854c2fcf3592b5f40336f891f4d9579350a6e0'),
        'fmv_e0m1_4': (780870713, 'fe11338ddcae3c9b016f2349235004662503de5c37b56bb2954b2b5b05b6565e'),
    },
}


def inventory(locale):
    locale = 'zh-Hans' if locale == 'zh-Hant' else locale
    if locale not in RECORDINGS:
        raise ValueError('The verified Technical Alpha archive has English and Mandarin recordings.')
    return {film: {'locale': locale, 'media_id': identity, 'sha256': digest}
            for film, (identity, digest) in RECORDINGS[locale].items()}


def _package(cache, locale):
    source = PACKAGES[locale]
    root = cache / 'endfield-history'
    root.mkdir(parents=True, exist_ok=True)
    destination = root / (source['sha256'] + '.pck')
    if destination.is_file() and destination.stat().st_size == source['size']:
        with destination.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == source['sha256']:
                return destination
    start = source['offset']
    end = start + source['compressed'] - 1
    request = urllib.request.Request(URL, headers={
        'Range': f'bytes={start}-{end}', 'User-Agent': 'GameImmersionToolkit/1',
        'Accept-Encoding': 'identity',
    })
    with tempfile.TemporaryDirectory(dir=root) as directory:
        temporary = Path(directory) / 'recording.pck'
        inflater = zlib.decompressobj(-15)
        digest = hashlib.sha256()
        received = expanded = 0
        with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as output:
            if (response.status != 206
                    or response.headers.get('Content-Range') != f'bytes {start}-{end}/{ARCHIVE_SIZE}'):
                raise ValueError('The Technical Alpha archive returned an unexpected byte range.')
            while chunk := response.read(min(1024**2, source['compressed'] + 1 - received)):
                received += len(chunk)
                if received > source['compressed']:
                    raise ValueError('The Technical Alpha package exceeds its verified compressed size.')
                decoded = inflater.decompress(chunk, source['size'] + 1 - expanded)
                expanded += len(decoded)
                if expanded > source['size']:
                    raise ValueError('The Technical Alpha package exceeds its verified expanded size.')
                digest.update(decoded)
                output.write(decoded)
        if (received != source['compressed'] or expanded != source['size']
                or not inflater.eof or inflater.unused_data or inflater.unconsumed_tail
                or digest.hexdigest() != source['sha256']):
            raise ValueError('The archived Technical Alpha package is incomplete or has changed.')
        temporary.replace(destination)
    return destination


def recording(cache, film, locale):
    records = inventory(locale)
    if film not in records:
        raise ValueError('Unknown verified Technical Alpha film.')
    record = records[film]
    package = _package(cache, record['locale'])
    entry = package_table(package, 3).get(record['media_id'])
    if entry is None:
        raise ValueError('The archived film recording is absent from its verified package.')
    data = entry.read()
    if hashlib.sha256(data).hexdigest() != record['sha256']:
        raise ValueError('The archived film recording does not match the verified performance.')
    return record, data
