import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from backend import mobile_export_controls as controls


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setattr(controls, 'discover_install', lambda game: None)
    root = tmp_path / 'toolkit'
    (root / 'data/voice-assets').mkdir(parents=True)
    (root / 'data/voice-assets/manifest.json').write_text(json.dumps({'entries': {'one': {}, 'two': {}}}))
    return controls.MobileExportManager(root)


def test_preview_estimates_audio_and_conversion_space_without_creating_destination(manager, tmp_path):
    destination = tmp_path / 'private-library'
    voices = manager.preview('zzz', True, str(destination))
    text = manager.preview('zzz', False, str(destination))
    assert voices['estimatedBytes'] > text['estimatedBytes'] > 0
    assert voices['estimateLowBytes'] < voices['estimatedBytes'] < voices['estimateHighBytes']
    assert voices['workingBytes'] > voices['estimatedBytes'] * 3
    assert voices['freeBytes'] > 0 and voices['rows'] == 2
    assert not destination.exists()


def test_destination_protects_sources_games_and_other_repositories(manager, tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        manager.preview('zzz', destination_folder='relative-folder')
    with pytest.raises(ValueError):
        manager.preview('zzz', destination_folder=str(manager.root / 'backend'))
    repository = tmp_path / 'another-project'
    (repository / '.git').mkdir(parents=True)
    with pytest.raises(ValueError):
        manager.preview('zzz', destination_folder=str(repository / 'exports'))
    install = tmp_path / 'game'
    install.mkdir()
    monkeypatch.setattr(controls, 'discover_install', lambda game: install)
    with pytest.raises(ValueError):
        manager.preview('zzz', destination_folder=str(install / 'exports'))
    manager.preview('zzz')  # Existing private output stays supported.


def test_previous_export_is_used_as_an_explicit_estimate(manager):
    folder = manager.destination() / 'zzz'
    revision = 'a' * 64
    (folder / revision).mkdir(parents=True)
    (folder / 'latest.json').write_text(json.dumps({'revision': revision}))
    (folder / revision / 'zzz.catalog.zip').write_bytes(b'catalog')
    (folder / revision / 'zzz.voices-test.zip').write_bytes(b'voices')
    assert manager.preview('zzz')['estimatedBytes'] == 13
    assert manager.preview('zzz', False)['estimatedBytes'] == 7
    assert 'Previous' in manager.preview('zzz')['basis']


def test_status_refreshes_free_space_instead_of_showing_stale_export_estimate(manager, monkeypatch):
    manager._status.update(estimate={'freeBytes': 5000}, outputFolder=str(manager.root))
    monkeypatch.setattr(controls.shutil, 'disk_usage', lambda path: SimpleNamespace(free=1234))
    assert manager.status()['estimate']['freeBytes'] == 1234
    assert manager._status['estimate']['freeBytes'] == 5000


@pytest.mark.parametrize('phase', ['preparing', 'exporting'])
def test_cancel_interrupts_blocked_preparation_and_decoder_children_and_retains_previous_export(manager, tmp_path, phase):
    output = manager.destination() / 'zzz'
    output.mkdir(parents=True)
    pointer = output / 'latest.json'
    pointer.write_text('{"previous":"valid"}')
    worker = tmp_path / 'blocked_worker.py'
    worker.write_text("""import sys,subprocess,json,time
from pathlib import Path
output=Path(sys.argv[1]);(output/'cache').mkdir(exist_ok=True)
(output/'cache/complete.mp3').write_bytes(b'completed fixture')
children=[subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']) for _ in range(8)]
(output/'child-ready').write_text(json.dumps([child.pid for child in children]))
print(json.dumps({'state':sys.argv[2],'message':'synthetic blocked phase'}),flush=True)
time.sleep(120)
""")
    manager._worker_args = lambda game, audio, out: [sys.executable, '-u', str(worker), str(out), phase]
    assert manager.start('zzz')
    limit = time.monotonic() + 10
    while not (output / 'child-ready').exists() and time.monotonic() < limit:
        time.sleep(.03)
    assert (output / 'child-ready').exists()
    start = time.monotonic()
    assert manager.cancel()
    manager._thread.join(timeout=8)
    assert not manager._thread.is_alive()  # Child inherited stdout; EOF requires killing it too.
    assert time.monotonic() - start < 8
    assert manager.status()['state'] == 'cancelled'
    assert pointer.read_text() == '{"previous":"valid"}'
    assert (output / 'cache/complete.mp3').read_bytes() == b'completed fixture'
    assert manager.cancel() is False


def test_selected_destination_is_remembered_and_busy_start_cannot_change_it(manager, tmp_path):
    target = tmp_path / 'my-mobile-libraries'
    manager._worker_args = lambda *args: [sys.executable, '-c', "print('{\"state\":\"complete\",\"progress\":100}')"]
    assert manager.start('zzz', destination_folder=str(target))
    manager._thread.join(timeout=5)
    assert manager.status()['state'] == 'complete'
    assert manager.destination() == target
    assert (target / 'zzz').is_dir()
    manager._status['state'] = 'cancelling'
    assert manager.start('zzz', destination_folder=str(tmp_path / 'other')) is False
    assert manager.destination() == target


def test_picker_cancel_preserves_destination_and_selection_is_applied(manager, tmp_path):
    previous = manager.destination()
    result = tmp_path / 'picker.json'
    manager._picker = SimpleNamespace(poll=lambda: 0)
    manager._picker_result = result
    assert manager.status()['destinationFolder'] == str(previous)
    selected = tmp_path / 'chosen'
    result.write_text(json.dumps({'folder': str(selected)}))
    manager._picker = SimpleNamespace(poll=lambda: 0)
    manager._picker_result = result
    assert manager.status()['destinationFolder'] == str(selected)
    assert not result.exists()


def running_picker(manager, tmp_path):
    result = tmp_path / 'picker.json'
    process = SimpleNamespace(returncode=None, terminated=False)
    process.poll = lambda: process.returncode
    process.terminate = lambda: setattr(process, 'terminated', True)
    process.wait = lambda timeout: setattr(process, 'returncode', -1)
    def stop():
        process.terminate()
        process.wait(timeout=5)
    manager._picker_owner = SimpleNamespace(process=process, stop=stop, close_streams=lambda: None)
    manager._picker, manager._picker_result = process, result
    manager._picker_started = time.monotonic()
    return process, result


def test_stalled_picker_times_out_and_destination_remains_editable(manager, tmp_path):
    previous = manager.destination()
    process, result = running_picker(manager, tmp_path)
    manager._picker_started -= 26
    status = manager.status()
    assert process.terminated
    assert status['browseActive'] is False and status['browsePhase'] is None
    assert status['destinationFolder'] == str(previous)
    assert 'did not show' in status['browseMessage']
    assert not result.exists()


def test_close_picker_discards_pending_selection_and_releases_busy_state(manager, tmp_path):
    previous = manager.destination()
    process, result = running_picker(manager, tmp_path)
    ready = Path(str(result) + '.ready')
    ready.write_text('{}')
    result.write_text(json.dumps({'folder': str(tmp_path / 'abandoned')}))
    assert manager.status()['browsePhase'] == 'open'
    assert manager.close_picker()
    assert process.terminated and manager.close_picker() is False
    assert not result.exists() and not ready.exists()
    assert manager.status()['browseActive'] is False
    assert manager.destination() == previous


def test_ready_picker_waits_for_user_and_reports_failure_without_private_details(manager, tmp_path):
    process, result = running_picker(manager, tmp_path)
    ready = Path(str(result) + '.ready')
    ready.write_text('{}')
    manager._picker_started -= 60
    assert manager.status()['browseActive'] and not process.terminated
    process.returncode = 1
    result.write_text(json.dumps({'error': 'private diagnostic'}))
    status = manager.status()
    assert not status['browseActive'] and 'failed' in status['browseMessage']
    assert 'private' not in status['browseMessage'] and not ready.exists()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows startup flags')
def test_picker_requests_visible_dialog_from_hidden_companion(manager, monkeypatch):
    calls = []
    monkeypatch.setattr(controls, 'OwnedProcess', lambda args, **kwargs: calls.append((args, kwargs)) or
                        SimpleNamespace(process=SimpleNamespace(poll=lambda: None)))
    assert manager.browse()
    args, options = calls[0]
    assert '-STA' in args
    assert options['show_window'] is True
    assert not options.get('visible_console', False)
