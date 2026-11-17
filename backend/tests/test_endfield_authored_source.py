"""Ordinary source continuation uses real receipts, parsers and HTTP budgets."""
import copy
import hashlib
import io
import json
import struct
from email.message import Message
from types import SimpleNamespace as NS

import pytest

pytest.importorskip('backend.game_data_protocol', reason='Reviewed pure preparation dependency')
from backend.game_data_protocol import GameDataError, GameDataRequest, PreparationStage, SnapshotSource
from backend import endfield_authored_source as source, endfield_game_data as game
from backend import endfield_tables as tables, endfield_text_source as text, endfield_resource_source as resources
from backend.tests.test_endfield_authored_validation import original
from backend.tests.test_endfield_text_source import Fixture as TextFixture, catalog


def table(name, values):
    """Small authored string/bean SparkBuffer fixture; production reader parses it."""
    definitions = []
    def schema(value):
        if isinstance(value, str): return (tables.STRING,)
        assert isinstance(value, dict)
        identity = len(definitions)
        definitions.append(None)
        fields = [(key, schema(item)) for key, item in value.items()]
        definitions[identity] = fields
        return tables.BEAN, identity
    item = schema(next(iter(values.values()))) if values else (tables.STRING,)
    raw = bytearray(16)
    def pad(): raw.extend(bytes((-len(raw)) % 4))
    def integer(value): raw.extend(struct.pack('<i', value))
    def string(value): raw.extend(value.encode() + b'\0')
    def kind(value):
        raw.append(value[0])
        if value[0] == tables.BEAN: pad(); integer(value[1])
    integer(len(definitions))
    for identity, fields in enumerate(definitions):
        raw.append(tables.BEAN); pad(); integer(identity); string('Owned' + str(identity)); pad(); integer(len(fields))
        for key, value in fields: string(key); kind(value)
    root = len(raw)
    raw.append(tables.MAP); string(name); raw.extend((tables.STRING, item[0]))
    if item[0] == tables.BEAN: pad(); integer(item[1])
    pad(); data = len(raw)
    def referenced(value, schema, offset):
        location = len(raw)
        struct.pack_into('<i', raw, offset, location)
        if schema[0] == tables.STRING: string(value)
        else:
            fields = definitions[schema[1]]
            assert list(value) == [key for key, _ in fields]
            raw.extend(bytes(4 * len(fields)))
            for index, (key, field) in enumerate(fields): referenced(value[key], field, location + 4 * index)
    integer(len(values)); raw.extend(bytes(8 * len(values)))
    offsets = len(raw); raw.extend(bytes(8 * len(values)))
    for number, (key, value) in enumerate(values.items()):
        referenced(str(key), (tables.STRING,), offsets + 8 * number)
        referenced(value, item, offsets + 8 * number + 4)
    # Empty map still needs one byte after its direct values offset.
    raw.extend(b'\0')
    struct.pack_into('<4i', raw, 0, 16, root, data, 0)
    result = bytes(raw)
    assert tables.read(result, name) == values
    return result


