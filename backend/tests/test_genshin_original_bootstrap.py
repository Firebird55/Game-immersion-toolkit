"""Whole authored profile, map and all-candidate controls; no real game data."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from backend import genshin_original_bootstrap as bootstrap
from backend.tests.test_genshin_original_containers import bundle


def contract(identity=0x12345678):
    return {'schema':'genshin-original-channel-loader-v1','source_basename':'authored.blk',
        'source_field':{'executable_sha256':hashlib.sha256(b'authored executable').hexdigest()},
        'config_fields':['ChannelName','DispatchConfigs'],'dispatch_fields':['DispatchName','DispatchUrls'],
        'object_candidates':[{'id':identity}],'profile_only':True,'complete_dispatch_bootstrap':False,'later_override_excluded':False}


def profile():
    return {'ChannelName':'AUTHORED','DispatchConfigs':[{'DispatchName':'A',
        'DispatchUrls':['https://authored.yuanshen.com/query_region_list']}],
        'RSAParam':{'keyId':7},'FutureField':{'retained':['original','data']}}


def encoded_body(raw):
    header=bytearray(72)
    struct.pack_into('<I',header,4,len(raw));header[21]=22
    struct.pack_into('<ii',header,24,1,1)
    struct.pack_into('<q',header,32,24);struct.pack_into('<I',header,56,len(raw))
    struct.pack_into('<q',header,40,24);struct.pack_into('<ii',header,64,0,len(raw))
    return b'Blb\x03'+struct.pack('<I',len(header))+bytes(20)+header+raw


def test_strict_profile_preserves_future_fields_and_multiple_unselected_profiles():
    value=profile();value['DispatchConfigs'].append({'DispatchName':'B','DispatchUrls':['https://another.yuanshen.com/query_region_list']})
    payload=json.dumps(value,ensure_ascii=False).encode()
    assert bootstrap.parse_profile(payload,contract())==value
    actual,original,proof=bootstrap.profile_body(bundle(payload=payload),contract())
    assert actual==value and original==payload
    assert proof['complete_named_object_map'] is proof['strict_payload_eof'] is True


@pytest.mark.parametrize('change',['duplicate','trailing','nan','foreign-host','http','credentials','query','fragment','duplicate-profile','duplicate-url','bool-key','wrong-shape','missing-native-role'])
def test_bad_profile_is_never_a_descriptor_or_a_partially_valid_profile(change):
    value=profile();recipe=contract()
    if change in ('foreign-host','http','credentials','query','fragment'):
        value['DispatchConfigs'][0]['DispatchUrls']=[{
            'foreign-host':'https://example.com/query_region_list','http':'http://authored.yuanshen.com/query_region_list',
            'credentials':'https://user:password@authored.yuanshen.com/query_region_list',
            'query':'https://authored.yuanshen.com/query_region_list?account_type=1',
            'fragment':'https://authored.yuanshen.com/query_region_list#ignored'}[change]]
    elif change=='duplicate-profile':value['DispatchConfigs']*=2
    elif change=='duplicate-url':value['DispatchConfigs'][0]['DispatchUrls']*=2
    elif change=='bool-key':value['RSAParam']['keyId']=True
    elif change=='wrong-shape':value['DispatchConfigs']={}
    elif change=='missing-native-role':recipe['config_fields']=[]
    payload=json.dumps(value).encode()
    if change=='duplicate':payload=payload.replace(b'"ChannelName": "AUTHORED"',b'"ChannelName":"A","ChannelName":"B"')
    elif change=='trailing':payload+=b'{}'
    elif change=='nan':payload=payload[:-1]+b',"bad":NaN}'
    with pytest.raises((ValueError,TypeError)):bootstrap.profile_body(bundle(payload=payload),recipe)


@pytest.mark.parametrize('change',['unselected-bad-ref','duplicate-map-name','missing-owned-id','two-owned-ids','wrong-object-kind','truncated'])
def test_complete_map_and_native_id_ambiguity_cannot_be_hidden_by_one_valid_object(change):
    payload=json.dumps(profile()).encode();recipe=contract();options={}
    if change=='unselected-bad-ref':options['entries']=[('12345678',1),('deadbeef',99)]
    elif change=='duplicate-map-name':options['entries']=[('12345678',1),('12345678',1)]
    elif change=='missing-owned-id':recipe=contract(0x87654321)
    elif change=='two-owned-ids':
        options['entries']=[('12345678',1),('87654321',1)];recipe['object_candidates'].append({'id':0x87654321})
    elif change=='wrong-object-kind':options['kind']=49
    raw=bundle(payload=payload,**options)
    if change=='truncated':raw=raw[:-1]
    with pytest.raises(ValueError):bootstrap.profile_body(raw,recipe)


def preparation_fixture(tmp_path,monkeypatch,*,ambiguous=False,bad_method=False):
    from backend import genshin_blb_native,genshin_native_x64
    executable=b'authored executable';source=tmp_path/'original';source.write_bytes(b'whole publisher container')
    source_receipt={'name':'Assets/authored.blk','bytes':source.stat().st_size,
        'md5':hashlib.md5(source.read_bytes()).hexdigest(),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    raw=bundle(payload=json.dumps(profile()).encode());calls=[]
    candidates=[genshin_blb_native.Candidate(b'wrong',('a'*64,)),
        genshin_blb_native.Candidate(b'good',() if bad_method else ('b'*64,)),
        genshin_blb_native.Candidate(b'also-good' if ambiguous else b'wrong-later',('c'*64,))]
    monkeypatch.setattr(genshin_native_x64,'Image',lambda data:SimpleNamespace(data=data))
    def discover(image):
        assert image.data==executable
        return candidates
    monkeypatch.setattr(genshin_blb_native,'discover_candidates',discover)
    class Helper:
        identity='authored-helper'
        def decode(self,original,parameters,destination,*,work):
            assert original==source and Path(work).parent==tmp_path
            current=parameters.read_bytes();calls.append(current)
            if current not in (b'good',b'also-good'):raise ValueError('Authored incompatible contract')
            destination.write_bytes(encoded_body(raw))
    return executable,source,source_receipt,contract(),Helper(),calls


def test_all_original_contracts_are_tested_before_unique_profile_only_acceptance(tmp_path,monkeypatch):
    arguments=preparation_fixture(tmp_path,monkeypatch)
    result=bootstrap.prepare_profile(*arguments[:5],directory=tmp_path)
    assert arguments[5]==[b'wrong',b'good',b'wrong-later']
    assert json.loads(result.payload)==profile() and result.parameters==b'good'
    assert result.proof['profile_only'] is True and result.proof['original_codec_candidates_tested']==3
    assert all(result.proof[key] is False for key in ('complete_dispatch_bootstrap','full_catalog_validated',
        'selected_shards_validated','later_override_excluded','response_signature_verified','community_numeric_data_used'))
    assert 'https://' not in repr(result) and not list(tmp_path.glob('channel-codec-*'))


@pytest.mark.parametrize('change',['ambiguous-contracts','missing-method-receipt','stale-native','wrong-source-digest','cancel'])
def test_no_profile_result_from_ambiguity_stale_owners_missing_recipe_or_cancellation(tmp_path,monkeypatch,change):
    executable,source,receipt,recipe,helper,calls=preparation_fixture(tmp_path,monkeypatch,
        ambiguous=change=='ambiguous-contracts',bad_method=change=='missing-method-receipt')
    if change=='stale-native':executable+=b'new generation'
    elif change=='wrong-source-digest':receipt['md5']='0'*32
    def cancel():
        if change=='cancel' and calls:raise InterruptedError('Authored cancellation')
    with pytest.raises((ValueError,InterruptedError)):
        bootstrap.prepare_profile(executable,source,receipt,recipe,helper,directory=tmp_path,check_cancel=cancel)
    assert not list(tmp_path.glob('channel-codec-*'))
    if change in ('stale-native','wrong-source-digest'):assert not calls
