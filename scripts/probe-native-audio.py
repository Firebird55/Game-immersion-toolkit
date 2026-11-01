"""Decode authored audio with the packaged codec bytes and no developer PATH."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.native_codecs import PREFIX, SCHEMA, host_target
from backend.runtime_bundle import relative_resource


def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def probe(resources, output):
    root = resources / PREFIX
    manifest = json.loads((root / 'runtime.json').read_text())
    if manifest['schema'] != SCHEMA or manifest['target'] != host_target(): raise ValueError('Wrong codec target')
    if set(manifest['tools']) != {'ffmpeg', 'vgmstream'}:
        raise ValueError('The desktop audio bundle must include both codec tools')
    expected = manifest['files']
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected) | {'runtime.json'}: raise ValueError('Codec inventory is not closed')
    for name, digest in expected.items():
        path = root / relative_resource(name)
        if any(p.is_symlink() or (p.exists() and getattr(p.lstat(), 'st_file_attributes', 0) & 0x400) for p in (path, *path.parents)):
            raise ValueError('Linked codec input')
        if sha(path) != digest: raise ValueError('Codec resource checksum failed')
    env = {name: value for name, value in os.environ.items() if name.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir', 'lang', 'lc_all'}}
    env['PATH'] = os.environ.get('SystemRoot', '') + '/System32' if sys.platform == 'win32' else '/usr/bin:/bin'
    checks = {}
    with tempfile.TemporaryDirectory(prefix='toolkit-authored-codec-') as temporary:
        work = Path(temporary)
        pcm = b''.join(struct.pack('<h', round(math.sin(i * math.tau * 440 / 16000) * 12000)) for i in range(16000))
        original = work / 'authored.wav'
        with wave.open(str(original), 'wb') as stream:
            stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed')); stream.writeframes(pcm)
        def run(tool, arguments):
            name = manifest['tools'][tool]
            if name != ('ffmpeg' if tool == 'ffmpeg' else 'vgmstream-cli') + ('.exe' if sys.platform == 'win32' else ''):
                raise ValueError('Unexpected codec entry')
            return subprocess.run([str(root / name), *map(str, arguments)], cwd=work, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=True)
        if 'ffmpeg' in manifest['tools']:
            run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', original, '-c:a', 'flac', work / 'authored.flac'])
            run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', work / 'authored.flac', '-c:a', 'pcm_s16le', '-f', 's16le', work / 'decoded.pcm'])
            checks['ffmpeg_lossless_pcm'] = (work / 'decoded.pcm').read_bytes() == pcm
            run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', original, '-codec:a', 'libmp3lame', '-q:a', '2', work / 'authored.mp3'])
            run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', work / 'authored.mp3', '-ar', '8000', '-c:a', 'pcm_s16le', '-f', 's16le', work / 'resampled.pcm'])
            checks['ffmpeg_mp3_resample'] = 14000 <= (work / 'resampled.pcm').stat().st_size <= 18000
            run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', original, '-filter_complex',
                '[0:a]aformat=channel_layouts=stereo,volume=-1dB,adelay=10:all=1,atrim=start=0.1:end=0.5,asetpts=PTS-STARTPTS[out]',
                '-map', '[out]', '-codec:a', 'libmp3lame', '-q:a', '2', work / 'filtered.mp3'])
            checks['ffmpeg_dialogue_filters'] = (work / 'filtered.mp3').stat().st_size > 100
        if 'vgmstream' in manifest['tools']:
            run('vgmstream', ['-o', work / 'vgm-decoded.wav', original])
            with wave.open(str(work / 'vgm-decoded.wav'), 'rb') as stream:
                checks['vgmstream_authored_riff'] = stream.getframerate() == 16000 and stream.readframes(stream.getnframes()) == pcm
            run('vgmstream', ['-o', work / 'vgm-flac.wav', work / 'authored.flac'])
            with wave.open(str(work / 'vgm-flac.wav'), 'rb') as stream:
                checks['vgmstream_authored_flac'] = stream.getframerate() == 16000 and stream.readframes(stream.getnframes()) == pcm
            run('vgmstream', ['-o', work / 'vgm-mp3.wav', work / 'authored.mp3'])
            with wave.open(str(work / 'vgm-mp3.wav'), 'rb') as stream:
                checks['vgmstream_authored_mpeg'] = stream.getframerate() == 16000 and 15000 <= stream.getnframes() <= 19000
            if sys.platform in {'linux', 'darwin'}:
                from scripts.audio_runtime_posix import inspect_dynamic_dependencies
                dependencies = {tool: inspect_dynamic_dependencies(root / manifest['tools'][tool]) for tool in manifest['tools']}
                checks['system_runtime_libraries_only'] = bool(dependencies)
                run('ffmpeg', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', original,
                              '-c:a', 'libopus', work / 'authored.ogg'])
                run('vgmstream', ['-o', work / 'vgm-opus.wav', work / 'authored.ogg'])
                with wave.open(str(work / 'vgm-opus.wav'), 'rb') as stream:
                    checks['vgmstream_authored_opus'] = stream.getframerate() == 48000 and 47000 <= stream.getnframes() <= 50000
    report = {'schema': 'toolkit-native-audio-probe-v1', 'target': host_target(), 'fixture': 'generated-sine-pcm-no-game-assets',
        'runtime_manifest_sha256': sha(root / 'runtime.json'), 'developer_path_removed': True, 'checks': checks,
        'passed': bool(checks) and all(checks.values()), 'game_audio_acceptance': 'not-tested', 'r19_complete': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(probe(args.resources.absolute(), args.output.absolute()))