class Fixture(TextFixture):
    def __init__(self, root, mode='text', locale='en', targets=('ja', 'de', 'zh-Hans')):
        super().__init__(root, mode)
        self.request = GameDataRequest('global', locale, targets, mode)
        values = original(locale).values
        for name, field in (('DialogTextTable', 'dialogText'), ('DialogOptionTable', 'optionText')):
            for row in values[name].values(): row[field]['id'] = str(row[field]['id'])
        values['AudioDialog'] = {key: {'path': row['path']} for key, row in values['AudioDialog'].items()
                                 if not row.get('isPlaceholder')}
        for code in {locale, *targets}:
            from backend.endfield_assets import TEXT_LOCALES
            values['I18nTextTable_' + TEXT_LOCALES[code]] = {
                str(i): code + ' complete authored translation ' + str(i) for i in range(1, 8)}
        self.files = [(name, table(name, value)) for name, value in values.items()]
        self.index, self.payload = catalog(self.files)
        self.header_calls, self.index_calls = [], []
        self.change_second_index = False

    def transport(self, ctx):
        transport = super().transport(ctx)
        inherited = transport.open
        fixture = self
        class Response:
            def __init__(self, url, data, owner):
                self.url, self.status, self.body = url, 206, io.BytesIO(data)
                self.headers = Message()
                self.headers['Content-Length'] = str(len(data))
                self.headers['Content-Range'] = owner
            def geturl(self): return self.url
            def read(self, size): return self.body.read(size)
            def __enter__(self): return self
            def __exit__(self, *_): pass
        def server(request, **options):
            if request.full_url.endswith('.blc') and request.get_header('Range'):
                low, high = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
                raw = fixture.index
                if high == 15: fixture.header_calls.append(len(raw))
                else:
                    fixture.index_calls.append(len(raw))
                    if fixture.change_second_index and len(fixture.index_calls) % 2 == 0:
                        # Valid new owned index behind the same short header.
                        changed = list(fixture.files)
                        changed[0] = (changed[0][0], changed[0][1] + b'\0')
                        raw, payload = catalog(changed)
                        assert raw[:16] == fixture.index[:16] and len(raw) == len(fixture.index)
                        fixture.files, fixture.index, fixture.payload = changed, raw, payload
                fixture.calls.append(request.full_url)
                return Response(request.full_url, raw[low:high + 1], f'bytes {low}-{high}/{len(raw)}')
            return inherited(request, **options)
        transport.open = server
        return transport

    def retained(self):
        quote, index = super().plan()
        return super().download(quote, index)

    def quote(self, reference):
        ctx = self.context()
        return source.plan(ctx, self.client, self.common, self.generation, reference, self.transport(ctx))

    def validate(self, quote, *, changed=False, budget=None):
        ctx = self.context('download', 2 * len(self.index) if budget is None else budget)
        reference = source.download(ctx, self.client, self.common, quote, self.transport(ctx),
            recheck=lambda: (self.client, {} if changed else self.generation))
        return reference, ctx


@pytest.mark.parametrize('mode', ['text', 'text-audio'])
@pytest.mark.parametrize('locale', ['en', 'zh-Hans', 'zh-Hant', 'ja', 'ko'])
def test_original_tables_all_locales_and_modes_publish_only_bounded_nonready_evidence(tmp_path, monkeypatch, mode, locale):
    fixture = Fixture(tmp_path, mode, locale)
    try:
        reference = fixture.retained()
        before = len(fixture.calls)
        with monkeypatch.context() as patch:
            patch.setattr(tables, 'read', lambda *_: pytest.fail('Plan must not decode table bodies'))
            quote = fixture.quote(reference)
        assert len(fixture.calls) == before + 1 and not fixture.index_calls
        assert quote['wire_index_recheck_bytes'] == 2 * len(fixture.index)
        assert quote['required_disk_bytes'] == 2 * (source.MAX_FACTS + source.MAX_RECEIPT)
        result, ctx = fixture.validate(quote)
        body = source.restore(ctx, fixture.client, fixture.common, fixture.generation, result, reference)
        assert body['validation_report']['ordinary_records_verified'] == 8
        assert body['validation_report']['snapshot_ready'] is False and not body['canonical_snapshot_prepared']
        assert body['facts_bytes'] < source.MAX_FACTS and len(json.dumps(result)) < 2048
        assert len(fixture.index_calls) == 2 and ctx.consumed == 2 * len(fixture.index)
        facts = json.loads(next((ctx.cache_directory / 'endfield-authored-tables/facts').glob('*.json')).read_bytes())
        assert set(facts['records'][0]['texts']) == {locale, *fixture.request.target_locales}
        assert all(row['audio'] is None for row in facts['records'])
        assert all('Audio' not in url and not url.endswith('.dll') for url in fixture.calls)
    finally: fixture.service.close()


