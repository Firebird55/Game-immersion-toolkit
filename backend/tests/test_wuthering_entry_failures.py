"""ENTRY failure identity, worker retention and offline original restoration."""
import base64
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from backend import wuthering_release as release, wuthering_metadata as metadata
from backend.preparation_errors import PreparationFailure, public_failure
from backend.tests.test_wuthering_metadata import protected


KEY, IV = b'a'*16, b'b'*16


def source(key=KEY, iv=IV):
    return b'const ENTRY_KEY: &str = "'+base64.b64encode(key)+b'"; const ENTRY_IV: &str = "'+base64.b64encode(iv)+b'";'


def encrypted(key=KEY):
    return base64.b64encode(AES.new(key,AES.MODE_CBC,IV).encrypt(pad(b'{"default":{"fixture":true}}',16)))


@pytest.fixture(autouse=True)
def isolate_format_cache():
    original=release._format
    original.cache_clear()
    yield
    original.cache_clear()


def pinned(monkeypatch, raw=None):
    raw=source() if raw is None else raw
    monkeypatch.setattr(release,'FORMAT_SHA',hashlib.sha256(raw).hexdigest())
    return raw


def assert_public(error, code):
    value=public_failure(error)
    assert value['code']==code and value['previous_snapshot_retained']
    assert not value['game_files_changed']
    assert 'private-sensitive' not in value['message'] and 'package format changed' not in value['message'].lower()
    return value


def test_missing_entry_source_is_a_typed_source_failure(tmp_path,monkeypatch):
    pinned(monkeypatch)
    def unavailable(*args,**kwargs):raise OSError('private-sensitive source path/key diagnostic')
    monkeypatch.setattr(release,'download',unavailable)
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(),tmp_path)
    assert_public(failure.value,'publisher_entry_source_unavailable')
    assert not metadata._path(tmp_path,'catalog-format').exists()


def test_unbounded_or_invalid_source_response_stays_a_typed_entry_error(tmp_path,monkeypatch):
    pinned(monkeypatch)
    def invalid(*args,**kwargs):raise ValueError('private-sensitive oversized response or redirect')
    monkeypatch.setattr(release,'download',invalid)
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(),tmp_path)
    assert_public(failure.value,'publisher_entry_source_invalid')
    assert not metadata._path(tmp_path,'catalog-format').exists()


@pytest.mark.parametrize('kind',['corrupt','empty','generation'])
def test_present_invalid_or_other_generation_cache_never_becomes_a_cold_fallback(tmp_path,monkeypatch,protected,kind):
    pinned(monkeypatch);path=metadata._path(tmp_path,'catalog-format');path.parent.mkdir(parents=True)
    if kind=='corrupt':path.write_bytes(b'private-sensitive corrupt envelope')
    else:assert metadata._write(path,b'' if kind=='empty' else source(b'c'*16))
    before=path.read_bytes()
    monkeypatch.setattr(release,'download',lambda *a,**k:pytest.fail('No fallback after a present invalid format cache'))
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(),tmp_path)
    assert_public(failure.value,'publisher_entry_cache_generation_mismatch' if kind=='generation' else 'publisher_entry_cache_invalid')
    assert path.read_bytes()==before


def test_source_checksum_failure_is_distinct_from_cache_or_key_mismatch(tmp_path,monkeypatch):
    raw=pinned(monkeypatch)
    monkeypatch.setattr(release,'download',lambda *a,**k:raw+b'private-sensitive changed wire')
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(),tmp_path)
    assert_public(failure.value,'publisher_entry_source_auth_failed')
    assert not metadata._path(tmp_path,'catalog-format').exists()


@pytest.mark.parametrize('raw',[b'no ENTRY declarations',source()+source(),source(b'short'),b'const ENTRY_KEY: &str = "!"; const ENTRY_IV: &str = "!";'])
def test_verified_but_unsupported_input_is_not_a_package_format_claim(tmp_path,monkeypatch,raw):
    pinned(monkeypatch,raw);monkeypatch.setattr(release,'download',lambda *a,**k:raw)
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(),tmp_path)
    assert_public(failure.value,'publisher_entry_source_invalid')
    assert not metadata._path(tmp_path,'catalog-format').exists()


