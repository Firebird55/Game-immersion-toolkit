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
    body = b'<ResList version="2.0.1" tag="baseTag"><BaseVersion tag="pakchunk101" version="0.101.1"><ResList><Package><Pak filesize="80" md5="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"><Entry name="Client/dub.pak" offset="3" size="10" md5="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"/></Pak></Package></ResList></BaseVersion></ResList>'
    def launcher():
        return (f'<config><ResVersion>2.0.1</ResVersion><Extra><listHash>{hashlib.md5(body).hexdigest()}</listHash></Extra>'
                '<BaseVerson><Res Tag="pakchunk101" version="0.101.1" ResSize="10"/></BaseVerson></config>').encode()
    def fetch(url, limit):
        assert url.startswith('https://ntecdn1.perfectworld.com/')
        if '/publish_PC/' in url:
            return first
        assert '/PC_200/' in url
        if url.endswith('2.0.1/ResList.bin.zip'):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as archive:
                archive.writestr('ResList.bin', body)
            return buf.getvalue()
        return launcher()
    monkeypatch.setattr(sources.nte_release, 'download', fetch)
    first_receipt = sources.collect('nte-global', tmp_path)
    assert first_receipt['files'] == {'Client/dub.pak': [10, 'b' * 32]}
    legacy = dict(first_receipt, files=first_receipt['previous_files'], scope=first_receipt['previous_scope'])
    assert sources.differences(legacy, first_receipt)['changed'] == []
    body = body.replace(b'b' * 32, b'c' * 32)
    change = sources.differences(first_receipt, sources.collect('nte-global', tmp_path))
    assert change == {'added': [], 'removed': [], 'changed': ['Client/dub.pak']}
    body = body.replace(b'offset="3"', b'offset="73"')
    with pytest.raises(ValueError, match='range'):
        sources.collect('nte-global', tmp_path)
    with pytest.raises(ValueError, match='regions'):
        sources.differences(first_receipt, dict(first_receipt, channel='nte-cn'))


def test_wuwa_keeps_game_paks_and_requires_current_launcher_checksum(monkeypatch):
    path = 'launcher/game/G153/50004/1.0.1/example/resource/50004/1.0.1/indexFile.json'
    row = {'dest': 'Client/Content/Paks/voice.pak', 'md5': '1' * 32, 'size': 123}
    data = json.dumps({'resource': [row, dict(row, dest='Browser/example.pak')]}).encode()
    cfg = {'config': {'version': '1.0.1', 'indexFile': path, 'indexFileMd5': hashlib.md5(data).hexdigest()},
           'resourcesBasePath': path.split('/resource/')[0] + '/zip',
           'cdnList': [{'url': 'https://cdn.aki-game.net/'}]}
    def fetch(url):
        if url == sources.KURO:
            return json.dumps({'default': cfg}).encode()
        assert url == 'https://cdn.aki-game.net/' + path
        return data
    monkeypatch.setattr(sources, 'kuro_bytes', fetch)
    assert sources.wuwa_launcher()[2] == {row['dest']: [123, '1' * 32]}
    cfg['config']['indexFileMd5'] = '0' * 32
    with pytest.raises(ValueError, match='checksum'):
        sources.wuwa_launcher()
