import threading
from types import SimpleNamespace

import pytest

from backend.config import SettingsStore
from backend.languages import normalize_text
from backend.zzz_cutscene_context import ZzzCutsceneContext


def index(rows, veto=False):
    caption = 'Rain, Rain! Are you okay?'
    key = normalize_text(caption, 'en')
    return caption, SimpleNamespace(game='zzz', lock=threading.RLock(),
        _lookup={'en': {key: rows}}, _full_frame_veto={'en': {key} if veto else set()})


@pytest.mark.parametrize('channel', ['Comic_abc', 'GalGame_dialogue', 'OngoingLevel_tip', 'CS_scene_001'])
def test_authored_player_identity_survives_restart_without_name_on_later_frames(tmp_path, channel):
    caption, catalog = index([{'text_id': channel, 'audio': {'event': 'voice_BangbooBelle_01'}}])
    context = ZzzCutsceneContext()
    assert context.observe_proxy(catalog, [caption], now=1, stable_frames=2) is None
    selected = context.observe_proxy(catalog, [caption], now=2, stable_frames=2)
    assert selected == 'female'
    store = SettingsStore(tmp_path / 'settings.json')
    store.remember_zzz_proxy(selected)
    assert SettingsStore(store.path).get().zzz_detected_proxy == 'female'
    # A later blank/name-only screen cannot erase or replace the evidence.
    assert context.observe_proxy(catalog, ['Wise'], now=3, stable_frames=2) is None
    store.remember_zzz_proxy(None)
    assert store.get().zzz_detected_proxy == 'female'


@pytest.mark.parametrize('rows,veto', [
    ([{'speaker_english': 'Belle', 'audio': {'event': 'voice_Belle_01'}}], False),
    ([{'player_voice': 'male'}, {'player_voice': 'female'}], False),
    ([{'player_voice': 'female'}, {'speaker_english': 'Nicole'}], False),
    ([{'player_voice': 'female'}], True),
])
def test_names_ambiguous_performances_and_choices_never_select_player(rows, veto):
    caption, catalog = index(rows, veto)
    context = ZzzCutsceneContext()
    for now in range(4):
        assert context.observe_proxy(catalog, [caption], now=now, stable_frames=2) is None


def test_detected_selection_preserves_manual_override_and_other_settings(tmp_path):
    store = SettingsStore(tmp_path / 'settings.json')
    current = store.get()
    current.zzz_proxy_voice = 'male'
    current.capture_unvoiced = True
    store.save(current)
    store.remember_zzz_proxy('female')
    restarted = SettingsStore(store.path).get()
    assert restarted.zzz_proxy_voice == 'male'
    assert restarted.zzz_detected_proxy == 'female' and restarted.capture_unvoiced
