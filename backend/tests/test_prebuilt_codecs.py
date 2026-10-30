"""Codec-specific trust, atomic publication and format failures absent from toolchain refusals.

Synthetic PE bytes and mocked process results are not a native decode pass; the
hosted extracted-runtime probe executes the exact actual artifact separately.
"""
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import threading

import pytest

from backend import prebuilt_codecs as codec, runtime_bundle, media_tools
from backend.codec_fixture import authored_flac, crc
from backend.preparation_errors import PreparationFailure
from backend.preparation_worker import PreparationCancelled
from backend.tests.test_runtime_bundle import frozen_layout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path, monkeypatch):
    layout = frozen_layout(tmp_path, profile='runtime-experiment')
    root = layout.resource_root / codec.PREFIX
    (root / 'notices').mkdir(parents=True)
    pe = bytearray(128); pe[:2] = b'MZ'; pe[60:64] = (64).to_bytes(4, 'little')
    pe[64:70] = b'PE\0\0\x64\x86'; pe[88:90] = b'\x0b\x02'
    for name in codec.PINNED_FILES:
        (root / name).write_bytes(pe if name in {'flac.exe', 'FLAC.dll'} else b'authored license fixture')
    monkeypatch.setattr(codec, 'PINNED_FILES', {name: digest((root / name).read_bytes()) for name in codec.PINNED_FILES})
    manifest = {'schema': codec.SCHEMA, 'kind': 'xiph-flac-experiment', 'version': '1.5.0', 'platform': 'win-x64',
        'source_commit': layout.source_commit, 'source_dirty': False,
        'source_inputs': {name: 'b' * 64 for name in codec.SOURCE_INPUTS}, 'entry': 'flac.exe',
        'archive_sha256': codec.ARCHIVE_SHA256, 'policy': codec.POLICY, 'production_execution_allowed': False,
        'redistribution_review': 'pending-exact-output', 'source_delivery_review': codec.SOURCE_REVIEW, 'servicing_review': codec.SERVICING_REVIEW,
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
    return layout, root, manifest


def seal(layout, root, manifest):
    manifest['files'] = {name: {'bytes': (root / name).stat().st_size, 'sha256': digest((root / name).read_bytes())}
        for name in codec.PINNED_FILES if (root / name).is_file()}
    manifest['build_id'] = codec.identity(manifest['files'])
    (root / 'codec-manifest.json').write_text(json.dumps(manifest))
    return replace(layout, resources={codec.PREFIX + path.relative_to(root).as_posix(): digest(path.read_bytes())
        for path in root.rglob('*') if path.is_file()})


@pytest.mark.parametrize('change', ['missing-notice', 'extra-file', 'empty-directory', 'unbound', 'dirty-source',
    'wrong-source', 'rights-approved', 'source-approved', 'servicing-approved', 'production-approved',
    'wrong-archive', 'wrong-policy', 'changed-executable', 'wrong-pe', 'missing-dll', 'changed-dll', 'old-codec'])
def test_incomplete_or_promoted_codec_cannot_resolve(tmp_path, monkeypatch, change):
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    if change == 'missing-notice': (root / 'notices/COPYING.GPL').unlink()
    elif change == 'extra-file': (root / 'unreviewed.dll').write_bytes(b'not collected')
    elif change == 'empty-directory': (root / 'unexpected').mkdir()
    elif change == 'dirty-source': manifest['source_dirty'] = True
    elif change == 'wrong-source': manifest['source_commit'] = 'c' * 40
    elif change == 'rights-approved': manifest['redistribution_review'] = 'approved'
    elif change == 'source-approved': manifest['source_delivery_review'] = 'approved'
    elif change == 'servicing-approved': manifest['servicing_review'] = 'approved'
    elif change == 'production-approved': manifest['production_execution_allowed'] = True
    elif change == 'wrong-archive': manifest['archive_sha256'] = '0' * 64
    elif change == 'wrong-policy': manifest['policy'] = {**codec.POLICY, 'operation': 'arbitrary-ffmpeg'}
    elif change == 'missing-dll': (root / 'FLAC.dll').unlink()
    elif change == 'changed-dll': (root / 'FLAC.dll').write_bytes(b'wrong sibling')
    elif change == 'old-codec': manifest['kind'], manifest['version'] = 'ffmpeg-flac-experiment', '7.1'
    elif change in {'wrong-pe', 'changed-executable'}:
        (root / 'flac.exe').write_bytes(b'not a PE' + b'\0' * 121)
        if change == 'wrong-pe': monkeypatch.setitem(codec.PINNED_FILES, 'flac.exe', digest((root / 'flac.exe').read_bytes()))
    layout = seal(layout, root, manifest)
    if change == 'unbound': layout = replace(layout, resources={})
    with pytest.raises(PreparationFailure): codec.prebuilt_flac_decoder(layout=layout)
    assert not layout.work_root.exists()


def test_codec_cannot_enable_general_ffmpeg_or_other_profiles(tmp_path, monkeypatch):
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    layout = seal(layout, root, manifest)
    assert media_tools.experimental_flac_decoder(layout=layout).executable == root / 'flac.exe'
    for profile in ['runtime', 'diagnostic', 'frontend-experiment', 'source']:
        with pytest.raises(PreparationFailure, match='quarantined'):
            codec.prebuilt_flac_decoder(layout=replace(layout, profile=profile))
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda *_: pytest.fail('Frozen adapter searched PATH'))
    media_tools.ffmpeg_executable.cache_clear()
    try: assert media_tools.ffmpeg_executable() is None
    finally: media_tools.ffmpeg_executable.cache_clear()