def test_failed_retention_refuses_new_preparation_without_erasing_prior_data(tmp_path,monkeypatch):
    raw=pinned(monkeypatch);monkeypatch.setattr(release,'download',lambda *a,**k:raw)
    monkeypatch.setattr(metadata,'remember_format',lambda *a:False)
    prior=tmp_path/'old-index-and-audio';prior.write_bytes(b'complete old prepared source')
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(),tmp_path)
    assert_public(failure.value,'publisher_entry_cache_failed')
    assert prior.read_bytes()==b'complete old prepared source'


def test_current_wrapper_key_mismatch_preserves_verified_input_without_refetch(tmp_path,monkeypatch,protected):
    raw=pinned(monkeypatch);assert metadata.remember_format(tmp_path,raw,release.FORMAT_SHA)
    path=metadata._path(tmp_path,'catalog-format');before=path.read_bytes()
    monkeypatch.setattr(release,'download',lambda *a,**k:pytest.fail('No new key guess or refetch after a current wrapper mismatch'))
    with pytest.raises(PreparationFailure) as failure:release._json(encrypted(b'c'*16),tmp_path)
    assert_public(failure.value,'publisher_format_key_unresolved')
    assert path.read_bytes()==before


@pytest.mark.parametrize('raw',[b'not base64!',b'',base64.b64encode(b'wrong length'),b'{invalid',bytes((255,))])
def test_invalid_wrapper_framing_does_not_request_an_entry_input(monkeypatch,raw):
    monkeypatch.setattr(release,'_format',lambda *a:pytest.fail('Do not fetch keys for invalid wire framing'))
    with pytest.raises(PreparationFailure) as failure:release._json(raw)
    assert_public(failure.value,'publisher_metadata_invalid')


def test_valid_plain_metadata_does_not_require_entry(monkeypatch):
    monkeypatch.setattr(release,'_format',lambda *a:pytest.fail('Plain metadata needs no ENTRY input'))
    assert release._json(b'{"resource": []}')=={'resource':[]}


