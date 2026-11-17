"""Original provider composition, generation ownership and failure preservation."""
from types import SimpleNamespace

import pytest

from backend import starrail_original_provider as provider


def fixture(monkeypatch, *, region='global', failed=None):
    state = {'calls': [], 'version': '9.8.7', 'native': 'native-generation-one'}
    base = {'channel': 'starrail-' + region, 'version': state['version'], 'manifests': {'game': ['official-manifest']}}
    def release(channel):
        assert channel == 'starrail-' + region
        state['calls'].append('launcher')
        return base
    def native(directory, build, names):
        assert directory.name == region and build is base and names == provider.TABLES
        state['calls'].append('native')
        return SimpleNamespace(native='matching-native', routes={'owned': 'routes'},
                               tables={'owned': 'table-descriptions'}, identity=state['native'])
    def discovery(directory, build, routes):
        assert routes == {'owned': 'routes'}
        state['calls'].append('dispatch')
        if failed == 'dispatch':
            raise ValueError('Original dispatch retired or malformed')
        return base | {'hotfix': {'indexes': {name: [state['version'], name, 123]
            for name in ('design', 'asb', 'lua', 'audio', 'video')}}}
    monkeypatch.setattr(provider.sophon, 'release', release)
    monkeypatch.setattr(provider.native, 'prepare', native)
    monkeypatch.setattr(provider.discovery, 'prepare', discovery)
    monkeypatch.setattr(provider.hotfix, 'index', lambda directory, build, name: state['calls'].append('index-' + name))
    monkeypatch.setattr(provider.hotfix, 'movie_files', lambda *args: {'original-movie': 'owned-index-entry'})
    monkeypatch.setattr(provider, 'NativeIndex', lambda native: native)
    monkeypatch.setattr(provider, 'Descriptions', lambda index: {'native': index})
    def tables(directory, build, *, descriptions):
        assert descriptions == {'owned': 'table-descriptions'}
        return 'original-tables'
    monkeypatch.setattr(provider, 'OriginalTables', tables)
    def configs(tables, descriptions):
        assert tables == 'original-tables' and descriptions == {'native': 'matching-native'}
        return 'original-configs'
    monkeypatch.setattr(provider, 'OriginalConfigs', configs)
    class Catalog:
        def __init__(self, tables, configs, movies, *, revision, build):
            assert (tables, configs, movies) == ('original-tables', 'original-configs', {'original-movie': 'owned-index-entry'})
            self.revision = revision
        def file(self, path):
            state['calls'].append(path)
            if failed == 'table' and path.endswith('VoiceConfig.json'):
                raise ValueError('Malformed original table')
            return []
        def caption_scripts(self):
            state['calls'].append('captions')
            if failed == 'caption':
                raise ValueError('Unproved original caption owner')
            return []
    monkeypatch.setattr(provider, 'OriginalCatalog', Catalog)
    monkeypatch.setattr(provider, '_catalog_identity', lambda generation: 'catalog-' + generation.identity)
    return state


@pytest.mark.parametrize('region', ['global', 'cn'])
def test_provider_joins_matching_original_generations_before_publishing_descriptor(tmp_path, monkeypatch, region):
    state = fixture(monkeypatch, region=region)
    stamp, catalog = provider.prepare(tmp_path, region, format_revision='a' * 40)
    assert catalog.revision == 'original-catalog-native-generation-one'
    assert catalog.movie_audio_source == (tmp_path / 'tools/sophon', stamp, 'a' * 40)
    assert state['calls'][:3] == ['launcher', 'native', 'dispatch']
    assert set(state['calls'][8:-1]) == {'ExcelOutput/' + name + '.json' for name in provider.TABLES}
    assert state['calls'][-1] == 'captions'
    assert (tmp_path / 'tools/sophon/releases' / stamp).is_file()
    assert provider.current(tmp_path / 'tools', stamp, region, format_revision='a' * 40)
    state['version'] = 'changed-original-index'
    assert not provider.current(tmp_path / 'tools', stamp, region)


def test_movie_description_revision_and_outage_state_are_part_of_the_source_generation(tmp_path, monkeypatch):
    fixture(monkeypatch)
    first, _ = provider.prepare(tmp_path, format_revision='a' * 40)
    second, catalog = provider.prepare(tmp_path, format_revision='b' * 40, format_metadata_stale=True)
    assert second != first and catalog.movie_format_metadata_stale
    assert provider.current(tmp_path / 'tools', second, format_revision='b' * 40, format_metadata_stale=True)
    assert not provider.current(tmp_path / 'tools', second, format_revision='b' * 40)
    with pytest.raises(ValueError):
        provider.prepare(tmp_path, format_metadata_stale='yes')


@pytest.mark.parametrize('failed', ['dispatch', 'table', 'caption'])
def test_bad_new_original_generation_preserves_existing_release_and_publishes_no_new_receipt(tmp_path, monkeypatch, failed):
    fixture(monkeypatch, failed=failed)
    releases = tmp_path / 'tools/sophon/releases'
    releases.mkdir(parents=True)
    old = releases / 'previous-complete-generation'
    old.write_bytes(b'preserve prior complete source')
    with pytest.raises(ValueError):
        provider.prepare(tmp_path)
    assert list(releases.iterdir()) == [old] and old.read_bytes() == b'preserve prior complete source'


def test_original_provider_never_needs_a_latest_third_party_format_publication(tmp_path, monkeypatch):
    from backend import starrail_movie_metadata as formats
    fixture(monkeypatch)
    monkeypatch.setattr(formats, 'check_latest', lambda *args: pytest.fail('No new third-party format publication'))
    _, catalog = provider.prepare(tmp_path)
    assert catalog.movie_audio_source[2] is None
    with pytest.raises(ValueError):
        provider.prepare(tmp_path, format_revision='latest')
