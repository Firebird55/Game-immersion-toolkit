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
