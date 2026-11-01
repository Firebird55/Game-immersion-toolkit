"""Setup displays verified production capability without approving candidates."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from backend import installation
from backend.runtime_bundle import RuntimeLayout


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    (root / '_internal').mkdir(parents=True)
    (root / 'THIRD_PARTY').mkdir()
    header = bytearray(256)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 128)
    header[128:132] = b'PE\0\0'
    struct.pack_into('<H', header, 132, 0x8664)
    executable = root / 'GameImmersionToolkit.exe'
    executable.write_bytes(header)
    (root / 'LICENSE').write_text('Authored application license fixture', encoding='utf-8')
    (root / 'THIRD_PARTY/fixture.txt').write_text('Authored dependency notice fixture', encoding='utf-8')
    (root / '_internal/package.json').write_text('{"version":"1.2.3"}', encoding='utf-8')
    identity = dict(source_commit='a' * 40, version='1.2.3', build_id='authored-status-fixture',
                    profile='runtime', storage_epoch=1, host_protocol=1)
    (root / '_internal/runtime-manifest.json').write_text(json.dumps(identity), encoding='utf-8')
    receipt = dict(schema='proxy-runtime-candidate-v1', **identity, r19_complete=False,
                   release_eligible=True, redistribution_review='approved', native_acceptance='approved',
                   files=[dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size,
                               sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                          for p in sorted(root.rglob('*')) if p.is_file()],
                   directories=[p.relative_to(root).as_posix() for p in sorted(root.rglob('*')) if p.is_dir()])
    (root / 'PROVENANCE.json').write_text(json.dumps(receipt), encoding='utf-8')
    user = tmp_path / 'user'
    layout = RuntimeLayout(mode='bundle', application_root=root, resource_root=root / '_internal',
        executable=executable, settings_root=user, **identity,
        **{name: user / name for name in ('data_root', 'cache_root', 'tool_root', 'work_root',
                                        'state_root', 'default_export_root')})
    monkeypatch.setattr(installation, 'discover_layout', lambda: layout)
    monkeypatch.setattr(installation, 'GAMES', [])
    monkeypatch.setattr(installation, 'load_paths', lambda: {})
    monkeypatch.setattr(installation, 'resource_path', lambda name: layout.resource_root / name)
    monkeypatch.setattr(installation, 'ffmpeg_executable', lambda: 'authored-decoder')
    monkeypatch.setattr('backend.ocr_engine.portable_models_available', lambda: True)
    monkeypatch.setattr('backend.desktop_capabilities.capture_capability',
                        lambda: dict(id='capture', title='Capture', ready=True, help='Available'))
    service = installation.InstallationService(root, settings=SimpleNamespace(get=lambda: SimpleNamespace(auto_start=False)),
        game_state=lambda _: {}, refresh=lambda _: None, account_configured=lambda: False)
    yield service, layout, receipt
    service.quiesce(timeout=3)


def requirement(service):
    return next(item for item in service.status()['requirements'] if item['id'] == 'runtime-acceptance')


def finish_check(service):
    requirement(service)
    if service._runtime_thread:
        service._runtime_thread.join(3)
        assert not service._runtime_thread.is_alive()
    return requirement(service)


def test_approved_production_inventory_is_ready_independently_of_r19(installed):
    service, _, receipt = installed
    assert receipt['r19_complete'] is False
    assert finish_check(service)['ready'] is True
    assert 'approved release inventory' in requirement(service)['help']
    capabilities = {item['id']: item for item in service.status()['requirements']}
    for name in ('capture', 'ocr', 'audio'):
        assert capabilities[name]['ready'] is True
        assert 'experimental' not in capabilities[name]['help']
        assert 'unavailable until' not in capabilities[name]['help']
    assert 'node' not in capabilities


def test_runtime_acceptance_does_not_hide_missing_local_capabilities(installed, monkeypatch):
    service, _, _ = installed
    assert finish_check(service)['ready'] is True
    monkeypatch.setattr(installation, 'ffmpeg_executable', lambda: None)
    monkeypatch.setattr('backend.desktop_capabilities.capture_capability',
        lambda: dict(id='capture', title='Capture', ready=False, help='Allow screen recording in system settings.'))
    capabilities = {item['id']: item for item in service.status()['requirements']}
    assert capabilities['runtime-acceptance']['ready'] is True
    assert capabilities['audio']['ready'] is False
    assert capabilities['capture']['ready'] is False
    assert capabilities['capture']['help'] == 'Allow screen recording in system settings.'


@pytest.mark.parametrize('target', ['linux-x64', 'macos-x64', 'macos-arm64'])
def test_approved_portable_receipt_uses_actual_executable_architecture(installed, monkeypatch, target):
    service, layout, receipt = installed
    root = layout.application_root
    layout.executable.unlink()
    executable = root / 'GameImmersionToolkit'
    header = bytearray(256)
    if target == 'linux-x64':
        header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', header, 18, 62)
    else:
        header[:4] = b'\xcf\xfa\xed\xfe'
        struct.pack_into('<I', header, 4, 0x100000c if target == 'macos-arm64' else 0x1000007)
    executable.write_bytes(header)
    receipt['files'] = [dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size,
                            sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                       for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'PROVENANCE.json']
    (root / 'PROVENANCE.json').write_text(json.dumps(receipt), encoding='utf-8')
    monkeypatch.setattr(installation, 'discover_layout', lambda: replace(layout, executable=executable))
    assert finish_check(service)['ready'] is True


@pytest.mark.parametrize(('key', 'value'), [
    ('release_eligible', False), ('release_eligible', 'true'),
    ('native_acceptance', 'unavailable'), ('redistribution_review', 'pending-exact-output'),
    ('profile', 'runtime-experiment'), ('build_id', 'another-build'),
    ('storage_epoch', 2), ('host_protocol', 2), ('schema', 'unrecognized'),
])
def test_candidate_or_mismatched_receipt_cannot_approve_installed_runtime(installed, key, value):
    service, layout, receipt = installed
    receipt[key] = value
    (layout.application_root / 'PROVENANCE.json').write_text(json.dumps(receipt), encoding='utf-8')
    assert finish_check(service)['ready'] is False


def test_experimental_layout_cannot_promote_itself_with_an_approved_receipt(installed, monkeypatch):
    service, layout, _ = installed
    monkeypatch.setattr(installation, 'discover_layout', lambda: replace(layout, profile='runtime-experiment'))
    assert requirement(service)['ready'] is False
    assert service._runtime_thread is None
    capabilities = {item['id']: item for item in service.status()['requirements']}
    assert capabilities['ocr']['ready'] and capabilities['audio']['ready']
    assert 'experimental' not in capabilities['ocr']['help']
    assert 'unavailable' not in capabilities['audio']['help']


@pytest.mark.parametrize('mutation', ['missing-receipt', 'bad-json', 'json-list', 'oversized-receipt',
                                      'changed-file', 'extra-file', 'empty-directory', 'missing-file'])
def test_missing_or_mutated_inventory_invalidates_previously_ready_status(installed, mutation):
    service, layout, _ = installed
    assert finish_check(service)['ready'] is True
    root = layout.application_root
    receipt = root / 'PROVENANCE.json'
    if mutation == 'missing-receipt':
        receipt.unlink()
    elif mutation == 'bad-json':
        receipt.write_text('{', encoding='utf-8')
    elif mutation == 'json-list':
        receipt.write_text('[]', encoding='utf-8')
    elif mutation == 'oversized-receipt':
        receipt.write_bytes(b' ' * (8 * 1024 * 1024 + 1))
    elif mutation == 'changed-file':
        (root / 'LICENSE').write_text('Changed fixture', encoding='utf-8')
    elif mutation == 'extra-file':
        (root / 'extra.txt').write_text('Unexpected fixture', encoding='utf-8')
    elif mutation == 'empty-directory':
        (root / 'extra').mkdir()
    else:
        (root / 'LICENSE').unlink()
    # Setup is a bounded display cache. Activation independently verifies every
    # payload byte; the next background refresh invalidates changed installs.
    service._runtime_next_check = 0
    assert requirement(service)['ready'] is False
    assert finish_check(service)['ready'] is False


def test_unchanged_inventory_does_not_repeat_full_payload_hashing(installed, monkeypatch):
    service, _, _ = installed
    assert finish_check(service)['ready'] is True
    def unexpected(*args, **kwargs):
        pytest.fail('Unchanged setup polls must reuse inventory verification')
    monkeypatch.setattr(installation.runtime_payload, 'validate', unexpected)
    assert requirement(service)['ready'] is True
    assert requirement(service)['ready'] is True
    service._runtime_next_check = 0
    assert finish_check(service)['ready'] is True


@pytest.mark.parametrize('operation', ['receipt', 'inventory'])
def test_slow_metadata_io_is_owned_off_the_setup_poll_thread(installed, monkeypatch, operation):
    service, _, _ = installed
    entered, release = threading.Event(), threading.Event()
    target = installation.runtime_payload if operation == 'receipt' else installation
    name = 'read_installed_receipt' if operation == 'receipt' else '_runtime_inventory_stamp'
    original = getattr(target, name)
    caller = threading.current_thread()
    def slow(*args, **kwargs):
        assert threading.current_thread() is not caller
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(target, name, slow)
    try:
        assert requirement(service)['ready'] is False
        assert entered.wait(1)
        thread = service._runtime_thread
        for _ in range(5):
            assert requirement(service)['ready'] is False
            assert service._runtime_thread is thread
        with pytest.raises(TimeoutError):
            service.quiesce(timeout=.01)
        assert service._runtime_thread is thread and thread.is_alive()
    finally:
        release.set()
        service.quiesce(timeout=3)
    service.resume()
    assert requirement(service)['ready'] is True


def test_cached_polls_perform_no_receipt_or_tree_io(installed, monkeypatch):
    service, _, _ = installed
    assert finish_check(service)['ready'] is True
    def unexpected(*args, **kwargs):
        pytest.fail('Cached setup polls cannot read the receipt or scan the payload')
    monkeypatch.setattr(installation.runtime_payload, 'read_installed_receipt', unexpected)
    monkeypatch.setattr(installation, '_runtime_inventory_stamp', unexpected)
    for _ in range(5):
        assert requirement(service)['ready'] is True


def test_layout_identity_change_invalidates_unexpired_display_cache(installed, monkeypatch):
    service, layout, _ = installed
    assert finish_check(service)['ready'] is True
    monkeypatch.setattr(installation, 'discover_layout', lambda: replace(layout, build_id='different-build'))
    assert requirement(service)['ready'] is False
    assert finish_check(service)['ready'] is False


def test_verification_is_retained_and_does_not_block_setup_or_escape_quiesce(installed, monkeypatch):
    service, _, _ = installed
    entered, release = threading.Event(), threading.Event()
    original = installation.runtime_payload.validate
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(installation.runtime_payload, 'validate', slow)
    try:
        assert requirement(service)['ready'] is False
        assert entered.wait(1)
        thread = service._runtime_thread
        assert 'Checking' in requirement(service)['help']
        assert service._runtime_thread is thread
        with pytest.raises(TimeoutError):
            service.quiesce(timeout=.01)
        with pytest.raises(RuntimeError, match='Runtime verification'):
            service.resume()
        assert service._runtime_thread is thread and thread.is_alive()
    finally:
        release.set()
        service.quiesce(timeout=3)
    service.resume()
    assert requirement(service)['ready'] is True


def test_mutation_during_verification_is_not_published_ready(installed, monkeypatch):
    service, layout, _ = installed
    original = installation.runtime_payload.validate
    def changed(*args, **kwargs):
        verified = original(*args, **kwargs)
        (layout.application_root / 'LICENSE').write_text('Changed after hashing', encoding='utf-8')
        return verified
    monkeypatch.setattr(installation.runtime_payload, 'validate', changed)
    assert finish_check(service)['ready'] is False


def test_source_setup_has_no_packaged_acceptance_requirement(installed, monkeypatch):
    service, layout, _ = installed
    monkeypatch.setattr(installation, 'discover_layout', lambda: replace(layout, mode='source', profile='source'))
    requirements = {item['id'] for item in service.status()['requirements']}
    assert 'runtime-acceptance' not in requirements
    assert 'node' in requirements
    assert service._runtime_thread is None


@pytest.mark.parametrize('state', ['approved', 'candidate', 'missing-receipt', 'changed-payload'])
def test_explicit_diagnostic_reports_only_verified_installed_production(installed, monkeypatch, capsys, state):
    from backend import bundle_entry
    _, layout, receipt = installed
    if state == 'candidate':
        receipt['native_acceptance'] = 'unavailable'
        (layout.application_root / 'PROVENANCE.json').write_text(json.dumps(receipt), encoding='utf-8')
    elif state == 'missing-receipt':
        (layout.application_root / 'PROVENANCE.json').unlink()
    elif state == 'changed-payload':
        (layout.application_root / 'LICENSE').write_text('Changed fixture', encoding='utf-8')
    monkeypatch.setattr(bundle_entry, 'discover_layout', lambda: layout)
    assert bundle_entry.main(['--runtime-diagnose']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['native_acceptance'] == ('approved' if state == 'approved' else 'unavailable')
    assert result['r19_complete'] is False
    assert str(layout.application_root) not in json.dumps(result)


def test_explicit_diagnostic_needs_no_application_or_native_imports(installed):
    _, layout, _ = installed
    script = r'''
import builtins, json, sys
from pathlib import Path
from types import SimpleNamespace
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('backend.api', 'backend.installation', 'backend.desktop_host', 'numpy', 'Crypto', 'PySide6')):
        raise AssertionError('Diagnostic imported application or native libraries: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from backend import bundle_entry
root = Path(sys.argv[1])
identity = json.loads((root / '_internal/runtime-manifest.json').read_text(encoding='utf-8'))
layout = SimpleNamespace(mode='bundle', schema='authored-fixture', children=(), application_root=root,
    resource_root=root / '_internal', executable=root / 'GameImmersionToolkit.exe', **identity)
bundle_entry.discover_layout = lambda: layout
raise SystemExit(bundle_entry.main(['--runtime-diagnose']))
'''
    process = subprocess.run([sys.executable, '-c', script, str(layout.application_root)],
        cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)['native_acceptance'] == 'approved'
