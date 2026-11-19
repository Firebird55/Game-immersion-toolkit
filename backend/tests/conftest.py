import os

import pytest


@pytest.fixture(autouse=True)
def synthetic_game_frames(monkeypatch):
    # Capture fixtures use synthetic handles and their own pixel providers.
    # Never send a fixture handle to a real desktop window during unit tests.
    monkeypatch.setattr('backend.capture.BackgroundCapture.frame', lambda self, window: None)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call():
    if os.name != 'nt':
        return (yield)
    symlink = os.symlink

    def create_link(*args, **kwargs):
        try:
            return symlink(*args, **kwargs)
        except OSError as error:
            if error.winerror == 1314:
                pytest.skip('This Windows test process cannot create symbolic links.')
            raise

    # Scope this to the test body. Pytest also tries creating a convenience
    # symlink during tmp_path setup, where missing privilege is already handled.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, 'symlink', create_link)
        return (yield)
