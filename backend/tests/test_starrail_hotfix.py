"""Checks for resource-only updates, old snapshot playback and regional compatibility."""
import hashlib
import io
import json
import struct
from types import SimpleNamespace

import pytest

from backend import starrail_hotfix as hotfix, hoyo_publisher_voice as voices


def pointers(design=10):
    return {field: f'{folder}/V4.7Live/output_{design if name == "design" else 8}_abcd_ef01'
            for name, (field, folder) in hotfix.ROUTES.items()}


def marker(rev, body):
    data = bytearray(66)
    data[:8] = b'SRMI\0\3\0\1'
    struct.pack_into('<I', data, 8, 66)
    digest = hashlib.md5(body).hexdigest()
    struct.pack_into('<5IQ', data, 24, rev, *(int(digest[i:i+8], 16) for i in range(0, 32, 8)), len(body))
    return bytes(data)


def test_discovery_rechecks_regional_markers_and_indexes_on_text_only_updates(tmp_path, monkeypatch):
    routes = {'OS4.7.0': pointers(), 'CN4.7.0': pointers()}
    region_mismatch = False
    def get(url, *, limit):
        if url == hotfix.ROUTE_INDEX:
            return json.dumps({'HotfixData': routes}).encode()
        revision = int(url.split('output_')[1].split('_')[0])
        data = str(revision).encode()
        if region_mismatch and 'autopatchcn.' in url and '/design_data/' in url:
            data += b'changed text'
        return marker(revision, data) if '/M_' in url else data
    monkeypatch.setattr(hotfix, 'download', get)
    cn = {'channel': 'starrail-cn', 'version': '4.7.0', 'build': 'unchanged', 'manifests': {}}
    old = hotfix.discover(cn)
    assert hotfix.index(tmp_path, old, 'design') == b'10'
    routes.update({'CN4.7.0': pointers(11), 'OS4.7.0': pointers(11)})
    new = hotfix.discover(cn)
    assert voices.descriptor(old)[0] != voices.descriptor(new)[0]
    assert new['hotfix']['indexes']['audio'] == old['hotfix']['indexes']['audio']
    assert hotfix.index(tmp_path, new, 'design') == b'11'
    assert hotfix.index(tmp_path, old, 'design') == b'10'
    region_mismatch = True
    with pytest.raises(ValueError):
        hotfix.discover(cn)
    routes['OS4.7.0']['LuaUrl'] = 'https://other.host/resource'
    with pytest.raises(ValueError):
        hotfix.discover(cn | {'channel': 'starrail-global'})


def test_real_audio_index_replaces_only_matching_sophon_assets_and_caches_verified_ranges(tmp_path, monkeypatch):
    old = b'old'
    new = b'new original audio'
    hashed = lambda x: hashlib.md5(x).hexdigest()
    prefix = 'StarRail_Data/StreamingAssets/Audio/AudioPackage/Windows/'
    rows = [{'Path': 'Japanese/line.pck', 'Size': len(new), 'Md5': hashed(new), 'Patch': False},
            {'Path': 'Japanese/previous.pck', 'Size': len(old), 'Md5': hashed(old), 'Patch': False},
            {'Path': 'Korean/other.pck', 'Size': len(old), 'Md5': hashed(old), 'Patch': False}]
    monkeypatch.setattr(hotfix,'index',lambda *args: b'\n'.join(json.dumps(x).encode() for x in rows))
    unchanged = SimpleNamespace(size=len(old),digest=hashed(old))
    regular = {prefix+'Japanese/'+name: unchanged for name in ('line.pck','previous.pck','removed.pck')}
    build={'channel':'starrail-global','version':'4.7.0','hotfix':{'routes':{k:pointers()[v[0]] for k,v in hotfix.ROUTES.items()}}}
    selected=hotfix.files(tmp_path,build,'ja',regular)
    assert len(selected)==2 and selected[prefix+'Japanese/previous.pck'] is unchanged
    asset=next(a for a in selected.values() if a is not unchanged)
    class Response(io.BytesIO):
        status=206
        headers={'Content-Range':f'bytes 4-11/{len(new)}','ETag':'"'+hashed(new).upper()+'"'}
        def geturl(self): return asset.url
    def response(request, timeout):
        assert request.get_header('Range')=='bytes=4-11'
        return Response(new[4:12])
    monkeypatch.setattr(hotfix,'urlopen',response)
    assert asset.read(tmp_path,4,8)==new[4:12]
    monkeypatch.setattr(hotfix,'urlopen',lambda *a,**kwargs: pytest.fail('offline replay'))
    assert asset.read(tmp_path,4,8)==new[4:12]
    Response.headers['ETag']='"'+hashed(old)+'"'
    monkeypatch.setattr(hotfix,'urlopen',response)
    with pytest.raises(ValueError):
        asset.read(tmp_path/'empty',4,8)
    rows.append(rows[0])
    with pytest.raises(ValueError):
        hotfix.files(tmp_path,build,'ja',regular)

def test_rate_limited_catalog_uses_authors_mirror_at_the_exact_release_commit(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    from backend import starrail_publisher as publisher
    sha = 'a' * 40
    def limited(*args, **kwargs):
        raise HTTPError('https://gitlab.com/', 429, 'rate limited', None, None)
    monkeypatch.setattr(publisher, 'matching_release_commit', limited)
    records = [{'sha': 'b' * 40, 'commit': {'message': 'another generation'}},
               {'sha': sha, 'commit': {'message': 'expected generation'}}]
    monkeypatch.setattr(publisher, 'download', lambda *a, **k: json.dumps(records).encode())
    assert publisher._text_commit('expected generation') == sha
    with pytest.raises(ValueError, match='matching'):
        publisher._text_commit('absent generation')
    catalog = publisher.ReleasedCatalog('starrail', tmp_path, revision=sha)
    def file_bytes(relative, url):
        if url.startswith('https://gitlab.com/'):
            limited()
        assert url == f'https://raw.githubusercontent.com/DimbreathBot/TurnBasedGameData/{sha}/{relative}'
        return b'{}'
    monkeypatch.setattr(catalog, '_bytes', file_bytes)
    assert catalog.file('ExcelOutput/Example.json') == {}
