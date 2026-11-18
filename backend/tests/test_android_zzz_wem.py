import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import wave
import zipfile

import pytest

from backend.android_zzz_wem import SCHEMA, SOURCES, create_android_zzz_codecs
from backend.game_data_protocol import GameDataError
from backend.tests.test_zzz_wav_codec import wem

ROOT = Path(__file__).resolve().parents[2]


def accepted_proof():
    return {'schema':SCHEMA, 'abi':'arm64-v8a', 'source_sha256':SOURCES, 'library_sha256':'1' * 64,
            'manifest_sha256':'2' * 64, 'apk_entry_verified':True, 'notices_verified':True,
            'system_fallback':False, 'max_wem_bytes':64 * 1024**2, 'max_frames_per_read':4096}


class AuthoredJava:
    def __init__(self, result):
        self.result = result
        self.closed = False
        self.calls = []

    def proof(self):
        return json.dumps(self.result)

    def begin(self, raw, channels, rate, frames):
        assert raw == wem(channels=1, rate=48000, frames=3)
        assert (channels, rate, frames) == (1, 48000, 3)
        return self

    def readFrames(self, frames):
        self.calls.append(frames)
        return [-1, -128, 1, 0, 2, 0] if frames == 3 else []

    def close(self):
        self.closed = True


def test_approved_host_ticket_decodes_through_public_portable_wav_path(tmp_path, monkeypatch):
    def jclass(name):
        assert name == 'io.github.firebird55.gameimmersiontoolkit.ZzzWemCodec'
        return AuthoredJava
    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=jclass))
    java = AuthoredJava(accepted_proof())
    codec = create_android_zzz_codecs(SimpleNamespace(zzzWemCodec=lambda: java))
    assert codec.identity == SCHEMA + ':' + '2' * 64
    path = codec.resolve(wem(channels=1, rate=48000, frames=3), {'audio_scope':'context'}, tmp_path / 'original',
                         cancelled=lambda: False)
    with wave.open(str(path), 'rb') as stream:
        assert stream.getframerate() == 48000 and stream.getnframes() == 3
        assert stream.readframes(3) == b'\xff\x80\x01\x00\x02\x00'
    assert java.closed and java.calls == [3, 1]


@pytest.mark.parametrize('kind', ['missing', 'wrong-type', 'changed-library', 'unreviewed-source', 'missing-notice'])
def test_missing_or_changed_android_capability_has_no_desktop_fallback(monkeypatch, kind):
    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=lambda name: AuthoredJava))
    proof = accepted_proof()
    if kind == 'changed-library':
        proof.pop('library_sha256')
    if kind == 'unreviewed-source':
        proof['source_sha256'] = {}
    if kind == 'missing-notice':
        proof['notices_verified'] = False
    native = None if kind == 'missing' else SimpleNamespace(zzzWemCodec=lambda: (
        object() if kind == 'wrong-type' else AuthoredJava(proof)))
    with pytest.raises(GameDataError) as error:
        create_android_zzz_codecs(native)
    assert error.value.code == 'zzz_audio_runtime_missing'


def test_android_download_passes_the_installed_codec_and_gateway_to_original_audio(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from backend import zzz_pc_audio, zzz_pc_stages
    from backend.game_data_protocol import GameDataPlan, GameDataRequest
    from backend.sophon_assets import descriptor
    from backend.zzz_game_data import ZzzGameDataProvider

    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=lambda name: AuthoredJava))
    native = SimpleNamespace(zzzWemCodec=lambda: AuthoredJava(accepted_proof()))
    provider = ZzzGameDataProvider(platform='android', native=native)
    reader = SimpleNamespace(identity='authored-android-catalogue')
    crypto = object()
    monkeypatch.setattr(provider, '_reader', lambda: reader)
    monkeypatch.setattr(provider, '_android_gateway', lambda: crypto)
    selection = GameDataRequest('global', 'en', content_mode='text-audio')
    build = {'channel': 'zzz-global', 'version': '3.3.0', 'build': 'authored-audio'}
    revision = descriptor(build)[0]
    handle = {'schema': zzz_pc_stages.SCHEMA, 'mode': 'audio-recordings', 'request': selection.json(),
              'reader': reader.identity, 'revision': revision, 'build': build}
    plan = GameDataPlan(revision, 0, 0, handle=handle, runtime_available=True, stage=handle['mode'])
    ctx = SimpleNamespace(request=selection, cache_directory=tmp_path, transfer_lock=nullcontext())
    accepted = object()

    def download(context, planned, selected_reader, codec, **options):
        assert context is ctx and planned is plan and selected_reader is reader
        assert codec.identity == SCHEMA + ':' + '2' * 64
        assert options['crypto'] is crypto
        assert options['verify_current'] is zzz_pc_stages._verify_current
        return accepted

    monkeypatch.setattr(zzz_pc_audio, 'download', download)
    assert provider.download(plan, ctx) is accepted


def apk_audit():
    spec = importlib.util.spec_from_file_location('authored_zzz_wem_apk_audit', ROOT / 'scripts/verify-android-apk.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_apk_auditor_distinguishes_absence_from_an_incomplete_software_namespace():
    audit = apk_audit()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        assert audit.verify_zzz_wem_component(archive, ROOT) == {'present': False}
        archive.writestr('lib/x86_64/libtoolkit_zzz_wem.so', b'partial')
        with pytest.raises(ValueError, match='namespace is incomplete'):
            audit.verify_zzz_wem_component(archive, ROOT)


@pytest.mark.parametrize('mutation', ['exact', 'changed-so', 'changed-license', 'compressed-so'])
def test_actual_native_codec_bundle_in_apk_auditor(mutation):
    bundle = os.environ.get('TOOLKIT_ZZZ_WEM_BUNDLE')
    if not bundle:
        pytest.skip('The verified native Android WEM software build is required')
    bundle = Path(bundle)
    audit = apk_audit()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for folder in ('assets', 'jniLibs'):
            for path in (bundle / folder).rglob('*'):
                if not path.is_file():
                    continue
                name = path.relative_to(bundle).as_posix().replace('jniLibs/', 'lib/', 1)
                data = path.read_bytes()
                method = zipfile.ZIP_STORED
                if name.startswith('lib/x86_64/'):
                    if mutation == 'changed-so':
                        data = data[:-1] + bytes([data[-1] ^ 1])
                    if mutation == 'compressed-so':
                        method = zipfile.ZIP_DEFLATED
                if mutation == 'changed-license' and name.endswith('libogg-COPYING'):
                    data += b'changed'
                archive.writestr(name, data, compress_type=method)
    with zipfile.ZipFile(stream) as archive:
        if mutation == 'exact':
            proof = audit.verify_zzz_wem_component(archive, ROOT)
            assert proof['present'] and set(proof['libraries']) == {'arm64-v8a', 'x86_64'}
            assert proof['manifest_sha256'] == hashlib.sha256((bundle / 'assets/zzz-wem-manifest.json').read_bytes()).hexdigest()
        else:
            with pytest.raises(ValueError):
                audit.verify_zzz_wem_component(archive, ROOT)
