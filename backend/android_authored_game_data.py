"""Opt-in DEBUG acceptance source; generated fixtures, never publisher evidence.

This provider exercises the ordinary preparation, index, recording and restore
contracts without a PC, imported ZIP, network endpoint or original game files.
Only the native DEBUG startup can install it; production factories never do.
"""
from dataclasses import asdict
import hashlib
import io
import json
import math
import struct
import wave

from .game_data_protocol import GameDataError, GameDataPlan, SnapshotSource, SourceProof
from .local_game import LocalDialogue

TEXT = 'Follow the river beyond the bridge.'
REVISION = 'authored-direct-source-v1'
BINDING = {'publisher': 'authored', 'file_id': 'original-bridge'}


def tone():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        audio.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(2 * math.pi * 440 * i / 16000)))
            for i in range(8 * 16000)))
    return output.getvalue()


def snapshot(request):
    row = asdict(LocalDialogue('authored:bridge', TEXT, '沿河走过桥。', source_locale='en',
        source_text=TEXT, texts={'en': TEXT, 'zh-Hans': '沿河走过桥。'}, audio_locale='en',
        audio=BINDING, ocr_texts={}, voice_status='voiced', dialogue_kind='conversation'))
    if request.content_mode == 'text':
        row.update(source_voice_binding=row['audio'], audio=None, audio_omitted_by_request=True,
            text_capture_verified=True)
    return json.dumps({'format': 2, 'game': 'zzz', 'fingerprint': REVISION,
        'source_locale': 'en', 'content_mode': request.content_mode, 'records': [row]},
        ensure_ascii=False, sort_keys=True).encode('utf8')


class _Voice:
    def __init__(self, path, digest):
        self.path, self.digest = path, digest

    def has(self, row):
        return row.get('audio') == BINDING

    def resolve(self, row, destination, *, cancelled):
        if cancelled() or not self.has(row):
            return None
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != self.digest:
            raise ValueError('The authored original recording changed.')
        if cancelled():
            return None
        path = destination.with_suffix('.wav')
        path.write_bytes(raw)
        return path


class AuthoredGameDataProvider:
    """Generated one-row source with explicit text-only audio omission."""
    title = 'Zenless Zone Zero'

    def plan(self, request, ctx):
        if request.region != 'global' or request.source_locale != 'en':
            raise GameDataError('authored_languages_only', 'This authored fixture uses Global English only.')
        ctx.check()
        text_bytes = len(snapshot(request))
        audio_bytes = len(tone()) if request.content_mode == 'text-audio' else 0
        return GameDataPlan(REVISION, text_bytes + audio_bytes, 65536 + text_bytes + audio_bytes,
            handle={'fixture': REVISION}, runtime_available=True,
            message='Generated DEBUG acceptance fixture; no publisher content or network transfer.')

    def download(self, plan, ctx):
        ctx.check()
        raw = snapshot(ctx.request)
        ctx.consume_bytes(len(raw), kind='asset')
        (ctx.directory / 'textmap.json').write_bytes(raw)
        handle = {'fixture': REVISION, 'text_sha256': hashlib.sha256(raw).hexdigest()}
        if ctx.request.content_mode == 'text-audio':
            audio = tone()
            ctx.consume_bytes(len(audio), kind='audio')
            (ctx.directory / 'original.wav').write_bytes(audio)
            handle['audio_sha256'] = hashlib.sha256(audio).hexdigest()
        return self.restore(handle, ctx)

    def restore(self, handle, ctx):
        ctx.check()
        expected = {'fixture', 'text_sha256'} | ({'audio_sha256'} if ctx.request.content_mode == 'text-audio' else set())
        if set(handle) != expected or handle.get('fixture') != REVISION:
            raise ValueError('Invalid authored source receipt.')
        path = ctx.directory / 'textmap.json'
        raw = path.read_bytes()
        if raw != snapshot(ctx.request) or hashlib.sha256(raw).hexdigest() != handle['text_sha256']:
            raise ValueError('The authored text changed.')
        voice = None
        if ctx.request.content_mode == 'text-audio':
            original = ctx.directory / 'original.wav'
            audio = original.read_bytes()
            if audio != tone() or hashlib.sha256(audio).hexdigest() != handle['audio_sha256']:
                raise ValueError('The authored recording changed.')
            voice = _Voice(original, handle['audio_sha256'])
        # Authored stand-in for the typed contract, NOT official-content proof.
        proof = SourceProof('official', hashlib.sha256((REVISION + handle['text_sha256']).encode()).hexdigest(), True)
        return SnapshotSource(path, handle, proof, voice)


def providers(native):
    if native is None:
        raise ValueError('Authored source startup requires the native DEBUG guard.')
    native.assertAuthoredGameData()
    return {'zzz': AuthoredGameDataProvider()}