@pytest.mark.parametrize('outcome', ['pass', 'bad-exit', 'wrong-size', 'timeout', 'cancel-after-decode'])
def test_fixed_decode_has_atomic_publication_and_owned_job_contract(tmp_path, monkeypatch, outcome):
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    layout = seal(layout, root, manifest)
    folder = layout.work_root / 'owned'; folder.mkdir(parents=True)
    source, output = folder / 'input.flac', folder / 'output.pcm'
    data, pcm = authored_flac(); source.write_bytes(data); output.write_bytes(b'previous complete output')
    monkeypatch.setenv('WINDIR', 'C:\\Windows')
    monkeypatch.setenv('FFREPORT', 'private-account-setting')
    cancelled = threading.Event()
    def run(job, command, *, cwd, timeout, env):
        assert command[0] == str(root / 'flac.exe') and '--decode' in command
        assert '--until=512' in command and '--force-raw-format' in command
        assert '--endian=little' in command and '--sign=signed' in command
        assert command[-2:] == ['--', str(source)] and '--apply-replaygain' not in command
        pending = Path(next(x.split('=', 1)[1] for x in command if x.startswith('--output-name=')))
        assert pending.parent == cwd and cwd.parent == folder
        assert env['PROXY_TRANSCRIPT_WORK_ROOT'] == str(layout.work_root)
        assert env['PYINSTALLER_RESET_ENVIRONMENT'] == '1' and 'FFREPORT' not in env
        if outcome == 'timeout': raise subprocess.TimeoutExpired(command, timeout)
        pending.write_bytes(b'wrong' if outcome == 'wrong-size' else pcm)
        if outcome == 'cancel-after-decode': cancelled.set()
        return 2 if outcome == 'bad-exit' else 0
    monkeypatch.setattr(codec.PreparationJob, 'run', run)
    decoder = codec.prebuilt_flac_decoder(layout=layout)
    if outcome == 'pass':
        assert decoder.decode(source, output)['pcm_sha256'] == digest(pcm)
        assert output.read_bytes() == pcm
    else:
        with pytest.raises((PreparationFailure, subprocess.TimeoutExpired, PreparationCancelled)):
            decoder.decode(source, output, cancelled=cancelled)
        assert output.read_bytes() == b'previous complete output'
    assert source.read_bytes() == data and sorted(p.name for p in folder.iterdir()) == ['input.flac', 'output.pcm']


def test_pre_cancelled_decode_creates_no_attempt_or_output(tmp_path, monkeypatch):
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    decoder = codec.prebuilt_flac_decoder(layout=seal(layout, root, manifest))
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(PreparationCancelled): decoder.decode(tmp_path / 'missing', tmp_path / 'other', cancelled=cancelled)
    assert not layout.work_root.exists()


def test_codec_cannot_write_outside_work_or_use_ads_names(tmp_path, monkeypatch):
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    decoder = codec.prebuilt_flac_decoder(layout=seal(layout, root, manifest))
    folder = layout.work_root / 'owned'; folder.mkdir(parents=True)
    source = folder / 'input.flac'; source.write_bytes(authored_flac()[0])
    for output in (tmp_path / 'external.pcm', folder / 'result:stream', source):
        with pytest.raises((PreparationFailure, runtime_bundle.RuntimeBundleError)): decoder.decode(source, output)
    assert list(folder.iterdir()) == [source]


@pytest.mark.parametrize('rate,channels,bits,samples', [(44100,1,16,512), (16000,2,16,512),
    (16000,1,24,512), (16000,1,16,0), (16000,1,16,16001)])
