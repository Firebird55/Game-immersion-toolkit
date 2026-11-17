"""Original acquisition refreshes codec data only after a container rejection."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import genshin_official_source as source
from backend.tests.test_genshin_original_containers import bundle, catalog
from backend.tests.test_genshin_original_textmap import parameters


def build():
    return {'channel': 'genshin-global', 'version': '9.4.0', 'manifests': {'game': []},
            'hotfix': {'revisions': {'res': [1, 'a'], 'design': [2, 'b'], 'silence': [3, 'c'], 'audio': [1, 'd']},
                       'indexes': {'design': ['a' * 32, 1]}}}


def test_whole_authenticated_original_package_reopens_cached_body_without_executing_codec(tmp_path, monkeypatch):
    directory = tmp_path / 'tools/genshin-original-text'; directory.mkdir(parents=True)
    publisher = directory.parent / 'sophon/genshin-packages'; publisher.mkdir(parents=True)
    raw = b'authored original publisher container fixture'
    digest = hashlib.md5(raw).hexdigest(); (publisher / digest).write_bytes(raw)
    listing = {'remoteName': source.INDEX_PACKAGE, 'fileSize': len(raw), 'md5': digest}
    unused = {'remoteName': 'blocks/00/1234.blk', 'fileSize': source.blb.MAX_PACKAGE + 1, 'md5': 'e' * 32}
    monkeypatch.setattr(source.hotfix, 'index', lambda *a: json.dumps(listing).encode() + b'\n' + json.dumps(unused).encode())
    calls = []
    def decode(original, parameters, destination, *, work):
        calls.append(original.read_bytes())
        destination.write_bytes(b'bounded decoded fixture')
    def unpack(decoded, destination):
        assert decoded.read_bytes() == b'bounded decoded fixture'
        destination.write_bytes(bundle([('0000006f', 1)], payload=catalog()))
    monkeypatch.setattr(source.blb, 'unpack', unpack)
    spec = parameters()
    monkeypatch.setattr(source.Source, 'native_parameters', lambda self: ((spec,), {'owned': 'authored fixture'}))
    helper = SimpleNamespace(identity='c' * 64, decode=decode)
    receipt = {'parameters_sha256': 'd' * 64}
    first = source.Source(directory, build(), helper, directory / 'private', receipt)
    assert len(calls) == 1 and len(first.catalog.assets) == 1
    monkeypatch.setattr(source.hotfix, '_download_package', lambda *a: pytest.fail('An unsupported unselected container was downloaded'))
    with pytest.raises(ValueError):
        first.objects(unused['remoteName'])
    def reject_decode(*args, **kwargs):
        calls.append(b'rejected')
        raise ValueError('A verified cached body ran the codec again')
    monkeypatch.setattr(helper, 'decode', reject_decode)
    reopened = source.Source(directory, build(), helper, directory / 'private', receipt)
    assert reopened.catalog.sha256 == first.catalog.sha256
    before = dict(first.package_receipts)
    body = next((directory / 'bodies').glob('*.json'))
    corrupted = json.loads(body.read_bytes()); corrupted['owner']['package']['md5'] = '0' * 32
    body.write_text(json.dumps(corrupted))
    with pytest.raises(source.CodecRejected):
        source.Source(directory, build(), helper, directory / 'private', receipt)
    assert len(calls) == 2 and first.package_receipts == before


@pytest.mark.parametrize('failure', ['native-schema', 'publisher-index', 'codec'])
def test_parameter_refresh_is_bounded_and_does_not_mask_native_or_publisher_failures(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(source.blb, 'helper', lambda directory: object())
    loads = []
    def load(directory, **kwargs):
        loads.append(kwargs)
        return tmp_path / 'private', {'sha256': ('b' if kwargs else 'a') * 64}
    monkeypatch.setattr(source.codec, 'load', load)
    attempts = []
    def construct(*args):
        attempts.append(True)
        if failure == 'codec': raise source.CodecRejected('unsupported original container')
        raise ValueError('unsupported ' + failure)
    monkeypatch.setattr(source, 'Source', construct)
    with pytest.raises(ValueError): source.prepare(tmp_path, build())
    assert len(attempts) == (2 if failure == 'codec' else 1)
    assert loads == ([{}, {'refresh': True}] if failure == 'codec' else [{}])
