"""Required imports retain exact original ownership and quote before transfer."""
import hashlib
from dataclasses import replace
from types import SimpleNamespace
import threading

import pytest

from backend import nte_game_data_imports as imports
from backend.game_data_protocol import GameDataError
from backend.nte_publisher_iostore import Container, Block
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
