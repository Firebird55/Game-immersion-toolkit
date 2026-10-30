import json
import threading
from types import SimpleNamespace

import pytest

from backend.local_game import LocalGameTextIndex
from backend.pragmata import PragmataTextIndex
from backend.local_game_updates import LocalGameUpdateManager


def payload(text='Stay close!', text_id='cyberpunk:1'):
    return {'format': 1, 'install': '.', 'fingerprint': 'old', 'records': [{
        'text_id': text_id, 'english': text, 'chinese': '跟紧我！',
        'source': 'fixture', 'audio': {'depot': 'fixture'}}]}


def write_index(path, value, pragmata=False):
    if not pragmata:
        value = {**value, 'records': [{k: v for k, v in r.items() if k != 'source'} for r in value['records']]}
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.mark.parametrize('pragmata', [False, True])
def test_matching_continues_while_replacement_lookup_is_prepared(tmp_path, monkeypatch, pragmata):
    module_name = 'backend.pragmata' if pragmata else 'backend.local_game'
    path = tmp_path / 'textmap.json'
    write_index(path, payload(), pragmata)
    index = PragmataTextIndex(tmp_path) if pragmata else LocalGameTextIndex('cyberpunk', tmp_path)
    if pragmata:
        assert index.load()
    from importlib import import_module
    module = import_module(module_name)
    original = module.ChineseLookup
    preparing, release, matched = threading.Event(), threading.Event(), threading.Event()
    def prepare(records):
        preparing.set()
        assert release.wait(3)
        return original(records)
    monkeypatch.setattr(module, 'ChineseLookup', prepare)
    write_index(path, payload('A replacement line is ready now.'), pragmata)
    loader = threading.Thread(target=index.load)
    loader.start()
    assert preparing.wait(2)
    def match():
        if index.match_lines(['Stay close!']) is not None:
            matched.set()
    reader = threading.Thread(target=match)
    reader.start()
    try:
        assert matched.wait(.5), 'Refresh held the live matcher lock while building a new lookup'
    finally:
        release.set()
        loader.join(3)
        reader.join(3)
    assert index.match_lines(['A replacement line is ready now.']) is not None
    monkeypatch.setattr(module, 'ChineseLookup', lambda _: pytest.fail('Unchanged snapshot rebuilt'))
    assert index.load()
    path.write_text('{broken', encoding='utf-8')
    assert not index.load()
    assert index.ready and index.match_lines(['A replacement line is ready now.']) is not None


def test_live_game_refresh_uses_a_separate_worker_and_keeps_old_snapshot(tmp_path, monkeypatch):
    import backend.local_game_updates as module
    import backend.cyberpunk_assets as assets
    path = tmp_path / 'textmap.json'
    write_index(path, payload())
    index = LocalGameTextIndex('cyberpunk', tmp_path)
    updater = LocalGameUpdateManager('cyberpunk', index, SimpleNamespace(reload=lambda: None), project_root=tmp_path)
    monkeypatch.setattr(module, 'discover_install', lambda _: tmp_path)
    monkeypatch.setattr('backend.game_tools.missing_tools', lambda *_: [])
    monkeypatch.setattr(assets, 'fingerprint', lambda _: 'new')
    monkeypatch.setattr(assets, 'index_install', lambda *_: pytest.fail('Heavy indexing ran inside OCR process'))
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Worker:
        returncode = 0
        def __init__(self, command, **options):
            calls.append((command, options))
            self.output = command[command.index('--output') + 1]
        def communicate(self, timeout):
            entered.set()
            assert release.wait(3)
            from pathlib import Path
            write_index(Path(self.output), payload('The new version has arrived.'))
            return None, ''
        def poll(self):
            return 0
    monkeypatch.setattr(module, 'start_process', Worker)
    thread = threading.Thread(target=updater._run)
    thread.start()
    assert entered.wait(2)
    try:
        assert index.match_lines(['Stay close!']) is not None
    finally:
        release.set()
        thread.join(3)
    assert calls[0][0][1:3] == ['-m', 'backend.game_index_worker']
    assert calls[0][1]['env']['OMP_NUM_THREADS'] == '1'
    assert index.match_lines(['The new version has arrived.']) is not None
