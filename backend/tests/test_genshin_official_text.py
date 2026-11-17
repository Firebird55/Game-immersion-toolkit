"""Normal changed catalogs and parameters retain complete official namespaces."""
from dataclasses import replace

import pytest

from backend import genshin_official_text as text
from backend.genshin_original_containers import DataObjects, DesignCatalog, asset_identity
from backend.tests.test_genshin_original_containers import catalog
from backend.tests.test_genshin_original_textmap import parameters, shard


class Objects(DataObjects):
    def __init__(self, payloads):
        self.payloads = payloads

    def resolve(self, catalog, identity, bundle):
        assert catalog.locate(identity).bundle == bundle
        return self.payloads[identity]


def generation(count=4, *, changed=False):
    spec = parameters(int(changed))
    payloads = {}
    for number in range(count):
        namespace = 'TextMap_Medium' if number < count // 2 else 'TextMap'
        identity = asset_identity(f'Data/_ExcelBinOutput/{namespace}/EN/Hash/{number}')
        payloads[identity] = shard(spec, [(number, f'Generation {int(changed)}, row {number}.')])
    c = DesignCatalog(catalog(tuple(payloads)))
    calls = []
    def load(location):
        calls.append(location.package)
        return Objects(payloads)
    descriptions = [spec, replace(spec, method_sha256='f' * 64)]
    return text.OriginalTables(c, load, descriptions), payloads, calls


def test_original_full_and_medium_files_come_from_the_complete_catalog_inventory():
    source, _, calls = generation()
    assert source.file('TextMap/TextMapEN.json') == {str(n): f'Generation 0, row {n}.' for n in range(4)}
    assert source.file('TextMap/TextMap_MediumEN.json') == {str(n): f'Generation 0, row {n}.' for n in range(2)}
    assert len(calls) == 1
    assert source.receipts['EN']['method_sha256s'] == ['0' * 64, 'f' * 64]
    assert len(source.receipts['EN']['shards']) == 4


def test_normal_update_can_change_shard_count_parameters_and_text_without_reader_update():
    old, _, _ = generation()
    before = old.file('TextMap/TextMapEN.json').copy()
    new, _, _ = generation(8, changed=True)
    assert len(new.file('TextMap/TextMapEN.json')) == 8
    assert new.receipts['EN']['parameters_sha256'] != old.receipts['EN']['parameters_sha256']
    assert old.file('TextMap/TextMapEN.json') == before


@pytest.mark.parametrize('change', ['truncated', 'wrong-shard', 'missing-object', 'catalog-hole', 'two-namespaces'])
def test_failed_current_generation_does_not_activate_partial_tables_or_damage_old(change):
    old, _, _ = generation()
    before = old.file('TextMap/TextMapEN.json').copy()
    new, payloads, _ = generation(8, changed=True)
    identity = next(iter(payloads))
    if change == 'truncated': payloads[identity] = payloads[identity][:-1]
    elif change == 'wrong-shard': payloads[identity] = shard(parameters(1), [(1, 'Wrong low-bit owner.')])
    elif change == 'missing-object': del payloads[identity]
    elif change == 'catalog-hole': del new.catalog.assets[identity]
    else:
        duplicate = asset_identity('Data/_ExcelBinOutput/TextMap/EN/Hash/0')
        new.catalog.assets[duplicate] = new.catalog.assets[identity]
        new.catalog.names[7, (duplicate >> 8) & 0xffffffff] = [duplicate]
    with pytest.raises((ValueError, KeyError)):
        new.file('TextMap/TextMapEN.json')
    assert not new.tables and not new.receipts
    assert old.file('TextMap/TextMapEN.json') == before


def test_no_unknown_locale_or_host_path_can_select_a_text_file():
    source, _, _ = generation()
    for name in ('TextMap/TextMapEN.json/../key', 'TextMap/TextMapBAD.json', 'BinOutput/Talk/a.json'):
        with pytest.raises(ValueError):
            source.file(name)