@pytest.mark.parametrize(('stage','kind','code'),[
    ('fingerprint','missing','publisher_entry_source_unavailable'),
    ('worker','missing','publisher_entry_source_unavailable'),
    ('worker','current-key','publisher_format_key_unresolved'),
    ('fingerprint','cache-corrupt','publisher_entry_cache_invalid'),
    ('fingerprint','cache-generation','publisher_entry_cache_generation_mismatch'),
    ('worker','source-auth','publisher_entry_source_auth_failed'),
])
def test_real_preparation_service_and_worker_keep_old_source_audio_and_offline_restart(
        tmp_path,monkeypatch,protected,stage,kind,code):
    from backend import api,game_assets,language_worker,media_tools,publisher_regions
    from backend.language_preparation import LanguagePreparation
    from backend.multilingual_index import MultilingualTextIndex
    from backend.tests.test_prepared_setup_state import runtime
    raw=pinned(monkeypatch)
    tools=tmp_path/'wuwa/tools';snapshot={'schema':1,'region':'global','base':{},'products':{},'versions':{'resource':'1.0.0','en':'1.0.0'}}
    descriptor=json.dumps(snapshot,sort_keys=True).encode();stamp='wuwa-'+hashlib.sha256(descriptor).hexdigest();depot='Client/Content/Aki/WwiseAudio_Generated/WwiseExternalSource/en_fixture_original.wem'
    original=b'RIFF'+(4).to_bytes(4,'little')+b'WAVE';source_dir=tools/'wuwa-publisher'/stamp;source_dir.mkdir(parents=True);(source_dir/'release.json').write_bytes(descriptor)
    binding=hashlib.sha256((stamp+'/'+depot).encode()).digest();clips=source_dir/'clips';clips.mkdir();clip=clips/hashlib.sha256(depot.encode()).hexdigest();clip.write_bytes(hashlib.sha256(binding+original).digest()+original)
    text='Retained official fixture line remains available.';audio={'publisher':stamp,'depot':depot,'locale':'en'}
    output=tmp_path/'languages/wuwa/en/textmap.json';output.parent.mkdir(parents=True)
    language_worker.write_payload('wuwa',{'format':2,'game':'wuwa','install':None,'source_locale':'en','fingerprint':stamp,'records':[{'text_id':'wuwa:retained-fixture','source_locale':'en','source_text':text,'english':text,'chinese':'保留的测试字幕。','texts':{'en':text,'zh-Hans':'保留的测试字幕。'},'audio_locale':'en','audio':audio}]},'en',['zh-Hans'],output)
    before={p:p.read_bytes() for p in (output,clip,source_dir/'release.json')}
    monkeypatch.setattr(api,'DATA_DIR',tmp_path);value=runtime(tmp_path,account='owner',locale=None);value.setup_install=lambda _:None
    monkeypatch.setattr(media_tools,'vgmstream_executable',lambda *_:None);monkeypatch.setattr(publisher_regions,'selected_region',lambda *a:'global')
    wire=encrypted(b'c'*16 if kind=='current-key' else KEY)
    if kind=='current-key':assert metadata.remember_format(tools,raw,release.FORMAT_SHA)
    if kind=='cache-corrupt':
        path=metadata._path(tools,'catalog-format');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'private-sensitive invalid cache')
    if kind=='cache-generation':assert metadata._write(metadata._path(tools,'catalog-format'),source(b'd'*16))
    def unavailable(*a,**k):
        if kind=='source-auth':return raw+b'private-sensitive changed source'
        raise OSError('private-sensitive ENTRY path/key diagnostic')
    monkeypatch.setattr(release,'download',unavailable)
    monkeypatch.setattr(release,'_current',lambda tools,*a,**k:release._json(wire,tools))
    worker_calls=[]
    if stage=='worker':
        monkeypatch.setattr(game_assets,'preparation_fingerprint',lambda *a:'new-fixture-release')
        monkeypatch.setattr(api,'child_command',lambda kind,args:['fixture-python',*args])
        def run(command,**kwargs):
            worker_calls.append(True);candidate=Path(command[command.index('--output')+1])
            try:language_worker.build('wuwa',None,tmp_path/'wuwa','en',('zh-Hans',),candidate)
            except PreparationFailure as error:
                candidate.with_name('failure.json').write_text(json.dumps(public_failure(error)),encoding='utf8')
                candidate.with_name('failure.log').write_text('private-sensitive worker diagnostic',encoding='utf8')
                return SimpleNamespace(returncode=1)
            raise AssertionError('Missing ENTRY must not publish a candidate')
        monkeypatch.setattr(api.subprocess,'run',run)
    manager=LanguagePreparation(lambda game,locale,targets:value.build_language(game,locale,targets,force=True),lambda *_:pytest.fail('Failed update cannot activate'),lambda *_:{'ready':True},path=tmp_path/'languages.json',supported=lambda _:('en',))
    manager.data['prepared']={'wuwa':{'en':{'targets':['zh-Hans']}}};manager.data['selected']={'owner':{'wuwa':'en'}};manager._save();value.languages=manager
    assert value.language_state('wuwa','en')['ready']
    assert manager.request('wuwa','en','fr','owner',rebuild=True)
    deadline=time.monotonic()+5
    while manager._workers and time.monotonic()<deadline:time.sleep(.005)
    assert not manager._workers
    job=manager.status('wuwa','owner')['locales'][0]['job'];assert job['state']=='error' and job['code']==code and job['previous_snapshot_retained']
    assert 'ENTRY' in job['message'] and 'private-sensitive' not in job['message'] and str(tmp_path) not in job['message']
    assert 'format changed' not in job['message'].lower()
    assert bool(worker_calls)==(stage=='worker')
    assert manager.selected('wuwa','owner')=='en' and manager.prepared('wuwa','en')['targets']==['zh-Hans']
    assert all(p.read_bytes()==data for p,data in before.items())
    # A fresh reader and original-source restore need neither the ENTRY input
    # nor a current bootstrap/network/protected-cache query.
    monkeypatch.setattr(release,'_format',lambda *a:pytest.fail('Offline old source cannot need ENTRY'))
    monkeypatch.setattr(release,'_parameters_for_snapshot',lambda *a:pytest.fail('Offline cache cannot need current keys'))
    restarted=LanguagePreparation(None,None,None,path=manager.path,supported=lambda _:('en',));assert restarted.selected('wuwa','owner')=='en'
    index=MultilingualTextIndex('wuwa',output.parent);hit=index.match_lines([text]);assert index.ready and hit and hit.text_id=='wuwa:retained-fixture'
    assert release.extract(tools,audio,'en')==original
    assert all(p.read_bytes()==data for p,data in before.items())