@pytest.mark.parametrize('change', ['late-generation', 'same-header-body', 'budget', 'table', 'oversized-output'])
def test_failure_never_publishes_candidate_or_replaces_old_library_and_recordings(tmp_path, monkeypatch, change):
    fixture = Fixture(tmp_path)
    old = tmp_path / 'old-ready.json'; old.write_bytes(b'old ready library')
    recording = tmp_path / 'old-recording.wav'; recording.write_bytes(b'old exact recording')
    try:
        reference = fixture.retained(); quote = fixture.quote(reference)
        if change == 'same-header-body': fixture.change_second_index = True
        elif change == 'table':
            path = next((fixture.context().cache_directory / 'endfield-text-tables/assets').iterdir())
            path.write_bytes(b'changed original table')
        elif change == 'oversized-output': monkeypatch.setattr(source, 'MAX_FACTS', 16)
        with pytest.raises(GameDataError):
            fixture.validate(quote, changed=change == 'late-generation', budget=0 if change == 'budget' else None)
        assert not list(tmp_path.rglob('endfield-authored-tables/receipts/*.json'))
        assert old.read_bytes() == b'old ready library' and recording.read_bytes() == b'old exact recording'
    finally: fixture.service.close()


@pytest.mark.parametrize('change', ['request', 'generation', 'receipt', 'facts', 'table'])
def test_exact_offline_restore_rejects_changed_source_without_network(tmp_path, change):
    fixture = Fixture(tmp_path)
    try:
        original_reference = fixture.retained(); quote = fixture.quote(original_reference)
        reference, ctx = fixture.validate(quote)
        calls = list(fixture.calls)
        if change == 'request': reference = {**reference, 'request': {**reference['request'], 'content_mode': 'text-audio'}}
        elif change == 'generation': reference = {**reference, 'generation_sha256': '0' * 64}
        elif change in ('receipt', 'facts'):
            folder = 'receipts' if change == 'receipt' else 'facts'
            next((ctx.cache_directory / 'endfield-authored-tables' / folder).iterdir()).write_bytes(b'changed')
        else: next((ctx.cache_directory / 'endfield-text-tables/assets').iterdir()).write_bytes(b'changed')
        with pytest.raises(GameDataError):
            source.restore(ctx, fixture.client, fixture.common, fixture.generation, reference, original_reference)
        assert fixture.calls == calls
    finally: fixture.service.close()


def provider_fixture(tmp_path, monkeypatch, mode):
    from backend.tests.test_endfield_presentation_bundles import Fixture as Navigation
    from backend.publisher_transport import PublisherTransport
    fixture = Fixture(tmp_path, mode)
    navigation = Navigation(tmp_path, mode)
    navigation.service.close()  # Only fixture's real service/context owns this run.
    fixture.common.directories.update(navigation.common.directories)
    fixture.generation = copy.deepcopy(navigation.generation)
    layer_body = b'original resource index fixture' * 3
    for layer in fixture.generation['layers'].values():
        layer.update(sha256=hashlib.sha256(layer_body).hexdigest(), index_bytes=len(layer_body))
    latest = {'version': fixture.client['version'], 'pkg': {'file_path': fixture.client['url'],
        'game_files_md5': fixture.client['game_files_md5'], 'packs': [
            {'url': row['url'], 'md5': row['md5'], 'package_size': str(row['bytes'])}
            for row in fixture.client['artifacts']]}}
    original_factory = fixture.transport
    class Response:
        def __init__(self, url, raw):
            self.url, self.status, self.body = url, 200, io.BytesIO(raw)
            self.headers = Message(); self.headers['Content-Length'] = str(len(raw))
        def geturl(self): return self.url
        def read(self, size): return self.body.read(size)
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def transport(ctx, *, hosts):
        table_http, navigation_http = original_factory(ctx).open, navigation.transport(ctx).open
        def server(request, **options):
            url = request.full_url
            if '/get_latest?' in url: return Response(url, json.dumps(latest).encode())
            if '/get_latest_resources?' in url:
                return Response(url, json.dumps({'resources': [
                    {'name': role, 'path': row['url'], 'version': row['version']}
                    for role, row in fixture.generation['layers'].items()]}).encode())
            if '/index_' in url: return Response(url, layer_body)
            return (table_http if '/00000018/' in url else navigation_http)(request, **options)
        return PublisherTransport(ctx, hosts=hosts, opener=server)
    provider = game.create_provider(platform='windows', transport_factory=transport)
    # Only the upstream client code recognizer is a fixture seam; real source
    # receipt/index/table parsers, HTTP, contexts and all stage guards run.
    monkeypatch.setattr(provider, '_runtime', lambda: None)
    monkeypatch.setattr(provider, '_text_bootstrap', lambda ctx, identity, transport, upstream: NS())
    monkeypatch.setattr(provider, '_common', lambda _: fixture.common)
    return provider, fixture, navigation


