import base64
import hashlib
import io
import json
import zipfile

import pytest

from scripts import live_game_sources as sources


def test_nte_follows_region_and_compares_resource_contents(monkeypatch, tmp_path):
    branch = base64.b64encode(b'{"branchName":"PC_200"}').decode()
    first = f'<config><ResConfig>{branch}</ResConfig></config>'.encode()
    active = b'<config><ResVersion>2.0.1</ResVersion><BaseVerson><Res Tag="pakchunk101" version="0.101.1" ResSize="10"/></BaseVerson></config>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('ResList.bin', b'resource list')
    def fetch(url, limit):
        assert url.startswith('https://ntecdn1.perfectworld.com/')
        if '/publish_PC/' in url:
            return first
        assert '/PC_200/' in url
        return buf.getvalue() if url.endswith('2.0.1/ResList.bin.zip') else active
    monkeypatch.setattr(sources, 'download', fetch)
    first_receipt = sources.collect('nte-global', tmp_path)
    assert first_receipt['files']['ResList.bin'] == [13, hashlib.sha256(b'resource list').hexdigest()]
    assert first_receipt['files']['pakchunk101'] == [10, '0.101.1']
    active = active.replace(b'0.101.1', b'0.101.2')
    change = sources.differences(first_receipt, sources.collect('nte-global', tmp_path))
    assert change == {'added': [], 'removed': [], 'changed': ['pakchunk101']}
    with pytest.raises(ValueError, match='regions'):
        sources.differences(first_receipt, dict(first_receipt, channel='nte-cn'))


def test_wuwa_keeps_game_paks_and_requires_current_launcher_checksum(monkeypatch):
    path = 'launcher/game/G153/50004/1.0.1/example/resource/50004/1.0.1/indexFile.json'
    row = {'dest': 'Client/Content/Paks/voice.pak', 'md5': '1' * 32, 'size': 123}
    data = json.dumps({'resource': [row, dict(row, dest='Browser/example.pak')]}).encode()
    cfg = {'config': {'version': '1.0.1', 'indexFile': path, 'indexFileMd5': hashlib.md5(data).hexdigest()},
           'cdnList': [{'url': 'https://cdn.aki-game.net/'}]}
    def fetch(url):
        if url == sources.KURO:
            return json.dumps({'default': cfg}).encode()
        assert url == 'https://cdn.aki-game.net/' + path
        return data
    monkeypatch.setattr(sources, 'kuro_bytes', fetch)
    assert sources.wuwa()[2] == {row['dest']: [123, '1' * 32]}
    cfg['config']['indexFileMd5'] = '0' * 32
    with pytest.raises(ValueError, match='checksum'):
        sources.wuwa()
