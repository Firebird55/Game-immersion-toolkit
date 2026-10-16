import pytest


@pytest.fixture(autouse=True)
def synthetic_game_frames(monkeypatch):
    # Capture fixtures use synthetic handles and their own pixel providers.
    # Never send a fixture handle to a real desktop window during unit tests.
    monkeypatch.setattr('backend.capture.background_frame', lambda window: None)
