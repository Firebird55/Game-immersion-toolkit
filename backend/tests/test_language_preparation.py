import threading
import time

import pytest

from backend.language_preparation import LanguagePreparation


def finish(manager):
    deadline = time.monotonic() + 3
    while manager._workers and time.monotonic() < deadline:
        time.sleep(.005)
    assert not manager._workers


def test_nothing_is_built_until_explicit_selection_and_only_prepared_languages_refresh(tmp_path):
    builds, activations = [], []
    manager = LanguagePreparation(lambda *args: builds.append(args), lambda *args: activations.append(args),
        lambda *_: {'ready': True, 'audio_count': 5}, path=tmp_path / 'languages.json',
        supported=lambda _: ('zh-Hans', 'ko', 'en'))
    manager.refresh_prepared()
    assert builds == [] and not manager.path.exists()
    manager.request('wuwa', 'ko', 'nl', 'account-one')
    finish(manager)
    assert builds == [('wuwa', 'ko', ('nl',))]
    assert manager.selected('wuwa', 'account-one') == 'ko'
    assert manager.selected('wuwa', 'account-two') is None
    manager.refresh_prepared()
    finish(manager)
    assert builds == [('wuwa', 'ko', ('nl',))] * 2
    assert manager.prepared('wuwa', 'zh-Hans') is None
    assert manager.prepared('cyberpunk', 'ko') is None
    manager.remove('wuwa', 'ko')
    manager.refresh_prepared()
    assert len(builds) == 2 and manager.selected('wuwa', 'account-one') is None


def test_failed_translation_build_keeps_previous_complete_preparation(tmp_path):
    fails = []
    def build(*args):
        if fails:
            raise ValueError('Official target text missing')
    manager = LanguagePreparation(build, lambda *_: None, lambda *_: {'ready': True}, path=tmp_path / 'languages.json')
    manager.request('cyberpunk', 'zh-Hans', 'en', 'first')
    finish(manager)
    original = manager.path.read_bytes()
    fails.append(True)
    manager.request('cyberpunk', 'zh-Hans', 'nl', 'second')
    finish(manager)
    assert manager.path.read_bytes() == original
    assert manager.prepared('cyberpunk', 'zh-Hans')['targets'] == ['en']
    assert manager.selected('cyberpunk', 'second') is None
    assert next(item for item in manager.status('cyberpunk')['locales'] if item['locale']=='zh-Hans')['job']['state'] == 'error'


def test_unprepared_selection_and_unknown_locales_are_rejected(tmp_path):
    manager = LanguagePreparation(lambda *_: None, lambda *_: None, lambda *_: {}, path=tmp_path / 'languages.json')
    with pytest.raises(ValueError, match='Prepare'):
        manager.select('nte', 'zh-Hans')
    with pytest.raises(ValueError, match='compatible reader'):
        manager.request('nte', 'ja', 'en')
    with pytest.raises(ValueError):
        manager.request('honkai3', 'zh-Hans', 'en')


def test_explicit_rebuild_uses_forced_builder_but_automatic_refresh_does_not(tmp_path):
    builds = []
    manager = LanguagePreparation(lambda *args: builds.append(('cached', args)), lambda *_: None,
        lambda *_: {'ready': True, 'audio_count': 1}, path=tmp_path / 'languages.json',
        supported=lambda _: ('en',), rebuild=lambda *args: builds.append(('forced', args)))
    manager.request('nte', 'en', 'zh-Hans', 'account')
    finish(manager)
    manager.request('nte', 'en', 'zh-Hans', 'account', rebuild=True)
    finish(manager)
    manager.refresh_prepared()
    finish(manager)
    assert [mode for mode, _ in builds] == ['cached', 'forced', 'cached']
    assert all(args == ('nte', 'en', ('zh-Hans',)) for _, args in builds)
