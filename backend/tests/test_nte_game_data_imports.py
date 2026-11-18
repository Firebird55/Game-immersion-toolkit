"""Required imports retain exact original ownership and quote before transfer."""
import hashlib
import struct
from dataclasses import replace
from types import SimpleNamespace
import threading

import pytest

from backend import nte_game_data_imports as imports
from backend.game_data_protocol import GameDataError
from backend.nte_publisher_iostore import Container, Block
from backend.nte_publisher_pak import Archive
from backend.nte_release import File


def fixture(tmp_path):
    data = (b'original-first', b'original-second')
    source = object.__new__(Container); source.root = tmp_path/'blocks'
    source.toc, source.ucas = File(10, 'a'*32, 10, 'a'*32, 0), File(99, 'b'*32, 99, 'b'*32, 0)
    source.blocks = (Block(10, len(data[0]), len(data[0]), 0, len(data[0]), hashlib.sha1(data[0]).digest()),
        Block(10+len(data[0]), len(data[1]), len(data[1]), 0, len(data[1]), hashlib.sha1(data[1]).digest()))
    ctx = SimpleNamespace(cache_directory=tmp_path/'cache', check=lambda: None, transfer_lock=threading.RLock())
    owner = {'reader': {'source_sha256': 'c'*64, 'dependencies_sha256': 'd'*64},
        'metadata_receipt': 'e'*64, 'metadata_recipe': {'imports': {'indices': {
            'request': {'region': 'global', 'source_locale': 'ja', 'target_locales': ['en'], 'content_mode': 'text'},
            'verification': {'https://publisher.invalid/source': {'bytes': 9, 'sha256': 'f'*64}}}}}}
    recorder = imports.RequestedBlocks(ctx); recorder.values = {'PatchPaks/owned.utoc': source}
    return source, data, ctx, owner, recorder


@pytest.mark.parametrize('fault', [None, 'foreign', 'misaligned', 'size', 'shared-owner', 'float-offset'])
def test_reader_missing_range_is_only_an_exact_contiguous_claim_from_owned_current_sources(tmp_path, fault):
    source, data, ctx, owner, recorder = fixture(tmp_path)
    selected, start, size = source, 10, sum(map(len, data))
    if fault == 'foreign': selected = object.__new__(Container); selected.blocks = source.blocks
    if fault == 'misaligned': start += 1
    if fault == 'size': size -= 1
    if fault == 'float-offset': start = float(start)
    if fault == 'shared-owner': recorder.values['Paks/foreign.utoc'] = source
    with pytest.raises(GameDataError) as error:
        recorder(selected, start, size)
    assert error.value.code == ('nte_required_imports_changed' if fault else 'nte_original_bytes_missing')
    assert bool(recorder.rows) is (fault is None)
    assert not list(ctx.cache_directory.rglob('*'))


def test_required_import_receipt_and_quote_reject_reader_locale_and_toc_drift_then_continue_only_missing_blocks(tmp_path):
    source, data, ctx, owner, recorder = fixture(tmp_path)
    with pytest.raises(GameDataError): recorder(source, 10, sum(map(len, data)))
    digest = imports.publish(owner, list(recorder.rows.values()), ctx)
    quote = imports.plan(owner, recorder.values, ctx)
    assert quote.download_bytes == sum(map(len, data))+18
    assert quote.handle['receipt'] == digest and len(quote.handle['ranges']) == 2
    assert not list(source.root.rglob('*'))
    for field in ('reader', 'locale', 'mode'):
        import copy
        wrong = copy.deepcopy(owner)
        if field == 'reader': wrong['reader']['dependencies_sha256'] = '0'*64
        if field == 'locale': wrong['metadata_recipe']['imports']['indices']['request']['source_locale'] = 'ko'
        if field == 'mode': wrong['metadata_recipe']['imports']['indices']['request']['content_mode'] = 'text-audio'
        assert imports.retained(wrong, ctx) is None
    saved = source.toc; source.toc = replace(saved, digest='0'*32)
    with pytest.raises(GameDataError): imports.plan(owner, recorder.values, ctx)
    source.toc = saved
    source._store(0, data[0])
    continuation = imports.plan(owner, recorder.values, ctx)
    assert continuation.download_bytes == len(data[1])+18 and continuation.handle['ranges'] == [{'toc': 'PatchPaks/owned.utoc', 'first': 1, 'stop': 2}]
    source._store(1, data[1])
    assert imports.plan(owner, recorder.values, ctx) is None
    receipt = imports._base(ctx)/(digest+'.receipt.json'); original = receipt.read_bytes()
    receipt.write_bytes(original+b'!')
    assert imports.retained(owner, ctx) is None
    receipt.write_bytes(original)
    assert imports.retained(owner, ctx)[0] == digest


