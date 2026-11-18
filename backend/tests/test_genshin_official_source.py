"""Official codec candidates are selected by complete publisher input, fail closed."""
import hashlib
import importlib.util
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


@pytest.mark.parametrize('change', ['receipt', 'genshin_blb_body', 'raw_lz4'])
def test_cached_body_requires_the_original_package_and_current_parser(tmp_path, monkeypatch, change):
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
    if change == 'receipt':
        corrupted = json.loads(body.read_bytes())
        corrupted['owner']['package']['md5'] = '0' * 32
        body.write_text(json.dumps(corrupted))
    else:
        module = importlib.util.find_spec('backend.' + change)
        code = module.loader.get_code(module.name)
        monkeypatch.setattr(module.loader, 'get_code',
            lambda _: code.replace(co_consts=(*code.co_consts, 'changed parser')))
    previous_receipt = body.read_bytes()
    with pytest.raises(source.CodecRejected):
        source.Source(directory, build(), helper, directory / 'private', receipt)
    assert len(calls) == 2 and first.package_receipts == before
    assert body.read_bytes() == previous_receipt


@pytest.mark.parametrize('outcomes', [('reject', 'accept'), ('accept', 'accept'), ('reject', 'reject'), ('native-error', 'accept')])
def test_all_official_candidates_are_checked_without_community_fallback(tmp_path, monkeypatch, outcomes):
    from backend.genshin_blb_native import Candidate
    monkeypatch.setattr(source.blb, 'helper', lambda directory: object())
    native = tmp_path / 'official-native'; native.write_bytes(b'original native fixture')
    owner = {'sha256': 'a' * 64, 'publisher_md5': 'b' * 32, 'bytes': 1024}
    monkeypatch.setattr(source, 'official_native', lambda *a: (native, owner))
    monkeypatch.setattr(source, 'Image', lambda value: value)
    candidates = tuple(Candidate(bytes([i]), ('c' * 64,)) for i in range(2))
    monkeypatch.setattr(source, 'discover_candidates', lambda image: candidates)
    attempts = []
    def construct(directory, build, helper, parameters, receipt, **kwargs):
        assert receipt['policy'] == 'official-native-blb-parameters-v1'
        assert receipt['parameters_sha256'] == hashlib.sha256(parameters.read_bytes()).hexdigest()
        assert kwargs['native_input'] == (native, owner)
        outcome = outcomes[len(attempts)]
        attempts.append(True)
        if outcome == 'reject': raise source.CodecRejected('unsupported original container')
        if outcome == 'native-error': raise ValueError('unsupported native schema')
        return SimpleNamespace(accepted=True)
    monkeypatch.setattr(source, 'Source', construct)
    if outcomes == ('reject', 'accept'):
        assert source.prepare(tmp_path, build()).accepted
    else:
        with pytest.raises(ValueError): source.prepare(tmp_path, build())
    assert len(attempts) == (1 if outcomes[0] == 'native-error' else 2)