@pytest.mark.parametrize('older_stage', ['original-text-navigation-pending', 'original-text-navigation-verified',
                                       'original-presentation-containers-downloaded'])
def test_older_normal_continuation_cannot_skip_authored_validation(tmp_path, monkeypatch, older_stage):
    provider, fixture, _ = provider_fixture(tmp_path, monkeypatch, 'text')
    try:
        reference = fixture.retained()
        tables_stage = {'schema': 1, 'stage': 'original-text-tables-downloaded', 'client': fixture.client,
            'request': fixture.request.json(), 'source': {'stage': 'client-bootstrap-downloaded'}, 'text': reference}
        stage = {'schema': 1, 'stage': older_stage, 'client': fixture.client,
                 'request': fixture.request.json(), 'tables': tables_stage}
        if older_stage == 'original-presentation-containers-downloaded':
            stage['source'] = {'generation_sha256': hashlib.sha256(game._json_bytes(fixture.generation)).hexdigest()}
        ctx = fixture.context(); ctx.stage_handle = stage
        plan = provider.plan(fixture.request, ctx)
        assert plan.stage == 'original-authored-table-validation' and plan.handle['resume'] == stage
        result = provider.download(plan, fixture.context('download', plan.download_bytes))
        assert result.restore_handle['resume']['stage'] == older_stage
        assert result.restore_handle['resume']['tables']['authored_validation']['receipt_sha256']
    finally: fixture.service.close()


def test_valid_changed_index_reenters_original_text_plan_without_reset_or_hidden_body_read(tmp_path, monkeypatch):
    provider, fixture, _ = provider_fixture(tmp_path, monkeypatch, 'text')
    try:
        reference = fixture.retained()
        upstream = {'schema': 1, 'stage': 'client-bootstrap-downloaded', 'client': fixture.client,
                    'request': fixture.request.json(), 'receipt_sha256': 'b' * 64}
        previous = {'schema': 1, 'stage': 'original-text-tables-downloaded', 'client': fixture.client,
                    'request': fixture.request.json(), 'source': upstream, 'text': reference}
        old_catalog = text.Catalog(fixture.context(), fixture.client, fixture.common, reference)
        old_value = old_catalog.file('TableCfg/DialogTextTable.json')
        planning = fixture.context(); planning.stage_handle = previous
        quote = provider.plan(fixture.request, planning)
        fixture.change_second_index = True
        result = provider.download(quote, fixture.context('download', quote.download_bytes))
        assert isinstance(result, PreparationStage) and result.restore_handle == upstream
        assert not list(tmp_path.rglob('endfield-authored-tables/receipts/*.json'))
        planning = fixture.context(); planning.stage_handle = result.restore_handle
        calls = len(fixture.calls)
        updated = provider.plan(fixture.request, planning)
        assert updated.stage == 'original-text-tables' and updated.handle['text']['payload_bytes'] > 0
        assert all(url.endswith('.blc') for url in fixture.calls[calls:])
        assert old_catalog.file('TableCfg/DialogTextTable.json') == old_value
    finally: fixture.service.close()


