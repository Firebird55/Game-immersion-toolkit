"""The managed bridge must not turn its temporary stream into a public reader."""
import hashlib
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from backend.nte_publisher_stream import Broker
from backend.preparation_errors import PreparationFailure


def container(tmp_path, *, fail=False):
    reads = []
    def read(at, size):
        reads.append((at, size))
        if fail:
            raise PreparationFailure('unsupported_game_format', 'Authored corrupt block')
        return bytes(range(32))[at:at + size]
    return SimpleNamespace(raw=b'owned checked toc', ucas=SimpleNamespace(size=32),
                           read_stored=read, root=tmp_path), reads


def request(url):
    # No ambient proxies or credentials are relevant to a private loopback stream.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=2) as response:
        return response.read()


def test_private_reader_exposes_only_registered_bounded_ranges_and_closes(tmp_path):
    source, reads = container(tmp_path)
    with Broker({'Paks/pakchunk1-Windows.utoc': source}) as broker:
        descriptor = broker.descriptors[0]
        assert request(descriptor['toc_url'] + '?offset=0&size=5') == b'owned'
        assert request(descriptor['ucas_url'] + '?offset=7&size=9') == bytes(range(7, 16))
        assert reads == [(7, 9)] and broker.delivered == 14 and broker.failures == []
    with pytest.raises(urllib.error.URLError):
        request(descriptor['toc_url'] + '?offset=0&size=5')


@pytest.mark.parametrize('query,status', [
    ('offset=0&size=33', 416), ('offset=33&size=0', 416),
    ('offset=-1&size=1', 400), ('offset=0&offset=1&size=1', 400),
    ('offset=0&size=1&file=elsewhere', 400), ('offset=0&size=4194305', 416),
    ('offset=0&size=', 400), ('offset=0&size=01', 400),
])
def test_invalid_requests_do_not_reach_publisher_sources(tmp_path, query, status):
    source, reads = container(tmp_path)
    with Broker({'pakchunk1-Windows.utoc': source}) as broker:
        with pytest.raises(urllib.error.HTTPError) as error:
            request(broker.descriptors[0]['ucas_url'] + '?' + query)
        assert error.value.code == status
        assert reads == [] and broker.failures == []


def test_wrong_nonce_or_unknown_source_is_not_an_archive_lookup(tmp_path):
    source, reads = container(tmp_path)
    with Broker({'pakchunk1-Windows.utoc': source}) as broker:
        url = broker.descriptors[0]['ucas_url']
        with pytest.raises(urllib.error.HTTPError) as error:
            request(url.replace('/' + broker.nonce + '/', '/' + 'x' * 43 + '/') + '?offset=0&size=1')
        assert error.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as error:
            request(url.rsplit('/', 1)[0] + '/' + '0' * 32 + '?offset=0&size=1')
        assert error.value.code == 400
        assert reads == []


def test_failed_checksum_is_closed_and_remembered_for_the_parent(tmp_path):
    source, _ = container(tmp_path, fail=True)
    with Broker({'pakchunk1-Windows.utoc': source}) as broker:
        with pytest.raises(urllib.error.HTTPError) as error:
            request(broker.descriptors[0]['ucas_url'] + '?offset=0&size=1')
        assert error.value.code == 502
        assert len(broker.failures) == 1 and broker.delivered == 0


def test_global_alignment_padding_requires_complete_file_verification(tmp_path, monkeypatch):
    from backend import nte_publisher_stream as streams
    source, reads = container(tmp_path)
    data = b'owned global data and alignment padding'
    source.paths = {}
    source.region, source.branch = 'nte-global', 'PC_150'
    source.ucas = SimpleNamespace(size=len(data), digest=hashlib.md5(data).hexdigest())
    downloads = []
    def save(region, branch, item, path):
        downloads.append(item.digest)
        path.write_bytes(data)
    monkeypatch.setattr(streams.release, 'save_file', save)
    with Broker({'Paks/global.utoc': source}) as broker:
        assert request(broker.descriptors[0]['ucas_url'] + '?offset=30&size=8') == data[30:38]
    assert reads == [] and len(downloads) == 1
    def offline(*args):
        raise AssertionError('Verified global cache unexpectedly downloaded')
    monkeypatch.setattr(streams.release, 'save_file', offline)
    with Broker({'Paks/global.utoc': source}) as broker:
        assert request(broker.descriptors[0]['ucas_url'] + '?offset=0&size=5') == b'owned'


