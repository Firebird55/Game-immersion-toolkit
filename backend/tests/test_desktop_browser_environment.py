"""System-browser launch isolation; no real browser or profile is opened."""
import ctypes
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import desktop_host as host


def frozen(monkeypatch, tmp_path, platform):
    root = tmp_path / 'runtime'
    root.mkdir()
    monkeypatch.setattr(host.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(host.sys, '_MEIPASS', str(root), raising=False)
    monkeypatch.setattr(host.sys, 'platform', platform)
    monkeypatch.setenv('PATH', os.pathsep.join((str(root), str(root / 'PySide6'), str(tmp_path / 'system'))))
    monkeypatch.setenv('QT_PLUGIN_PATH', str(root / 'PySide6/plugins'))
    monkeypatch.setenv('QML2_IMPORT_PATH', str(root / 'PySide6/qml'))
    monkeypatch.setenv('QML_IMPORT_PATH', str(tmp_path / 'system-qml'))
    return root


@pytest.mark.parametrize('platform', ['linux', 'darwin'])
@pytest.mark.parametrize('original', [None, 'system-libraries'])
def test_posix_opener_receives_sanitized_copy_and_preserves_host(monkeypatch, tmp_path, platform, original):
    root = frozen(monkeypatch, tmp_path, platform)
    monkeypatch.setenv('LD_LIBRARY_PATH', str(root))
    if original is None:
        monkeypatch.delenv('LD_LIBRARY_PATH_ORIG', raising=False)
    else:
        monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', original)
    monkeypatch.setenv('DYLD_LIBRARY_PATH', os.pathsep.join((str(root), str(tmp_path / 'native'))))
    before = dict(os.environ)
    calls = []
    def find(name, *, path):
        assert name == 'xdg-open' and path == str(tmp_path / 'system')
        return '/usr/bin/xdg-open'
    monkeypatch.setattr(host.shutil, 'which', find)
    monkeypatch.setattr(host.subprocess, 'Popen', lambda command, **options:
                        calls.append((command, options)) or SimpleNamespace(wait=lambda timeout: 0))
    assert host.open_desktop_browser('http://127.0.0.1:1234')
    command, options = calls[0]
    assert command[0] == ('/usr/bin/open' if platform == 'darwin' else '/usr/bin/xdg-open')
    environment = options['env']
    assert environment['PATH'] == str(tmp_path / 'system')
    assert environment['DYLD_LIBRARY_PATH'] == str(tmp_path / 'native')
    assert environment.get('LD_LIBRARY_PATH') == (original if platform == 'linux' else None)
    assert 'QT_PLUGIN_PATH' not in environment and 'QML2_IMPORT_PATH' not in environment
    assert environment['QML_IMPORT_PATH'] == str(tmp_path / 'system-qml')
    assert dict(os.environ) == before
    assert options['close_fds'] and options['start_new_session']


def test_path_filter_uses_directory_boundary_not_prefix(monkeypatch, tmp_path):
    root = frozen(monkeypatch, tmp_path, 'darwin')
    sibling = str(root) + '-system'
    monkeypatch.setenv('PATH', os.pathsep.join((str(root), sibling)))
    assert host._browser_environment()['PATH'] == sibling


@pytest.mark.parametrize('platform', ['win32', 'linux', 'darwin'])
def test_source_mode_preserves_environment_and_never_changes_dll_search(monkeypatch, platform):
    monkeypatch.delattr(host.sys, 'frozen', raising=False)
    monkeypatch.setattr(host.sys, 'platform', platform)
    before = dict(os.environ)
    monkeypatch.setattr(host, '_windows_browser_environment', lambda *_: pytest.fail('source DLL directory changed'))
    monkeypatch.setattr(host.webbrowser, 'open', lambda url: True)
    monkeypatch.setattr(host.shutil, 'which', lambda name: '/usr/bin/xdg-open')
    def spawn(command, **options):
        assert 'env' not in options
        return SimpleNamespace(wait=lambda timeout: 0)
    monkeypatch.setattr(host.subprocess, 'Popen', spawn)
    assert host.open_desktop_browser('http://127.0.0.1:1234')
    assert dict(os.environ) == before


class NativeCall:
    def __init__(self, callback):
        self.callback = callback
    def __call__(self, *arguments):
        return self.callback(*arguments)


@pytest.mark.parametrize('result', [True, False, 'raise'])
@pytest.mark.parametrize('prior_directory', [None, 'earlier-native-directory'])
def test_windows_restores_environment_and_observed_dll_directory_on_all_outcomes(monkeypatch, tmp_path, result, prior_directory):
    frozen(monkeypatch, tmp_path, 'win32')
    before = dict(os.environ)
    directory, changes = [prior_directory], []
    def get(size, buffer):
        value = directory[0]
        if not value:
            return 0
        if not size:
            return len(value) + 1
        buffer.value = value
        return len(value)
    def set_directory(value):
        changes.append(value)
        directory[0] = value
        return True
    kernel = SimpleNamespace(GetDllDirectoryW=NativeCall(get), SetDllDirectoryW=NativeCall(set_directory))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *_a, **_kw: kernel, raising=False)
    monkeypatch.setattr(ctypes, 'set_last_error', lambda _value: None, raising=False)
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 0, raising=False)
    def open_browser(url):
        assert directory[0] is None
        assert os.environ['PATH'] == str(tmp_path / 'system')
        assert 'QT_PLUGIN_PATH' not in os.environ
        assert os.environ['QML_IMPORT_PATH'] == str(tmp_path / 'system-qml')
        if result == 'raise':
            raise OSError('Authored handler failure')
        return result
    monkeypatch.setattr(host.webbrowser, 'open', open_browser)
    if result == 'raise':
        with pytest.raises(OSError, match='Authored handler failure'):
            host.open_desktop_browser('http://127.0.0.1:1234')
    else:
        assert host.open_desktop_browser('http://127.0.0.1:1234') is result
    assert changes == ([None, prior_directory] if prior_directory else [])
    assert directory[0] == prior_directory and dict(os.environ) == before


@pytest.mark.skipif(os.name != 'nt', reason='Actual Windows DLL-directory API')
def test_actual_windows_dll_directory_is_restored_after_handler_exception(monkeypatch, tmp_path):
    from ctypes import wintypes
    frozen(monkeypatch, tmp_path, 'win32')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes, kernel.GetDllDirectoryW.restype = [wintypes.DWORD, wintypes.LPWSTR], wintypes.DWORD
    kernel.SetDllDirectoryW.argtypes, kernel.SetDllDirectoryW.restype = [wintypes.LPCWSTR], wintypes.BOOL
    def current():
        length = kernel.GetDllDirectoryW(0, None)
        if not length:
            return None
        buffer = ctypes.create_unicode_buffer(length)
        assert kernel.GetDllDirectoryW(length, buffer) < length
        return buffer.value
    original = current()
    selected = str(tmp_path / 'original-search')
    Path(selected).mkdir()
    try:
        assert kernel.SetDllDirectoryW(selected)
        def fail(url):
            assert not current()
            raise OSError('Authored handler failure')
        monkeypatch.setattr(host.webbrowser, 'open', fail)
        with pytest.raises(OSError, match='Authored handler failure'):
            host.open_desktop_browser('http://127.0.0.1:1234')
        assert current() == selected
    finally:
        assert kernel.SetDllDirectoryW(original or None)
