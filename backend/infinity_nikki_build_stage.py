"""Current Global SDK/build metadata and consent-bound whole BuildPatch sources."""
import base64
import hashlib
import json
from pathlib import Path
import re

from .game_data_protocol import GameDataError, GameDataPlan, PreparationStage
from .private_data_paths import _no_links
from .publisher_transport import STRONG_ETAG
from . import infinity_nikki_release as release
from . import infinity_nikki_bootstrap as bootstrap
from . import infinity_nikki_inventory as inventory
from . import infinity_nikki_chunks as chunks
from . import infinity_nikki_native as native
from . import infinity_nikki_sdk_stage as sdk

POLICY='infinitynikki-global-build-sources/1'
STAGES={'global-build-manifests','global-build-source'}
GATE=('The current official package manifests are verified. Selected configuration packages, '
      'ordered settings and dynamic-keychain/text/voice readers still require preparation. '
      'No language library has been activated.')
QUOTE=('Download the current official package metadata. Whole original manifests and their '
       'generation checks are included; no game voice package is selected. Text, voice and '
       'settings packages require a subsequent size plan.')


def _foundation():
    from . import infinitynikki_game_data
    return infinitynikki_game_data


def _check(value):
    if not value:
        raise GameDataError('publisher_source_unverified','Could not verify the current official Global package metadata.')


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def _sha(raw):return hashlib.sha256(raw).hexdigest()


def _path(ctx,digest,suffix='json'):
    _check(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and suffix in {'json','manifest'})
    path=Path(ctx.cache_directory).absolute()/'infinitynikki-global-build'/(digest+'.'+suffix)
    _no_links(path)
    return path


def _store(ctx,value):
    raw=_json(value);_check(len(raw)<=sdk.MAX_ARTIFACT)
    digest=_sha(raw);ctx.check();_foundation()._save(_path(ctx,digest),raw)
    return digest


def _read(ctx,digest):
    path=_path(ctx,digest)
    _check(path.is_file() and 0<path.stat().st_size<=sdk.MAX_ARTIFACT)
    raw=path.read_bytes();_check(_sha(raw)==digest)
    return json.loads(raw,object_pairs_hook=release._unique_object)


