"""Controlled codec descriptions retain exact immutable bytes across retries."""
import hashlib
import json
from urllib.error import URLError

import pytest

from backend import genshin_blb_parameters as profiles
from backend.tests.test_genshin_blb import source


def test_pinned_profile_reopens_offline_and_corruption_retries_the_same_revision(tmp_path, monkeypatch):
    raw, commit = source(), 'a' * 40
    monkeypatch.setattr(profiles, 'SEED', {'revision': commit, 'sha256': hashlib.sha256(raw).hexdigest()})
    requests = []
    def download(url, **kwargs):
        requests.append(url)
        assert f'/{commit}/' in url and url.endswith('/' + profiles.RELATIVE)
        return raw
    monkeypatch.setattr(profiles, 'download', download)
    path, receipt = profiles.load(tmp_path)
    assert len(requests) == 1 and path.read_bytes()
    before = path.read_bytes()
    monkeypatch.setattr(profiles, 'download', lambda *a, **k: pytest.fail('A valid pinned profile queried a moving source'))
    assert profiles.load(tmp_path, pinned=receipt) == (path, receipt)
    (tmp_path / (commit + '.private-source')).write_bytes(b'changed source')
    def offline(*args, **kwargs): raise URLError('offline')
    monkeypatch.setattr(profiles, 'download', offline)
    with pytest.raises(URLError): profiles.load(tmp_path, pinned=receipt)
    assert path.read_bytes() == before
    monkeypatch.setattr(profiles, 'download', download)
    assert profiles.load(tmp_path, pinned=receipt) == (path, receipt)
    assert len(requests) == 2
    assert not any(name in json.dumps(receipt) for name in ('GF256Exp', 'Blb3Key', 'Blb3SBox'))


def test_live_refresh_resolves_once_then_fetches_only_that_immutable_description(tmp_path, monkeypatch):
    raw, commit, calls = source(), 'b' * 40, []
    def download(url, **kwargs):
        calls.append(url)
        return json.dumps({'sha': commit}).encode() if url.endswith('/commits/master') else raw
    monkeypatch.setattr(profiles, 'download', download)
    _, receipt = profiles.load(tmp_path, refresh=True)
    assert receipt['revision'] == commit and len(calls) == 2 and f'/{commit}/' in calls[1]
    with pytest.raises(ValueError): profiles.load(tmp_path, pinned=receipt, refresh=True)


@pytest.mark.parametrize('revision', ['master', '../data', 'a' * 39, 'A' * 40])
def test_unpinned_revision_never_constructs_a_download(tmp_path, monkeypatch, revision):
    monkeypatch.setattr(profiles, 'download', lambda *a, **k: pytest.fail('Unpinned helper data was requested'))
    with pytest.raises(ValueError): profiles.load(tmp_path, pinned={'revision': revision})
