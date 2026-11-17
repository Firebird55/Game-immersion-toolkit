"""Small owned original containers verify bounds, overlays and atomic blocks."""
import pytest

from backend import nte_graph_prefetch as prefetch, nte_release as release
from backend.tests.test_nte_publisher_iostore import prepare
from backend.preparation_errors import PreparationFailure


def test_prefetch_reads_only_selected_complete_blocks_and_restarts_offline(tmp_path, monkeypatch):
    opened, _, ranges = prepare(monkeypatch, tmp_path)
    source = opened(); containers = {'Paks/owned.utoc': source}
    report = prefetch.prefetch(containers, {'HT/a.uasset': 80})
    assert report['complete'] and report['new_compressed_bytes_upper_bound'] == 96
    assert ranges == [(0, 96)] and not (source.root/'2.block').exists()
    assert source.read('HT/a.uasset') == b'A'*80
    monkeypatch.setattr(prefetch, 'MAX_NEW_BYTES', 0)
    assert prefetch.prefetch(containers, {'HT/a.uasset': 80})['new_compressed_bytes_upper_bound'] == 0
    assert ranges == [(0, 96)]


def test_nonadjacent_stored_blocks_never_fetch_unsigned_gaps(tmp_path, monkeypatch):
    opened, _, ranges = prepare(monkeypatch, tmp_path, gap=True)
    source = opened()
    report = prefetch.prefetch({'Paks/owned.utoc': source}, {'HT/a.uasset': 80})
    assert report['requests_upper_bound'] == 2 and report['workers'] <= 8
    assert sorted(ranges) == [(0, 64), (80, 32)]


@pytest.mark.parametrize('change', ['missing', 'size', 'collision', 'bytes', 'blocks', 'transfer'])
def test_untrusted_inventory_or_budget_never_starts_a_source_download(tmp_path, monkeypatch, change):
    opened, _, ranges = prepare(monkeypatch, tmp_path)
    source = opened(); packages = {'HT/a.uasset': 80}
    if change == 'missing': packages = {'HT/missing.uasset': 80}
    elif change == 'size': packages = {'HT/a.uasset': 79}
    elif change == 'collision': packages['ht/A.uasset'] = 80
    elif change == 'bytes': monkeypatch.setattr(prefetch, 'MAX_PACKAGE_BYTES', 79)
    elif change == 'blocks': monkeypatch.setattr(prefetch, 'MAX_BLOCKS', 1)
    else: monkeypatch.setattr(prefetch, 'MAX_NEW_BYTES', 95)
    with pytest.raises(PreparationFailure): prefetch.prefetch({'Paks/owned.utoc': source}, packages)
    assert not ranges


def test_corrupt_source_does_not_publish_any_block_in_its_run(tmp_path, monkeypatch):
    opened, _, _ = prepare(monkeypatch, tmp_path)
    source = opened()
    monkeypatch.setattr(release, 'read_range', lambda _r, _b, _i, _at, size: bytes(size))
    with pytest.raises(PreparationFailure):
        prefetch.prefetch({'Paks/owned.utoc': source}, {'HT/a.uasset': 80})
    assert not list(source.root.glob('*.block'))


def test_equal_priority_claims_are_rejected_and_patch_priority_is_explicit(tmp_path, monkeypatch):
    opened, _, ranges = prepare(monkeypatch, tmp_path)
    source = opened()
    with pytest.raises(PreparationFailure):
        prefetch.plan({'Paks/one.utoc': source, 'Paks/two.utoc': source}, {'HT/a.uasset': 80})
    report = prefetch.prefetch({'Paks/base.utoc': source, 'PatchPaks/patch_0_P.utoc': source}, {'HT/a.uasset': 80})
    assert report['complete'] and ranges == [(0, 96)]