def _source_bytes(value,maximum):
    _check(isinstance(value,str) and len(value)<=4*((maximum+2)//3))
    raw=base64.b64decode(value,validate=True)
    _check(0<len(raw)<=maximum)
    return raw


def _receipt(transfer,url,raw):
    _check(isinstance(transfer,dict) and transfer.get('source_url_sha256')==_sha(url.encode()) and
           transfer.get('bytes')==len(raw) and transfer.get('sha256')==_sha(raw) and
           transfer.get('original_range') is None)


def _configuration(provider,handle,ctx):
    _foundation()._handle(handle,ctx.request)
    _check(handle['stage']=='global-sdk-source')
    receipt,_,path=sdk._retained(handle,ctx)
    if not sdk._runtime(provider.platform):
        raise GameDataError('game_runtime_unavailable',sdk.SIGNATURE_GATE,409)
    crypto=_foundation()._crypto(provider.platform,provider.native)
    identity,encoded=bootstrap.launcher_data_resources(path.read_bytes(),crypto=crypto)
    config=release.decode_launcher_config(encoded,identity,crypto=crypto)
    release._production_app(config)
    return receipt,identity,config,crypto


def _pointer(packet):
    _check(isinstance(packet,dict) and isinstance(packet.get('game_config_patch'),dict))
    patch=packet['game_config_patch']
    _check(all(type(patch.get(field)) is int and 0<=patch[field]<2**31 for field in ('region','channel','role')) and
           isinstance(patch.get('extra'),dict) and isinstance(patch['extra'].get('cdn_url'),str))
    return inventory.build_version_urls(patch['extra']['cdn_url'])


def _decode_build(raw,sdk_handle,crypto,ctx):
    # BuildVersion is an original JSON document in the current Global response.
    # Other original metadata uses _XYLUAP_; neither name nor directory implies
    # that every document has that wrapper. Both paths remain source-bound.
    _check(isinstance(raw,bytes) and 0<len(raw)<=native.MAX_WRAPPED)
    if raw.lstrip().startswith(b'{'):
        try:
            value=json.loads(raw.decode('utf-8'),object_pairs_hook=release._unique_object,
                parse_constant=lambda _: _check(False))
            _check(isinstance(value,dict))
            return value
        except (UnicodeError,ValueError,RecursionError) as error:
            raise GameDataError('publisher_source_unverified',
                'Could not verify the current official Global build document.') from error
    sdk_receipt,_,_=sdk._retained(sdk_handle,ctx)
    native_receipt=_foundation()._retained(sdk_receipt['native_handle'],ctx)
    path=_foundation()._path(ctx,native_receipt['module_sha256']+'.so')
    try:
        material=native.extract_wrapper_material(path.read_bytes(),expected_native_sha256=native_receipt['module_sha256'])
        return native.decode_wrapped_metadata(raw,material,crypto=crypto)
    except ValueError as error:
        raise GameDataError('publisher_wrapper_owner_unresolved',
            'The current official metadata wrapper parameter still needs verification. Existing data is retained.',409) from error


def _selection(provider,artifact,ctx):
    _check(isinstance(artifact,dict) and set(artifact)=={'policy','request','sdk_handle','timestamp',
        'request_sha256','sdk_response','sdk_transfer','build_url','build_raw','build_transfer','pins'} and
        artifact['policy']==POLICY and artifact['request']==ctx.request.json())
    _,identity,config,crypto=_configuration(provider,artifact['sdk_handle'],ctx)
    stamp=artifact['timestamp']
    _check(isinstance(stamp,str) and re.fullmatch('[0-9]{1,19}',stamp) and str(int(stamp))==stamp)
    exchange=release.patchlist_request(config,identity,now=int(stamp),crypto=crypto)
    _check(artifact['request_sha256']==_sha(exchange.data))
    response=_source_bytes(artifact['sdk_response'],release.MAX_RESPONSE)
    _receipt(artifact['sdk_transfer'],exchange.url,response)
    packet=release.decode_patchlist_response(response,config,exchange,crypto=crypto)
    urls=_pointer(packet)
    _check(artifact['build_url'] in urls)
    wrapped=_source_bytes(artifact['build_raw'],native.MAX_WRAPPED)
    _receipt(artifact['build_transfer'],artifact['build_url'],wrapped)
    build=_decode_build(wrapped,artifact['sdk_handle'],crypto,ctx)
    targets=chunks.manifest_sources(artifact['build_url'],build)
    _check(isinstance(artifact['pins'],list) and len(artifact['pins'])==2)
    for pin,role,url in zip(artifact['pins'],('base','fastpatch'),targets):
        _check(isinstance(pin,dict) and set(pin)=={'role','url','total','etag','prefix'} and pin['role']==role and
               pin['url']==url and type(pin['total']) is int and 32<=pin['total']<=chunks.MAX_MANIFEST and
               isinstance(pin['etag'],str) and STRONG_ETAG.fullmatch(pin['etag']) and
               isinstance(pin['prefix'],str) and re.fullmatch('[0-9a-f]{64}',pin['prefix']))
    # SDK region/channel and build.Region are preserved separately. No profile
    # alias, patch-overlay order or CMS response identity is inferred here.
    return build,packet


def _quote(provider,artifact,handle,ctx):
    build,_=_selection(provider,artifact,ctx)
    wire=sum(pin['total']+32 for pin in artifact['pins'])
    revision='global-build-'+build['DefaultVersion']+'.'+build['FastPatchVersion']+'-'+_sha(_json(artifact['pins']))[:12]
    return GameDataPlan(revision,wire,wire+len(_json(artifact))+128*1024,handle,
        runtime_available=True,stage='global-build-manifests',message=QUOTE)


def _collect(provider,previous,ctx):
    _,identity,config,crypto=_configuration(provider,previous,ctx)
    exchange=release.patchlist_request(config,identity,crypto=crypto)
    transport=provider.transport_factory(ctx,hosts={'passport.infoldgames.com'})
    response,transfer=transport.fetch_bytes(exchange.url,limit=release.MAX_RESPONSE,kind='metadata',
        method='POST',body=exchange.data,
        headers={key:value for key,value in exchange.headers.items() if key.lower()!='accept-encoding'})
    packet=release.decode_patchlist_response(response,config,exchange,crypto=crypto)
    urls=_pointer(packet)
    transport=provider.transport_factory(ctx,hosts=set(inventory.RESOURCE_HOSTS))
    # The primary source is source-owned, not a guessed platform/path. A network
    # failure keeps the old state; no unproven mirror or edition is substituted.
    build_url=urls[0]
    wrapped,build_transfer=transport.fetch_bytes(build_url,limit=native.MAX_WRAPPED,kind='metadata')
    build=_decode_build(wrapped,previous,crypto,ctx)
    pins=[]
    for role,url in zip(('base','fastpatch'),chunks.manifest_sources(build_url,build)):
        prefix,info=transport.fetch_bytes(url,limit=32,expected_size=32,kind='metadata',original_range=(0,32,None))
        _check(info.original_range is not None and info.response_etag is not None and STRONG_ETAG.fullmatch(info.response_etag))
        total=info.original_range[2]
        _check(type(total) is int and 32<=total<=chunks.MAX_MANIFEST)
        pins.append({'role':role,'url':url,'total':total,'etag':info.response_etag,'prefix':prefix.hex()})
    return {'policy':POLICY,'request':ctx.request.json(),'sdk_handle':previous,'timestamp':exchange.timestamp,
        'request_sha256':_sha(exchange.data),'sdk_response':base64.b64encode(response).decode(),
        'sdk_transfer':transfer.json(),'build_url':build_url,'build_raw':base64.b64encode(wrapped).decode(),
        'build_transfer':build_transfer.json(),'pins':pins}


def _retained(provider,handle,ctx):
    value=_read(ctx,handle['receipt_sha256'])
    _check(isinstance(value,dict) and set(value)=={'policy','request','artifact_sha256','manifests'} and
           value['policy']==POLICY and value['request']==ctx.request.json() and
           isinstance(value['manifests'],list) and len(value['manifests'])==2)
    artifact=_read(ctx,value['artifact_sha256'])
    build,_=_selection(provider,artifact,ctx)
    manifests=[]
    for row,pin in zip(value['manifests'],artifact['pins']):
        _check(isinstance(row,dict) and set(row)=={'role','sha256','bytes','transfer'} and
               row['role']==pin['role'] and row['bytes']==pin['total'])
        path=_path(ctx,row['sha256'],'manifest')
        _check(path.is_file() and path.stat().st_size==pin['total'])
        raw=path.read_bytes();_check(_sha(raw)==row['sha256'] and raw[:32].hex()==pin['prefix'])
        _receipt(row['transfer'],pin['url'],raw)
        _check(row['transfer'].get('response_etag')==pin['etag'])
        manifests.append(chunks.parse_manifest(raw,expected_sha256=row['sha256'],
            manifest_url=pin['url'],expected_version=build['DefaultVersion']))
    return value,artifact,tuple(manifests)


def plan(provider,previous,ctx):
    ctx.check()
    if previous['stage']=='global-build-source':
        value,_,_=_retained(provider,previous,ctx)
        return GameDataPlan('global-configuration-reader',0,0,previous,stage='global-build-source',message=GATE)
    if previous['stage']=='global-build-manifests':
        prior=_read(ctx,previous['receipt_sha256']);_selection(provider,prior,ctx)
        previous=prior['sdk_handle']
    _check(previous['stage']=='global-sdk-source')
    if not sdk._runtime(provider.platform):
        sdk._retained(previous,ctx)
        return GameDataPlan('global-sdk-verification',0,0,previous,stage='global-sdk-source',message=sdk.SIGNATURE_GATE)
    artifact=_collect(provider,previous,ctx)
    digest=_store(ctx,artifact)
    handle={'policy':_foundation().POLICY,'request':ctx.request.json(),
            'stage':'global-build-manifests','receipt_sha256':digest}
    return _quote(provider,artifact,handle,ctx)


def download(provider,consent,ctx):
    if consent.handle['stage']=='global-build-source':
        _retained(provider,consent.handle,ctx)
        raise GameDataError('publisher_configuration_reader_unresolved',GATE,409)
    _check(consent.stage==consent.handle['stage']=='global-build-manifests')
    artifact=_read(ctx,consent.handle['receipt_sha256'])
    _check(consent==_quote(provider,artifact,consent.handle,ctx))
    build,_=_selection(provider,artifact,ctx)
    transport=provider.transport_factory(ctx,hosts=set(inventory.RESOURCE_HOSTS))
    records=[]
    pending=[]
    try:
        for pin in artifact['pins']:
            stage_digest=_sha(_json(pin));target=_path(ctx,stage_digest,'manifest')
            pending.append(target)
            info=transport.download_to(pin['url'],target,limit=pin['total'],expected_size=pin['total'],
                kind='asset',headers={'If-Match':pin['etag']})
            raw=target.read_bytes();_check(raw[:32].hex()==pin['prefix'])
            chunks.parse_manifest(raw,expected_sha256=info.sha256,manifest_url=pin['url'],expected_version=build['DefaultVersion'])
            after,_=transport.fetch_bytes(pin['url'],limit=32,expected_size=32,kind='metadata',
                original_range=(0,32,pin['total']),headers={'If-Match':pin['etag']})
            _check(after.hex()==pin['prefix'])
            records.append({'role':pin['role'],'sha256':info.sha256,'bytes':pin['total'],'transfer':info.json()})
        ctx.check()
        for target,row in zip(pending,records):
            destination=_path(ctx,row['sha256'],'manifest')
            if destination.exists():_check(_sha(destination.read_bytes())==row['sha256'])
            else:_foundation().atomic_replace(target,destination)
        digest=_store(ctx,{'policy':POLICY,'request':ctx.request.json(),
            'artifact_sha256':consent.handle['receipt_sha256'],'manifests':records})
        ctx.check()
    finally:
        for path in pending:
            _no_links(path);path.unlink(missing_ok=True)
    return PreparationStage({'policy':_foundation().POLICY,'request':ctx.request.json(),
        'stage':'global-build-source','receipt_sha256':digest},GATE)


def restore(provider,handle,ctx):
    if handle['stage']=='global-build-source':_retained(provider,handle,ctx)
    else:_selection(provider,_read(ctx,handle['receipt_sha256']),ctx)
    raise GameDataError('publisher_configuration_reader_unresolved',GATE,409)