def header_fixture(tmp_path, *, gap=False, fault=None, block_bytes=16):
    """Parse a complete authored signed-v8 TOC; no game data or transfers."""
    source, _, ctx, owner, recorder = fixture(tmp_path)
    identity = bytes.fromhex('123456789abcdef0')
    header_id = identity+b'\0\0\0\x06'
    if fault == 'foreign-id': header_id = b'foreign!'+b'\0\0\0\x06'
    if fault == 'index': header_id = identity+b'\0\1\0\x06'
    if fault == 'type': header_id = identity+b'\0\0\0\x07'
    if fault == 'padding': header_id = identity+b'\0\0\1\x06'
    ids = [b'neighbor'+b'\0\0\0\x01', header_id, b'unrelated'+b'\0\0\x01']
    locations = [(0, block_bytes), (block_bytes, 3*block_bytes), (4*block_bytes, block_bytes)]
    if fault == 'duplicate': ids.append(header_id); locations.append((block_bytes, 3*block_bytes))
    if fault == 'overlap': locations[2] = (32, 16)
    if fault == 'shared-boundary': locations[1] = (16, 36); locations[2] = (52, 12)
    if fault == 'empty-header': locations[1] = (block_bytes, 0)
    chunks = [bytes([index+65])*block_bytes for index in range(5)]
    stored = bytearray(); records = []
    for index, chunk in enumerate(chunks):
        if gap and index in (2, 3): stored.extend(b'gap-gap')
        offset = len(stored); stored.extend(chunk)
        records.append(offset.to_bytes(5, 'little')+len(chunk).to_bytes(3, 'little')+
            len(chunk).to_bytes(3, 'little')+b'\0')
    raw = bytearray(144); raw[:16] = b'-==--==--==--==-'; raw[16] = 8
    struct.pack_into('<9I', raw, 20, 144, len(ids), 5, 12, 0, 32, block_bytes, 0, 1)
    raw[56:64] = bytes(8) if fault == 'zero-id' else identity
    raw[80] = 4; struct.pack_into('<Q', raw, 88, 2**64-1)
    raw = bytes(raw)+b''.join(ids)+b''.join(at.to_bytes(5, 'big')+size.to_bytes(5, 'big')for at, size in locations)+b''.join(records)
    raw += struct.pack('<I', 4)+b'signsign'+b''.join(hashlib.sha1(chunk).digest()for chunk in chunks)+bytes(len(ids)*24)
    def descriptor(data):
        digest = hashlib.md5(data).hexdigest()
        return File(len(data), digest, len(data), digest, 0)
    toc, ucas = descriptor(raw), descriptor(stored)
    root = ctx.cache_directory/'iostore'/'nte-global'/toc.digest/ucas.digest
    root.mkdir(parents=True); (root/'index.utoc').write_bytes(raw)
    archive = object.__new__(Archive); archive.source = SimpleNamespace(region='nte-global', branch='PC_150')
    archive.encryption_guid, archive.selected_key = bytes(16), None
    def no_network(*_args): raise AssertionError('Quote processing must not acquire data')
    source = Container('nte-global', 'PC_150', toc, ucas, [archive], ctx.cache_directory/'iostore', range_reader=no_network)
    recorder.values = {'PatchPaks/owned.utoc': source}
    return source, chunks, ctx, owner, recorder