def test_huge_current_index_is_only_quoted_not_hidden_in_plan_metadata(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    try:
        reference = fixture.retained()
        real = fixture.transport(fixture.context())
        class Header:
            def fetch_bytes(self, url, **options):
                assert options['original_range'] == (0, 16, None) and options['kind'] == 'metadata'
                data, receipt = real.fetch_bytes(url, **options)
                from dataclasses import replace
                return data, replace(receipt, original_range=(0, 16, 16 * 1024**2))
        quote = source.plan(fixture.context(), fixture.client, fixture.common, fixture.generation, reference, Header())
        assert quote['wire_index_recheck_bytes'] == 32 * 1024**2
        assert len(fixture.header_calls) == 1 and not fixture.index_calls
    finally: fixture.service.close()


def test_interrupted_publication_keeps_no_receipt_then_retries_same_original_source(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    try:
        reference = fixture.retained(); quote = fixture.quote(reference)
        helpers = source._helpers
        def interrupt():
            write, error, no_links = helpers()
            def fail_receipt(path, raw):
                if path.parent.name == 'receipts': raise OSError('Authored storage interruption')
                return write(path, raw)
            return fail_receipt, error, no_links
        with monkeypatch.context() as patch:
            patch.setattr(source, '_helpers', interrupt)
            with pytest.raises(OSError, match='storage interruption'): fixture.validate(quote)
        assert not list(tmp_path.rglob('endfield-authored-tables/receipts/*.json'))
        result, ctx = fixture.validate(quote)
        assert source.restore(ctx, fixture.client, fixture.common, fixture.generation, result, reference)['facts_bytes']
    finally: fixture.service.close()


@pytest.mark.parametrize('change', ['facts', 'receipt'])
def test_ordinary_preparation_quotes_local_evidence_repair_without_losing_original_source(tmp_path, monkeypatch, change):
    provider, fixture, _ = provider_fixture(tmp_path, monkeypatch, 'text')
    try:
        reference = fixture.retained()
        stage = {'schema': 1, 'stage': 'original-text-tables-downloaded', 'client': fixture.client,
            'request': fixture.request.json(), 'source': {'stage': 'client-bootstrap-downloaded'}, 'text': reference}
        ctx = fixture.context(); ctx.stage_handle = stage
        quote = provider.plan(fixture.request, ctx)
        result = provider.download(quote, fixture.context('download', quote.download_bytes))
        folder = 'facts' if change == 'facts' else 'receipts'
        next((fixture.context().cache_directory / 'endfield-authored-tables' / folder).iterdir()).write_bytes(b'corrupt')
        ctx = fixture.context(); ctx.stage_handle = result.restore_handle
        with monkeypatch.context() as patch:
            patch.setattr(tables, 'read', lambda *_: pytest.fail('Repair planning must not decode source bodies'))
            repair = provider.plan(fixture.request, ctx)
        assert repair.stage == 'original-authored-table-validation'
        repaired = provider.download(repair, fixture.context('download', repair.download_bytes))
        assert repaired.restore_handle['resume']['text'] == reference
    finally: fixture.service.close()


def test_validated_stage_replans_same_client_resource_hotfix_and_keeps_old_facts(tmp_path, monkeypatch):
    provider, fixture, _ = provider_fixture(tmp_path, monkeypatch, 'text')
    try:
        reference = fixture.retained()
        upstream = {'schema': 1, 'stage': 'client-bootstrap-downloaded', 'client': fixture.client,
                    'request': fixture.request.json(), 'receipt_sha256': 'b' * 64}
        stage = {'schema': 1, 'stage': 'original-text-tables-downloaded', 'client': fixture.client,
                 'request': fixture.request.json(), 'source': upstream, 'text': reference}
        ctx = fixture.context(); ctx.stage_handle = stage
        quote = provider.plan(fixture.request, ctx)
        result = provider.download(quote, fixture.context('download', quote.download_bytes))
        old_facts = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in source._root(fixture.context()).rglob('*.json')}
        fixture.generation['layers']['main']['url'] = fixture.generation['layers']['main']['url'].replace('300-1_', '301-2_')
        fixture.generation['layers']['main']['version'] = '301-2'
        ctx = fixture.context(); ctx.stage_handle = result.restore_handle
        before = len(fixture.calls)
        updated = provider.plan(fixture.request, ctx)
        assert updated.stage == 'original-text-tables' and updated.handle['source'] == upstream
        assert updated.handle['text']['generation'] != quote.handle['validation']['generation']
        assert all(url.endswith('.blc') for url in fixture.calls[before:])
        assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in old_facts.items())
    finally: fixture.service.close()
