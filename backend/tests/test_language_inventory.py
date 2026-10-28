import json
from pathlib import Path
import pytest
from backend.language_inventory import LanguageInventory, directory_bytes
from backend.language_preparation import LanguagePreparation


def fixture(tmp_path):
    catalog = Path(__file__).parents[2] / 'public/mobile-capture/games-data.json'
    inventory = LanguageInventory(tmp_path, lambda _: None, catalog=catalog)
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

    # A preserved installation can carry an older catalog without newer games.
    # Every shipped game's language screen must use the active runtime bundle.
    from backend.languages import GAME_LOCALES
    old_catalog = tmp_path / 'public/mobile-capture/games-data.json'
    old_catalog.parent.mkdir(parents=True)
    old_catalog.write_text('{"games": []}', encoding='utf-8')
    installed = LanguageInventory(tmp_path / 'data', lambda _: None)
    for game, locales in GAME_LOCALES.items():
        prepared = manager.status(game)
        actual = installed.status(game, prepared)
        assert set(actual['locales']) == set(locales)
        assert actual['official_text_locales']
    assert old_catalog.read_text(encoding='utf-8') == '{"games": []}'


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


def test_status_refresh_reuses_summary_but_observes_replaced_table(tmp_path, monkeypatch):
    inventory, manager, path = fixture(tmp_path)
    read_text = Path.read_text
    reads = []
    def read(value, *args, **kwargs):
        if value == path:
            reads.append(value)
        return read_text(value, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    inventory.status('beyond', manager.status('beyond'))
    inventory.invalidate()
    inventory.status('beyond', manager.status('beyond'))
    assert len(reads) == 1, 'Status changes do not repeatedly decode an unchanged catalog'
    path.write_text(json.dumps({'records': [{'audio': None, 'voice_status': 'unvoiced'}]}))
    inventory.invalidate()
    value = inventory.status('beyond', manager.status('beyond'))['locales']['nl']
    assert len(reads) == 2 and value['dialogue_inventory']['voice_counts']['unvoiced'] == 1


def test_worker_validates_and_records_voice_inventory_before_publishing(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend import language_worker
    payload = {'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': [
        {'text_id': 'beyond:fixture', 'english': 'Synthetic test line', 'chinese': '',
         'source_locale': 'nl', 'source_text': 'Synthetic test line', 'texts': {'nl': 'Synthetic test line'}, 'audio_locale': 'nl',
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
    payload['records'][0]['audio'] = None
    for invalid in ({'source_text': ''}, {'source_text': '  '}, {'source_locale': 'fr'},
                    {'texts': {'nl': 'Different text'}}, {'audio_locale': 'en'}):
        original = payload['records'][0]
        payload['records'][0] = {**original, **invalid}
        with pytest.raises(ValueError, match='game study text'):
            language_worker.build('beyond', tmp_path, tmp_path, 'nl', ['en'], output)
        assert output.read_bytes() == before
        payload['records'][0] = original


def test_progress_lock_failures_do_not_abort_build_and_later_status_recovers(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from backend import language_worker
    output = tmp_path / 'snapshot.json'
    progress = output.with_name('progress.json')
    progress.write_text('{"message":"Previous status"}', encoding='utf-8')
    clock = [0.0]
    monkeypatch.setattr(language_worker.time, 'monotonic', lambda: clock[0])
    write_text, replace = Path.write_text, Path.replace
    attempts = []
    def locked_write(path, *args, **kwargs):
        if path == progress.with_suffix('.pending'):
            attempts.append(clock[0])
            if clock[0] == 0:
                raise PermissionError('Synthetic sharing violation on progress write')
        return write_text(path, *args, **kwargs)
    def locked_replace(path, target):
        if Path(target) == progress and clock[0] == 1:
            raise PermissionError('Synthetic sharing violation on progress replace')
        return replace(path, target)
    monkeypatch.setattr(Path, 'write_text', locked_write)
    monkeypatch.setattr(Path, 'replace', locked_replace)
    def extract(*_, progress):
        for stamp in (0, .2, .9, 1):
            clock[0] = stamp
            progress('Reading game files')
        return {'format': 2, 'game': 'beyond', 'source_locale': 'nl', 'records': [
            {'text_id': 'fixture', 'english': 'Synthetic line', 'chinese': '', 'audio': None,
             'source_locale': 'nl', 'source_text': 'Synthetic line', 'texts': {'nl': 'Synthetic line'}, 'audio_locale': 'nl'}]}
    monkeypatch.setattr(language_worker, 'asset_adapter', lambda _: (
        SimpleNamespace(LANGUAGE_INDEX_VERSION=1, index_language=extract), None))
    report = language_worker.progress_reporter(output)
    language_worker.build('beyond', tmp_path, tmp_path, 'nl', ['en'], output, report)
    assert output.is_file() and attempts == [0, 1]
    assert json.loads(progress.read_text(encoding='utf-8'))['message'] == 'Previous status'
    clock[0] = 2
    report('Validating language table')
    assert json.loads(progress.read_text(encoding='utf-8'))['message'] == 'Validating language table'
    def denied_snapshot(path, *args, **kwargs):
        if path == output:
            raise PermissionError('Synthetic snapshot failure')
        return write_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', denied_snapshot)
    with pytest.raises(PermissionError, match='snapshot failure'):
        language_worker.build('beyond', tmp_path, tmp_path, 'nl', ['en'], output, report)