@pytest.mark.parametrize('gap', [False, True])
def test_one_missing_header_block_quotes_its_exact_complete_owner_once_without_adjacent_package(tmp_path, gap):
    source, chunks, ctx, owner, recorder = header_fixture(tmp_path, gap=gap)
    previous = ctx.cache_directory/'current.json'; previous.write_bytes(b'old complete library')
    for index in (2, 1):
        with pytest.raises(GameDataError, match='Additional original'):
            recorder(source, source.blocks[index].offset, source.blocks[index].length)
    assert len(recorder.rows) == 1
    assert [(row['first'], row['stop'])for row in recorder.rows.values()] == [(1, 4)]
    receipt = imports.publish(owner, list(recorder.rows.values()), ctx)
    quote = imports.plan(owner, recorder.values, ctx)
    assert quote.download_bytes == 3*16+18
    assert quote.handle['ranges'] == [{'toc': 'PatchPaks/owned.utoc', 'first': i, 'stop': i+1}for i in (1, 2, 3)]
    assert not list(source.root.glob('*.block'))
    assert previous.read_bytes() == b'old complete library'
    # Different original owners cannot reuse consent even at the same size.
    original = source.ucas; source.ucas = replace(original, digest='0'*32)
    with pytest.raises(GameDataError): imports.plan(owner, recorder.values, ctx)
    source.ucas = original
    assert imports.retained(owner, ctx)[0] == receipt
    for index in (1, 2, 3): source._store(index, chunks[index])
    assert imports.plan(owner, recorder.values, ctx) is None
    assert not (source.root/'0.block').exists() and not (source.root/'4.block').exists()
    assert previous.read_bytes() == b'old complete library'


@pytest.mark.parametrize('fault', ['zero-id', 'foreign-id', 'index', 'type', 'padding', 'duplicate', 'overlap', 'shared-boundary', 'empty-header'])
def test_unproven_or_ambiguous_header_owner_keeps_the_original_single_range(tmp_path, fault):
    source, _, ctx, owner, recorder = header_fixture(tmp_path, fault=fault)
    with pytest.raises(GameDataError): recorder(source, source.blocks[2].offset, source.blocks[2].length)
    assert [(row['first'], row['stop'])for row in recorder.rows.values()] == [(2, 3)]
    imports.publish(owner, list(recorder.rows.values()), ctx)
    assert imports.plan(owner, recorder.values, ctx).download_bytes == 16+18
    assert not list(source.root.glob('*.block'))


def test_header_expansion_rejects_a_changed_toc_without_publishing_a_new_request(tmp_path):
    source, _, ctx, _, recorder = header_fixture(tmp_path)
    source.raw += b'!'
    with pytest.raises(GameDataError) as error: recorder(source, source.blocks[2].offset, source.blocks[2].length)
    assert error.value.code == 'nte_required_imports_changed' and not recorder.rows
    assert not imports._base(ctx).exists()


