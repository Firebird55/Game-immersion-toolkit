"""Authored shared-core fixture run unchanged on desktop and embedded Android."""
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import wave
import sys
import time

from .prepared_library import write_prepared_library
from .prepared_session import PreparedCaptureSession

TEXT = 'Follow the river beyond the bridge.'


def _library(root, text=TEXT, identity='authored:bridge', *, duration=0.2):
    root.mkdir(parents=True, exist_ok=True)
    clip = root / 'authored-tone.wav'
    with wave.open(str(clip), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        if not 0 < duration <= 10:
            raise ValueError('Authored fixture duration is outside its bound')
        output.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(round(16000 * duration))))
    row = dict(text_id=identity, english=text, chinese='沿河走过桥。', source_locale='en',
        source_text=text, texts={'en': text, 'zh-Hans': '沿河走过桥。'}, audio_locale='en',
        audio={'authored-fixture': True}, voice_status='voiced', dialogue_kind='conversation')
    snapshot = dict(format=2, game='zzz', source_locale='en', records=[row])
    return write_prepared_library(snapshot, root / 'library.zip', {identity: clip})


def run(root):
    root = Path(root);root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='shared-core-', dir=root))
    library = _library(work / 'original')
    session = PreparedCaptureSession(work / 'application')
    session.import_library(library)
    generation = session.start()
    first = session.observe(generation, 1, [TEXT], now=1)
    replay = session.observe(generation, 1, [TEXT], now=1.01)
    confirmed = session.observe(generation, 2, [TEXT], now=1.02)
    if len(confirmed) != 1:
        raise ValueError('Shared confirmation fixture failed')
    identity = confirmed[0]['id']
    audio = session.audio_path(identity)
    original_pcm = audio.read_bytes()
    session.history.set_favorite(identity, True)
    session.stop()
    late = session.observe(generation, 3, [TEXT], now=1.03)
    pointer = session.libraries.pointer.read_bytes()
    cancelled = False
    try:
        session.import_library(library, cancelled=lambda: True)
    except InterruptedError:
        cancelled = session.libraries.pointer.read_bytes() == pointer
    broken = work / 'broken.zip';broken.write_bytes(b'not a library')
    rejected = False
    try:
        session.import_library(broken)
    except Exception:
        rejected = session.libraries.pointer.read_bytes() == pointer
    newer = _library(work / 'new', 'The new chapter follows the river.', 'authored:new')
    session.import_library(newer)
    restarted = PreparedCaptureSession(work / 'application')
    retained = restarted.history.get(identity)
    results = {'first_frame_waited': first == [], 'replayed_frame_rejected': replay == [],
        'confirmed_text_id': confirmed[0]['text_id'], 'confirmed_source_locale': confirmed[0]['source_locale'],
        'confirmed_voice_status': confirmed[0]['voice_status'], 'original_audio_source': confirmed[0]['audio_source'],
        'late_result_rejected': late == [], 'cancelled_import_preserved': cancelled,
        'corrupt_import_preserved': rejected, 'restart_is_stopped': not restarted.running,
        'history_retained': restarted.history.count() == 1, 'favorite_retained': retained.favorite,
        'old_recording_sha256': hashlib.sha256(restarted.audio_path(identity).read_bytes()).hexdigest(),
        'recording_retained': restarted.audio_path(identity).read_bytes() == original_pcm,
        'new_generation_text_id': restarted.index._records[0]['text_id']}
    if any(value is False for value in results.values()):
        raise ValueError('Shared lifecycle fixture failed')
    encoded = json.dumps(results, sort_keys=True, separators=(',', ':')).encode()
    from rapidfuzz import fuzz, process
    import rapidfuzz
    import pydantic_core
    choices = ['A publisher authored dialogue near the mountain checkpoint ' + str(number) for number in range(50000)]
    started = time.perf_counter()
    process.extract('A publisher auth0red dialogue near the mountain checkpoint 49999', choices,
        scorer=fuzz.ratio, score_cutoff=88, limit=2)
    fuzzy_ms = (time.perf_counter() - started) * 1000
    return json.dumps({'schema': 'toolkit-android-shared-core-probe-v1', 'results': results,
        'result_sha256': hashlib.sha256(encoded).hexdigest(), 'fixture': 'authored-text-and-generated-tone',
        'runtime': {'python': sys.version.split()[0], 'pydantic_core': pydantic_core.__version__,
            'rapidfuzz': rapidfuzz.__version__, 'fuzzy_scorer': fuzz.ratio.__module__,
            'fuzzy_extractor': process.extract.__module__, 'authored_fuzzy_50000_ms': fuzzy_ms},
        'private_audio_path': str(restarted.audio_path(identity))}, sort_keys=True)


def run_ocr(root, raw):
    """Feed actual bundled native OCR into the unchanged production session."""
    root = Path(root);root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='native-ocr-', dir=root))
    blocks = json.loads(raw)['blocks']
    observed = [block['text'] for block in blocks]
    session = PreparedCaptureSession(work / 'application')
    session.import_library(_library(work / 'original'))
    generation = session.start()
    first = session.observe(generation, 1, observed, now=1)
    confirmed = session.observe(generation, 2, observed, now=1.1)
    if first or len(confirmed) != 1 or confirmed[0]['text_id'] != 'authored:bridge':
        raise ValueError('Native OCR did not match the authored shared-core fixture')
    return json.dumps({'fixture': 'authored-native-bitmap', 'confirmed_text_id': confirmed[0]['text_id'],
        'voice_status': confirmed[0]['voice_status'], 'original_audio_available': session.audio_path(confirmed[0]['id']).is_file()})
