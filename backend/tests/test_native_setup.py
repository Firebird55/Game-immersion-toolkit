"""Exercise real local Qt forms with mocked identity and protected storage."""
import time

import httpx
import pytest

from backend.accounts import AccountStore
from backend.protected_storage import ProtectedBlobs
from backend.tests.test_protected_storage import Store


@pytest.fixture
def qt(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication(['Setup tests'])
    return application


def finish(app, dialog):
    deadline = time.monotonic() + 5
    while dialog.task and dialog.task.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not dialog.task.isRunning()
    app.processEvents()


def test_account_form_verifies_readonly_and_keeps_key_out_of_visible_status(qt, tmp_path):
    from backend.native_setup import AccountDialog
    from PySide6.QtWidgets import QLineEdit
    calls = []
    def reply(request):
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={'user': {'id': 'TEST_OWNER', 'name': 'Test'}})
    blobs = ProtectedBlobs(tmp_path / 'protected', provider=Store())
    store = AccountStore(tmp_path / 'accounts', protect=blobs.protect, transport=httpx.MockTransport(reply))
    dialog = AccountDialog(store)
    key = 'lx_TEST_ONLY_mock_credential'
    try:
        assert dialog.key.echoMode() == QLineEdit.Password
        dialog.key.setText(key)
        dialog.save()
        finish(qt, dialog)
        assert dialog.success and dialog.key.text() == ''
        assert key not in dialog.status.text()
        assert key.encode() not in store.path.read_bytes()
        assert store.active_key() == key
        assert calls == [('GET', '/v1/me')]
    finally:
        dialog.close()


def test_failed_account_verification_keeps_form_retryable_without_saving(qt, tmp_path):
    from backend.native_setup import AccountDialog
    store = AccountStore(tmp_path / 'accounts', transport=httpx.MockTransport(lambda _: httpx.Response(401)))
    dialog = AccountDialog(store)
    try:
        dialog.key.setText('lx_TEST_ONLY_rejected_credential')
        dialog.save()
        finish(qt, dialog)
        assert not dialog.success and not store.path.exists()
        assert dialog.key.isEnabled() and dialog.key.text() == ''
        assert 'rejected' in dialog.status.text()
    finally:
        dialog.close()


def test_folder_cancel_does_not_change_game_paths(qt, monkeypatch):
    from backend import native_setup
    monkeypatch.setattr(native_setup, 'load_paths', lambda: {})
    monkeypatch.setattr(native_setup.QFileDialog, 'getExistingDirectory', lambda *_: '')
    monkeypatch.setattr(native_setup, 'save_install', lambda *_: pytest.fail('Cancelled dialog saved a folder'))
    dialog = native_setup.FolderDialog()
    try:
        dialog.choose()
        assert not dialog.success
    finally:
        dialog.close()


def test_setup_reports_wayland_requirement_instead_of_claiming_ready(monkeypatch):
    import backend.platform_windows  # Resolve native psutil before simulating another platform.
    from backend.desktop_capabilities import capture_capability
    monkeypatch.setattr('backend.desktop_capabilities.sys.platform', 'linux')
    monkeypatch.setenv('XDG_SESSION_TYPE', 'wayland')
    result = capture_capability()
    assert not result['ready'] and 'portal' in result['help']


def test_mac_setup_explains_denied_screen_permission(monkeypatch):
    import sys
    from types import SimpleNamespace
    from backend.desktop_capabilities import capture_capability
    monkeypatch.setattr('backend.desktop_capabilities.sys.platform', 'darwin')
    monkeypatch.setitem(sys.modules, 'Quartz', SimpleNamespace(CGPreflightScreenCaptureAccess=lambda: False))
    result = capture_capability()
    assert not result['ready'] and 'System Settings' in result['help']