@pytest.mark.parametrize('fault', [None, 'checksum', 'consent', 'old-consent'])
def test_header_download_keeps_quote_source_hashes_and_previous_library_gates(tmp_path, monkeypatch, fault):
    source, chunks, ctx, owner, recorder = header_fixture(tmp_path, gap=True)
    previous = ctx.cache_directory/'current.json'; previous.write_bytes(b'previous complete source')
    with pytest.raises(GameDataError): recorder(source, source.blocks[2].offset, source.blocks[2].length)
    imports.publish(owner, list(recorder.rows.values()), ctx)
    quote = imports.plan(owner, recorder.values, ctx)
    handle = owner['metadata_recipe']['imports']['indices']; handle['files'] = []
    reader = SimpleNamespace(identity=owner['reader'])
    # These pre-existing source gates have independent original-input tests.
    # Exercise the actual required-import receipt/quote and download path here.
    monkeypatch.setattr(imports.content, 'validate_handle', lambda *_a: (ctx.cache_directory, 'publisher.invalid'))
    monkeypatch.setattr(imports.processing, '_read', lambda *_a: {'receipt': owner['metadata_receipt']})
    monkeypatch.setattr(imports.imports, 'containers', lambda *_a: recorder.values)
    ctx.progress = lambda *_a: None
    # The receipt must include exactly the request being prepared.
    imports.publish(owner, list(recorder.rows.values()), ctx)
    quote = imports.plan(owner, recorder.values, ctx)
    if fault in ('consent', 'old-consent'):
        first = 0 if fault == 'consent' else 2
        wrong = {**quote.handle, 'ranges': [{'toc': 'PatchPaks/owned.utoc', 'first': first, 'stop': first+1}]}
        quote = replace(quote, handle=wrong, revision='nte-required-imports-'+imports.content._identity(wrong))
    calls = []
    def fetch(url, **options):
        calls.append(options)
        if options['kind'] == 'metadata': return b'metadata', SimpleNamespace(bytes=9)
        at, size, total = options['original_range']
        index = next(index for index, block in enumerate(source.blocks) if block.offset == at)
        assert index in (1, 2, 3) and size == 16 and total == source.ucas.size
        data = bytes(16) if fault == 'checksum' else chunks[index]
        return data, SimpleNamespace(bytes=len(data))
    transport = SimpleNamespace(fetch_bytes=fetch)
    if fault:
        with pytest.raises(GameDataError) as error: imports.download(quote, ctx, reader, transport)
        assert error.value.code == ('publisher_checksum_mismatch' if fault == 'checksum' else 'nte_required_imports_changed')
        assert not list(source.root.glob('*.block'))
        if fault in ('consent', 'old-consent'): assert calls == []
    else:
        result = imports.download(quote, ctx, reader, transport)
        assert result.restore_handle['transferred_bytes'] == quote.download_bytes == 66
        assert len([call for call in calls if call['kind'] == 'metadata']) == 2
        assert len([call for call in calls if call['kind'] == 'asset']) == 3
        assert not (source.root/'0.block').exists() and not (source.root/'4.block').exists()
    assert previous.read_bytes() == b'previous complete source'


def test_retained_single_block_receipt_gets_a_new_complete_quote_without_rewriting_its_provenance(tmp_path):
    source, _, ctx, owner, recorder = header_fixture(tmp_path, gap=True)
    original_request = {'toc': 'PatchPaks/owned.utoc', 'toc_md5': source.toc.digest,
        'ucas_md5': source.ucas.digest, 'first': 2, 'stop': 3}
    digest = imports.publish(owner, [original_request], ctx)
    path = imports._base(ctx)/(digest+'.receipt.json'); before = path.read_bytes()
    quote = imports.plan(owner, recorder.values, ctx)
    assert quote.handle['receipt'] == digest
    assert quote.handle['ranges'] == [{'toc': 'PatchPaks/owned.utoc', 'first': index, 'stop': index+1}for index in (1, 2, 3)]
    assert path.read_bytes() == before
    assert not list(source.root.glob('*.block'))


def test_large_header_is_one_exact_quote_partitioned_at_existing_receipt_and_transfer_bounds(tmp_path):
    source, _, ctx, owner, recorder = header_fixture(tmp_path, gap=True, block_bytes=2*1024**2)
    with pytest.raises(GameDataError): recorder(source, source.blocks[2].offset, source.blocks[2].length)
    rows = list(recorder.rows.values())
    assert [(row['first'], row['stop'])for row in rows] == [(1, 3), (3, 4)]
    assert all(sum(block.length for block in source.blocks[row['first']:row['stop']]) <= 4*1024**2 for row in rows)
    imports.publish(owner, rows, ctx)
    quote = imports.plan(owner, recorder.values, ctx)
    assert quote.download_bytes == 6*1024**2+18
    assert quote.handle['ranges'] == [{'toc': 'PatchPaks/owned.utoc', 'first': i, 'stop': i+1}for i in (1, 2, 3)]
    assert not list(source.root.glob('*.block'))


def test_header_beyond_aggregate_stage_budget_keeps_the_original_narrow_request(tmp_path, monkeypatch):
    source, _, ctx, owner, recorder = header_fixture(tmp_path)
    monkeypatch.setattr(imports, 'MAX_BYTES', 32)
    with pytest.raises(GameDataError): recorder(source, source.blocks[2].offset, source.blocks[2].length)
    assert [(row['first'], row['stop'])for row in recorder.rows.values()] == [(2, 3)]
    imports.publish(owner, list(recorder.rows.values()), ctx)
    assert imports.plan(owner, recorder.values, ctx).download_bytes == 16+18