def test_complete_global_cache_is_not_accepted_after_corruption(tmp_path, monkeypatch):
    from backend import nte_publisher_stream as streams
    source, _ = container(tmp_path)
    source.paths = {}
    source.region, source.branch = 'nte-global', 'PC_150'
    source.ucas = SimpleNamespace(size=4, digest=hashlib.md5(b'good').hexdigest())
    (tmp_path / 'complete.ucas').write_bytes(b'bad!')
    monkeypatch.setattr(streams.release, 'save_file', lambda _r, _b, _i, p: p.write_bytes(b'bad!'))
    with pytest.raises(PreparationFailure):
        Broker({'global.utoc': source})


@pytest.mark.parametrize('cached', [None, b'bad!', b'good'])
def test_owned_global_requires_a_prior_complete_authenticated_stage_without_implicit_http(tmp_path, monkeypatch, cached):
    from backend import nte_publisher_stream as streams
    source, reads = container(tmp_path)
    source.paths = {}; source.range_reader = lambda *_: pytest.fail('Global range bypass')
    source.region, source.branch = 'nte-global', 'PC_150'
    source.ucas = SimpleNamespace(size=4, digest=hashlib.md5(b'good').hexdigest())
    if cached is not None: (tmp_path/'complete.ucas').write_bytes(cached)
    monkeypatch.setattr(streams.release, 'save_file', lambda *_: pytest.fail('Unplanned global HTTP'))
    if cached != b'good':
        with pytest.raises(PreparationFailure): Broker({'Paks/global.utoc': source})
    else:
        with Broker({'Paks/global.utoc': source}) as broker:
            assert request(broker.descriptors[0]['ucas_url']+'?offset=0&size=4') == b'good'
    assert reads == []


@pytest.mark.parametrize('failure,code', [(OSError('offline'), 'game_metadata_unavailable'),
    (PreparationFailure('unsupported_game_format', 'owned bad block'), 'unsupported_game_format')])
def test_publisher_reader_preserves_source_failure_kind_without_install_access(tmp_path, monkeypatch, failure, code):
    from backend import nte_assets as assets, nte_publisher_stream as streams
    source, _ = container(tmp_path)
    class FailedBroker:
        descriptors = []
        failures = [failure]
        def __enter__(self): return self
        def __exit__(self, *_args): pass
    monkeypatch.setattr(streams, 'Broker', lambda _sources: FailedBroker())
    monkeypatch.setattr(assets, '_reader_invocation', lambda *_args: (['owned-reader'], None, tmp_path))
    monkeypatch.setattr(assets, 'fingerprint', lambda *_args: pytest.fail('Publisher mode touched an installation'))
    monkeypatch.setattr(assets.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=0))
    with pytest.raises(PreparationFailure) as error:
        assets.run_publisher_reader(tmp_path / 'empty-context', tmp_path / 'reader', tmp_path / 'staging',
            {'pakchunk1-Windows.utoc': source}, 'owned-format-parameter', inventory=True)
    assert error.value.code == code


def test_existing_outputs_cannot_masquerade_as_a_successful_fresh_extraction(tmp_path, monkeypatch):
    from backend import nte_assets as assets
    (tmp_path / 'inventory.json').write_text('[]')
    monkeypatch.setattr(assets.subprocess, 'run', lambda *_a, **_k: pytest.fail('Reused stale staging'))
    with pytest.raises(ValueError, match='fresh staging'):
        assets.run_publisher_reader(tmp_path / 'context', tmp_path / 'reader', tmp_path,
                                   {}, 'owned-format-parameter', inventory=True)
