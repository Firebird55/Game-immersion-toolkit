"""Exact authored container members survive source-byte cache deduplication."""
import copy
import io
import json
from email.message import Message

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Reviewed pure preparation dependency')
from backend.game_data_protocol import GameDataError
from backend import endfield_presentation_bundles as source
from backend.tests.test_endfield_navigation_source import Fixture as NavigationFixture, index


class Fixture(NavigationFixture):
    def __init__(self, root, mode='text', initial_ui=False):
        super().__init__(root, mode, initial_ui)
        self.payloads, self.asset_calls = {}, []
        self.corrupt_asset = False
        for block, role in ((2, 'initial'), (11, 'main')):
            files = [('Data/Bundles/Windows/' + name, b'owned fixture bundle')
                     for name in sorted(set(self.owners.values())) if name.startswith(role + '/')]
            if files:
                self.indices[block], self.payloads[block] = index(files, block)

    def transport(self, ctx):
        transport = super().transport(ctx)
        inherited = transport.open
        fixture = self
        class Response:
            def __init__(self, url, raw, start, end, total):
                self.url, self.status, self.body = url, 206, io.BytesIO(raw)
                self.headers = Message()
                self.headers['Content-Length'] = str(len(raw))
                self.headers['Content-Range'] = f'bytes {start}-{end}/{total}'
            def geturl(self): return self.url
            def read(self, size): return self.body.read(size)
            def __enter__(self): return self
            def __exit__(self, *_): pass
        def opened(request, **kwargs):
            url = request.full_url
            if url.endswith('.chk') and any('/' + fixture.common.directories[block] + '/' in url for block in fixture.payloads):
                block = next(block for block in fixture.payloads if '/' + fixture.common.directories[block] + '/' in url)
                start, end = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
                fixture.asset_calls.append((url, start, end))
                data = fixture.payloads[block][start:end + 1]
                if fixture.corrupt_asset: data = data[:-1] + bytes([data[-1] ^ 1])
                return Response(url, data, start, end, len(fixture.payloads[block]))
            return inherited(request, **kwargs)
        transport.open = opened  # Explicit per-fixture HTTP seam, never global I/O.
        return transport

    def navigation(self):
        first, index4 = self.plan()
        self.download(first, index4)
        second, index4 = self.plan()
        return self.download(second, index4)

    def bundle_plan(self, reference):
        ctx = self.context()
        return source.plan(ctx, self.client, self.common, self.generation, reference, self.transport(ctx))[0]

    def bundle_download(self, quote, *, changed=False, budget=None):
        ctx = self.context('download', quote['download_bytes'] if budget is None else budget)
        return source.download(ctx, self.client, self.common, quote, self.transport(ctx),
            recheck=lambda: (self.client, {} if changed else self.generation))


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
@pytest.mark.parametrize('initial_ui', [False, True])
def test_exact_members_compact_plan_and_cold_warm_original_source_only(tmp_path, mode, initial_ui):
    original = Fixture(tmp_path, mode, initial_ui)
    try:
        reference = original.navigation()
        quote = original.bundle_plan(reference)
        assert quote['selected_member_count'] == 12 and quote['unique_payload_count'] == 1
        assert quote['payload_bytes'] == len(b'owned fixture bundle')
        assert not original.asset_calls
        assert quote['decoded_library_bytes'] is None
        assert len(json.dumps(quote)) < 1024**2 and 'groups' not in quote
        result = original.bundle_download(quote)
        assert result['stage'] == 'original-presentation-containers-downloaded'
        assert len(original.asset_calls) == 1
        body, owners, files = source.restore(original.context(), original.client, original.common, original.generation, result)
        assert len(files) == 12 and len(owners) == 12 and len(body['members']) == 12
        assert body['aes_header_parameters_verified'] is False and body['canonical_snapshot_prepared'] is False
        warm = original.bundle_plan(result['navigation'])
        assert warm['payload_bytes'] == 0 and warm['retained_verified_bytes'] == len(b'owned fixture bundle')
        before = len(original.asset_calls)
        original.bundle_download(warm)
        assert len(original.asset_calls) == before
    finally:
        original.service.close()


def test_valid_changed_index_selection_returns_new_navigation_before_asset_transfer(tmp_path):
    original = Fixture(tmp_path)
    original.no_etag = True
    try:
        reference = original.navigation()
        quote = original.bundle_plan(reference)
        files = [('Data/Bundles/Windows/' + name, b'X' * len(b'owned fixture bundle')) for name in sorted(set(original.owners.values()))]
        old_header = original.indices[11][:16]
        original.indices[11], original.payloads[11] = index(files, 11)
        assert original.indices[11][:16] == old_header
        result = original.bundle_download(quote)
        assert result['stage'] == 'original-text-navigation-verified' and result['selection_changed']
        assert not original.asset_calls
        current = original.bundle_plan(result['navigation'])
        assert current['inventory_sha256'] != quote['inventory_sha256']
    finally:
        original.service.close()


@pytest.mark.parametrize('failure', ['body', 'inventory', 'budget', 'generation', 'late-generation', 'cancel'])
def test_failed_container_stage_publishes_no_source_and_preserves_previous_ready_bytes(tmp_path, failure):
    original = Fixture(tmp_path)
    old_ready = tmp_path / 'old-ready.json'
    old_ready.write_bytes(b'old exact complete library')
    try:
        quote = original.bundle_plan(original.navigation())
        if failure == 'body': original.corrupt_asset = True
        elif failure == 'inventory':
            path = source._root(original.context()) / 'plans' / (quote['inventory_sha256'] + '.json')
            path.write_bytes(b'{}')
        with pytest.raises(GameDataError):
            if failure in {'late-generation', 'cancel'}:
                ctx = original.context('download', quote['download_bytes'])
                if failure == 'cancel': ctx.cancel.set()
                count = 0
                def recheck():
                    nonlocal count
                    count += 1
                    return original.client, original.generation if count == 1 else {}
                source.download(ctx, original.client, original.common, quote, original.transport(ctx), recheck=recheck)
            else:
                original.bundle_download(quote, changed=failure == 'generation', budget=0 if failure == 'budget' else None)
        assert old_ready.read_bytes() == b'old exact complete library'
        assert not list(source._root(original.context()).glob('sources/*.json'))
        if failure == 'late-generation':
            assert original.asset_calls
            assert original.bundle_plan(quote['navigation'])['payload_bytes'] == 0  # Checked partials survive a new quote.
    finally:
        original.service.close()


def test_missing_cached_source_fails_exact_restore_without_source_lookup(tmp_path):
    original = Fixture(tmp_path)
    try:
        reference = original.bundle_download(original.bundle_plan(original.navigation()))
        body, _, files = source.restore(original.context(), original.client, original.common, original.generation, reference)
        row = next(iter(files.values()))
        (source._root(original.context()) / 'assets' / row.content_hashes[1]).write_bytes(bytes(row.size))
        before = len(original.calls), len(original.asset_calls)
        with pytest.raises(GameDataError):
            source.restore(original.context(), original.client, original.common, original.generation, reference)
        assert (len(original.calls), len(original.asset_calls)) == before
    finally:
        original.service.close()
