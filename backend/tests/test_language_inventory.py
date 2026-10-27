import json
from pathlib import Path
import pytest
from backend.language_inventory import LanguageInventory, directory_bytes
from backend.language_preparation import LanguagePreparation


def fixture(tmp_path):
    catalog = Path(__file__).parents[2] / 'public/mobile-capture/games-data.json'
    inventory = LanguageInventory(tmp_path, catalog, lambda _: None)
    manager = LanguagePreparation(None, None, None, path=tmp_path / 'state.json')
    path = inventory.table('beyond', 'nl')
    path.parent.mkdir(parents=True)
    path.write_text('{}')
    manager.data['prepared'] = {'beyond': {'nl': {'targets': ['en']}}}
    manager.data['selected'] = {'account': {'beyond': 'nl'}}
    return inventory, manager, path


def test_cleanup_only_removes_owned_table_and_clears_selections(tmp_path):
    inventory, manager, path = fixture(tmp_path)
    history = tmp_path / 'history.db'
    history.write_bytes(b'keep history')
    assert inventory.cleanup('beyond', 'nl', manager)['reclaimed_bytes'] == 2
    assert not path.exists()
    assert history.read_bytes() == b'keep history'
    assert manager.selected('beyond', 'account') is None


def test_busy_unknown_and_escape_cleanup_are_rejected(tmp_path):
    inventory, manager, path = fixture(tmp_path)
    with pytest.raises(ValueError):
        inventory.cleanup('beyond', 'nl', manager, busy=True)
    for game, locale in [('../outside', 'nl'), ('beyond', '../../secret'), ('honkai3', 'en')]:
        with pytest.raises(ValueError):
            inventory.cleanup(game, locale, manager)
    assert path.exists()


def test_inventory_reports_actual_bytes_and_unknown_external_sizes(tmp_path):
    inventory, manager, path = fixture(tmp_path)
    result = inventory.status('beyond', manager.status('beyond'))
    assert result['locales']['nl']['table_bytes'] == 2
    assert result['storage']['installed_game_bytes'] is None
    assert result['storage']['tables_bytes'] == 2
    assert directory_bytes(tmp_path / 'languages') == 2


def test_language_inventory_separates_silence_from_missing_voices(tmp_path):
    inventory, manager, path = fixture(tmp_path)
    path.write_text(json.dumps({'records': [
        {'audio': {'source': 'synthetic'}, 'dialogue_kind': 'conversation'},
        {'audio': None, 'voice_status': 'unvoiced', 'dialogue_kind': 'message'},
        {'audio': None, 'voice_status': 'unavailable', 'dialogue_kind': 'cutscene'},
        {'audio': None}], 'coverage_warnings': ['Some cinematic timing references are unresolved.']}))
    value = inventory.status('beyond', manager.status('beyond'))['locales']['nl']
    assert value['dialogue_inventory']['voice_counts'] == dict.fromkeys(('voiced', 'unvoiced', 'unavailable', 'unknown'), 1)
    assert value['dialogue_inventory']['categories']['message']['unvoiced'] == 1
    assert value['coverage_warnings'] == ['Some cinematic timing references are unresolved.']


def test_worker_validates_and_records_voice_inventory_before_publishing(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend import language_worker
    payload = {'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': [
        {'text_id': 'beyond:fixture', 'english': 'Synthetic test line', 'chinese': '',
         'audio': None, 'voice_status': 'unvoiced', 'dialogue_kind': 'conversation'}]}
    adapter = SimpleNamespace(LANGUAGE_INDEX_VERSION=3, index_language=lambda *_: payload)
    monkeypatch.setattr(language_worker, 'asset_adapter', lambda _: (adapter, None))
    output = tmp_path / 'snapshot.json'
    language_worker.build('beyond', tmp_path, tmp_path, 'nl', ['en'], output)
    value = json.loads(output.read_text(encoding='utf-8'))
    assert value['reader_revision'] == 3 and value['targets_requested'] == ['en']
    assert value['dialogue_inventory']['categories']['conversation']['unvoiced'] == 1
    payload['records'][0]['audio'] = {'source': 'contradictory voice'}
    before = output.read_bytes()
    with pytest.raises(ValueError, match='voice status'):
        language_worker.build('beyond', tmp_path, tmp_path, 'nl', ['en'], output)
    assert output.read_bytes() == before
