import hashlib
import json
from xml.etree import ElementTree

import pytest

from backend import nte_regional_text as regional


def test_release_refresh_and_snapshot_mismatch(monkeypatch, tmp_path):
    newest, older = 'a' * 40, 'b' * 40
    first = b'<ResList version="1.2.3" tag="baseTag" />'
    second = b'<ResList version="1.2.4" tag="baseTag" />'
    blobs = {newest: second, older: first}
    identities = [('PC_120', '1.2.3', hashlib.md5(first).hexdigest())]
    commits = [{'sha': older, 'commit': {'message': '1.2.3 | 2981'}}]

    class Catalog:
        def __init__(self, game, cache, revision=None):
            assert game == 'nte-cn' and cache == tmp_path
            self.revision = revision or newest

        def raw_file(self, path):
            if path == 'ResList.xml':
                return blobs[self.revision]
            assert path == 'GameVersion/LogicVersion.h'
            return b'2981 \n'

        def file(self, path):
            assert path == 'Localization/Game/zh-CN/game.json'
            return {'story': {'line': '台词', 'next': '继续'}, '': {'line': '提示'}}

    monkeypatch.setattr(regional, 'DialogueCatalog', Catalog)
    monkeypatch.setattr(regional, 'publisher_identity', lambda: identities[0])
    monkeypatch.setattr(regional, 'download', lambda url, **kwargs: json.dumps(commits).encode())
    selected = regional.snapshot(tmp_path, namespace='story', keys=['line'])
    assert selected['texts'] == {'story': {'line': '台词'}} and selected['metadata_commit'] == older
    assert selected['logic_version'] == '2981' and selected['locale'] == 'zh-CN'
    identities[0] = 'PC_120', '1.2.4', hashlib.md5(second).hexdigest()
    assert regional.snapshot(tmp_path)['metadata_commit'] == newest
    assert regional.snapshot(tmp_path, namespace='')['texts'] == {'': {'line': '提示'}}
    with pytest.raises(ValueError, match='namespace'):
        regional.snapshot(tmp_path, keys=['line'])
    with pytest.raises(ValueError, match='Unknown key'):
        regional.snapshot(tmp_path, namespace='story', keys=['missing'])

    # A same-version export from another region must not pass on its build label.
    identities[0] = 'PC_120', '1.2.3', 'c' * 32
    with pytest.raises(ValueError, match='unique'):
        regional.snapshot(tmp_path)
    another = 'd' * 40
    commits.append({'sha': another, 'commit': {'message': '1.2.3 | 2981'}})
    blobs[another] = first
    identities[0] = 'PC_120', '1.2.3', hashlib.md5(first).hexdigest()
    with pytest.raises(ValueError, match='unique'):
        regional.snapshot(tmp_path)
    identities = iter([('PC_120', '1.2.4', hashlib.md5(second).hexdigest()),
                       ('PC_121', '1.2.5', 'e' * 32)])
    monkeypatch.setattr(regional, 'publisher_identity', lambda: next(identities))
    with pytest.raises(ValueError, match='changed during'):
        regional.snapshot(tmp_path)


def test_text_requires_valid_mainland_launcher_digest(monkeypatch):
    config = ElementTree.fromstring('<Config><Extra><listHash>bad</listHash></Extra></Config>')
    monkeypatch.setattr(regional, 'release_config', lambda region: ('PC_123', '1.2.3', '', config))
    with pytest.raises(ValueError, match='checksum'):
        regional.publisher_identity()