def test_metadata_cannot_expand_the_bounded_decode_scope(tmp_path, monkeypatch, rate, channels, bits, samples):
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    decoder = codec.prebuilt_flac_decoder(layout=seal(layout, root, manifest))
    folder = layout.work_root / 'owned'; folder.mkdir(parents=True)
    source, output = folder / 'input.flac', folder / 'previous.pcm'
    data = bytearray(authored_flac()[0])
    data[18:26] = ((rate<<44) | ((channels-1)<<41) | ((bits-1)<<36) | samples).to_bytes(8, 'big')
    source.write_bytes(data); output.write_bytes(b'keep')
    monkeypatch.setattr(codec.PreparationJob, 'run', lambda *_a, **_k: pytest.fail('Invalid scope executed a codec'))
    with pytest.raises(PreparationFailure, match='at most one second'): decoder.decode(source, output)
    assert output.read_bytes() == b'keep'


@pytest.mark.parametrize('change', ['missing', 'wrong-hash', 'other-app-dll', 'app-crt', 'external', 'duplicate'])
def test_module_origin_check_rejects_wrong_or_incomplete_native_bindings(tmp_path, change):
    from types import SimpleNamespace
    from backend.codec_module_probe import checked_modules, PINNED_FILES
    layout = frozen_layout(tmp_path, profile='runtime-experiment')
    decoder = SimpleNamespace(executable=layout.resource_root / codec.PREFIX / 'flac.exe')
    prefix = decoder.executable.parent.relative_to(layout.application_root).as_posix() + '/'
    records = [{'file': prefix+n, 'origin': 'application', 'sha256': PINNED_FILES[n]} for n in ('flac.exe','FLAC.dll')]
    records += [{'file': n, 'origin': 'windows-system', 'sha256': 'a'*64} for n in ('VCRUNTIME140.dll','ucrtbase.dll')]
    assert checked_modules(layout, decoder, records) == records
    if change == 'missing': records.pop(1)
    elif change == 'wrong-hash': records[1]['sha256'] = '0'*64
    elif change == 'other-app-dll': records[1]['file'] = '_internal/FLAC.dll'
    elif change == 'app-crt': records[2].update(file='_internal/VCRUNTIME140.dll', origin='application')
    elif change == 'external': records[1]['origin'] = 'external'
    elif change == 'duplicate': records.append(dict(records[1]))
    with pytest.raises(runtime_bundle.RuntimeBundleError, match='DLL origins'): checked_modules(layout, decoder, records)


def test_independently_authored_flac_has_fixed_signal_and_standard_crc_check_values():
    data, pcm = authored_flac()
    assert len(pcm) == 1024 and pcm != b'\0' * 1024
    assert digest(pcm) == 'e153774c8d06b094341ec9eb1e1f53571d3398a01cfd6526df97bc073f7ef379'
    assert digest(data) == '4e4d0d3eec7654126c8dfb64b54bddc3de62ae4181bcce206726df3e321792df'
    assert crc(b'123456789', 8, 0x07) == 0xf4
    assert crc(b'123456789', 16, 0x8005) == 0xfee8


def test_build_policy_matches_runtime_pins_and_refuses_legacy_wheel_before_writes(tmp_path):
    source = Path(__file__).resolve().parents[2]
    pin = json.loads((source / 'packaging/codecs/flac-reference.json').read_text())
    assert pin['source']['sha256'] == codec.ARCHIVE_SHA256
    assert all(codec.PINNED_FILES['notices/' + name] == sha for name, sha in pin['notices'].items())
    spec = importlib.util.spec_from_file_location('owned_codec_builder', source / 'scripts/prepare-runtime-codec.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    wheel = tmp_path / 'old-ffmpeg.whl'; wheel.write_bytes(b'legacy artifact')
    output = tmp_path / 'candidate'
    with pytest.raises(ValueError, match='Non-regular'): builder.prepare(wheel, output)
    assert not output.exists()


def test_collection_binds_codec_receipt_to_current_source_files(tmp_path, monkeypatch):
    # Runtime resource hashes alone cannot establish that a prepared codec used
    # the same preparation policy as the candidate being frozen.
    from backend.tests.test_runtime_experiment import recorder
    module = recorder(monkeypatch)
    layout, root, manifest = fixture(tmp_path, monkeypatch)
    source = tmp_path / 'source'
    for name in codec.SOURCE_INPUTS:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'owned source fixture')
    manifest['source_inputs'] = {name: digest((source / name).read_bytes()) for name in codec.SOURCE_INPUTS}
    layout = seal(layout, root, manifest)
    resources = [{'path': name, 'sha256': sha} for name, sha in layout.resources.items()]
    assert module.verified_codec(layout.resource_root, resources, layout.source_commit, source).executable == root / 'flac.exe'
    (source / 'packaging/codecs/flac-reference.json').write_bytes(b'changed policy')
    with pytest.raises(module.ClosureError, match='sources differ'):
        module.verified_codec(layout.resource_root, resources, layout.source_commit, source)
