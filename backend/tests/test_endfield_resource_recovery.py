"""A same-client hotfix replans from exact upstream source without reset."""
import copy
from types import SimpleNamespace as NS

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Reviewed pure preparation dependency')
from backend import endfield_game_data as game, endfield_resource_source, endfield_text_source
from backend.tests.test_endfield_text_source import Fixture, catalog
from backend.tests.test_endfield_release import text_table


@pytest.mark.parametrize('stage', ['original-text-tables-downloaded', 'original-text-navigation-pending', 'original-presentation-containers-downloaded'])
def test_same_client_new_resource_replans_text_and_retains_prior_exact_source(tmp_path, monkeypatch, stage):
    original = Fixture(tmp_path)
    try:
        plan, index = original.plan()
        reference = original.download(plan, index)
        old_generation = copy.deepcopy(original.generation)
        old_catalog = endfield_text_source.Catalog(original.context(), original.client, original.common, reference)
        bootstrap = {'schema': 1, 'stage': 'client-bootstrap-downloaded', 'client': original.client,
                     'request': original.request.json(), 'receipt_sha256': 'b' * 64}
        tables_stage = {'schema': 1, 'stage': 'original-text-tables-downloaded', 'client': original.client,
                        'request': original.request.json(), 'source': bootstrap, 'text': reference}
        continuation = tables_stage if stage == tables_stage['stage'] else {
            'schema': 1, 'stage': stage, 'client': original.client, 'request': original.request.json(), 'tables': tables_stage}
        if stage == 'original-presentation-containers-downloaded':
            import hashlib
            continuation['source'] = {'generation_sha256': hashlib.sha256(game._json_bytes(old_generation)).hexdigest()}
        old_ready = tmp_path / 'old-complete-library.json'
        old_ready.write_bytes(b'old complete library retained')
        original.generation = copy.deepcopy(original.generation)
        original.generation['layers']['main']['sha256'] = 'f' * 64
        original.files[1] = ('I18nTextTable_EN', text_table('I18nTextTable_EN', 1, 'New resource English'))
        original.index, original.payload = catalog(original.files)
        provider = game.create_provider(platform='windows')
        monkeypatch.setattr(provider, '_runtime', lambda: None)
        monkeypatch.setattr(provider, '_latest', lambda *_: (original.client, None))
        monkeypatch.setattr(provider, '_transport', lambda request, ctx: original.transport(ctx))
        def checked_upstream(ctx, identity, transport, source):
            assert source == bootstrap and identity == original.client
            return NS()
        monkeypatch.setattr(provider, '_text_bootstrap', checked_upstream)
        monkeypatch.setattr(provider, '_common', lambda *_: original.common)
        monkeypatch.setattr(endfield_resource_source, 'discover', lambda *_: original.generation)
        before = len(original.calls)
        planning = original.context()
        planning.stage_handle = continuation
        updated = provider.plan(original.request, planning)
        assert updated.stage == 'original-text-tables'
        assert updated.handle['source'] == bootstrap and updated.handle['text']['generation'] == original.generation
        assert all(url.endswith('.blc') for url in original.calls[before:])
        downloading = original.context('download', updated.download_bytes)
        result = provider.download(updated, downloading)
        current = endfield_text_source.Catalog(downloading, original.client, original.common, result.restore_handle['text'])
        assert current.generation != old_generation
        assert current.file('TableCfg/I18nTextTable_EN.json') == {'1': 'New resource English'}
        assert old_catalog.file('TableCfg/I18nTextTable_EN.json') == {'1': 'Complete English'}
        assert old_ready.read_bytes() == b'old complete library retained'
        assert not any(url.endswith('.dll') or '/Audio' in url for url in original.calls)
    finally:
        original.service.close()
