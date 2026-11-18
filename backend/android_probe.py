"""Authored shared-core fixture run unchanged on desktop and embedded Android."""
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
import wave
import sys
import time
import sqlite3
from contextlib import closing

from .prepared_library import write_prepared_library
from .prepared_session import PreparedCaptureSession

TEXT = 'Follow the river beyond the bridge.'


def run_wuwa_bootstrap(root, native, fixture_json):
    """DEBUG-authored source stage through real provider/crypto/mmap contracts.

    The opener supplies only the small authored carrier; production transport,
    budgets, APK authentication, selected-member decode and ELF derivation run
    unchanged. This cannot establish official-server or language-library Ready.
    """
    import base64
    from email.message import Message
    import io
    import re
    from .game_data import GameDataService, _Context
    from .game_data_protocol import GameDataError, GameDataRequest
    from .publisher_transport import PublisherTransport
    from .publisher_crypto import create_publisher_crypto
    from .wuwa_game_data import create_provider
    from . import wuthering_bootstrap_source as source
    from .wuthering_elf_bootstrap import default_output
    if not isinstance(fixture_json,str) or len(fixture_json)>65536:
        raise ValueError('Authored bootstrap envelope exceeds its bound')
    fixture=json.loads(fixture_json)
    if fixture.get('schema')!='toolkit-authored-wuwa-bootstrap-v1':raise ValueError('Invalid authored bootstrap fixture')
    apk=base64.b64decode(fixture['apk_base64'],validate=True)
    if not 1024<=len(apk)<=32768 or len(apk)!=fixture['apk_bytes'] or hashlib.sha256(apk).hexdigest()!=fixture['apk_sha256']:
        raise ValueError('Authored carrier identity changed')
    for field in ('module_sha256','default_output_sha256'):
        if not re.fullmatch('[0-9a-f]{64}',fixture[field]):raise ValueError('Invalid authored expected output')
    # This deliberately rejects host substitutes in production; reference tests
    # install an explicit simulated Java class, never a provider crypto bypass.
    crypto=create_publisher_crypto(platform='android',native=native.publisherCrypto())
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='wuwa-bootstrap-',dir=root))
    url='https://owned.aki-game.com/client/download/original/game.apk'
    cases=[]
    for case in ('text','text-audio','corrupt','cancel'):
        calls=[];controls={'offline':False};activated=[]
        request={'region':'global','source_locale':'ja','target_locales':['en','zh-Hans'],
            'content_mode':case if case in ('text','text-audio') else 'text'}
        class Response(io.BytesIO):
            def __init__(self,raw,target,status,headers,ctx):
                super().__init__(raw);self.url,self.status,self.headers,self.ctx=target,status,Message(),ctx
                for name,value in headers.items():self.headers[name]=str(value)
            def geturl(self):return self.url
            def read(self,size):
                raw=super().read(min(size,173))
                if raw and case=='cancel' and self.ctx.phase=='download':self.ctx.cancel.set()
                return raw
        def transport(ctx,**kwargs):
            def open_(request,**unused):
                if controls['offline']:raise AssertionError('An offline native stage attempted transport')
                target=request.full_url;calls.append((target,ctx.phase))
                if target.startswith(source.CATALOGUE+'?_t='):
                    raw=json.dumps({'primary':url,'version':'1.0.0'}).encode()
                    return Response(raw,target,200,{'Content-Length':len(raw)},ctx)
                if target!=url:raise AssertionError('Unexpected authored source URL')
                headers={'ETag':'"authored-bootstrap"'}
                selected=request.get_header('Range')
                if selected:
                    low,high=map(int,selected.removeprefix('bytes=').split('-'))
                    if not 0<=low<=high<len(apk):raise AssertionError('Invalid fixture range')
                    raw=apk[low:high+1]
                    headers.update({'Content-Range':f'bytes {low}-{high}/{len(apk)}','Content-Length':len(raw)})
                    return Response(raw,target,206,headers,ctx)
                raw=bytearray(apk)
                if case=='corrupt':raw[-23]^=1
                headers['Content-Length']=len(raw)
                return Response(bytes(raw),target,200,headers,ctx)
            return PublisherTransport(ctx,opener=open_,**kwargs)
        provider=create_provider('android',native,transport_factory=transport)
        directory=work/case;marker=directory/'retained-history';directory.mkdir()
        marker.write_bytes(b'Authored old history and recording marker')
        service=GameDataService(directory,{'wuwa':provider},on_activate=lambda *args:activated.append(True))
        try:
            quote=service.plan('wuwa',request)['game']
            if not quote['can_download'] or quote['download_bytes']!=len(apk) or quote['can_activate']:
                raise ValueError('Authored native source quote changed')
            pending=service.plans[quote['plan_id']]
            ctx=_Context(service,directory,'local','wuwa',GameDataRequest.parse(request),directory/'restore','restore')
            before=len(calls)
            try:provider.restore(pending['plan'].handle,ctx)
            except GameDataError as error:
                if error.code!='publisher_bootstrap_incomplete':raise
            else:raise ValueError('A quote claimed verified native source')
            if len(calls)!=before:raise ValueError('Quote restore performed transport')
            service.download('wuwa',{'plan_id':quote['plan_id'],'revision':quote['revision']})
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                row=next(row for row in service.snapshot()['games'] if row['id']=='wuwa')
                if row['job'] and row['job']['status'] not in ('queued','running'):break
                time.sleep(.01)
            if row['job'] is None or row['job']['status'] in ('queued','running'):
                raise ValueError('Authored bootstrap worker did not finish')
            if row['can_activate'] or row['state']=='ready' or activated or (directory/'wuwa/current.json').exists():
                raise ValueError('Bootstrap stage incorrectly activated a language library')
            if marker.read_bytes()!=b'Authored old history and recording marker':raise ValueError('Existing data changed')
            if case in ('corrupt','cancel'):
                if row['job']['status']=='needs_plan' or list(directory.rglob('module.so')) or (directory/'wuwa/stage.json').exists():
                    raise ValueError('A failed native bootstrap was published')
                if row['job']['downloaded_bytes']<=0:raise ValueError('Failed transfer lost its accounting')
                cases.append({'case':case,'rejected':True,'retained_data':True,'charged_bytes':row['job']['downloaded_bytes']})
                continue
            if row['job']['status']!='needs_plan' or row['job']['downloaded_bytes']!=len(apk):
                raise ValueError('Native bootstrap did not publish its bounded stage')
            stage=service._stage_handle(directory,'wuwa',GameDataRequest.parse(request))
            module=source._module(ctx.cache_directory,stage['source'])
            if module.stat().st_size!=fixture['module_bytes']:raise ValueError('Retained native member size changed')
            parsed=default_output(module,fixture['module_sha256'])
            if (hashlib.sha256(parsed.parameter).hexdigest()!=fixture['default_output_sha256']
                    or any(getattr(parsed,name)!=fixture[name] for name in ('callback','initializer','source_address'))):
                raise ValueError('Original native source-data derivation changed')
            controls['offline']=True;before=len(calls)
            warm=service.plan('wuwa',request)['game']
            if warm['can_download'] or warm['can_activate'] or len(calls)!=before:
                raise ValueError('Cached native stage crossed its format gate')
            service.close()
            service=GameDataService(directory,{'wuwa':provider})
            restarted=service.plan('wuwa',request)['game']
            if restarted['can_download'] or restarted['can_activate'] or len(calls)!=before:
                raise ValueError('Fresh service failed offline stage recovery')
            ctx=_Context(service,directory,'local','wuwa',GameDataRequest.parse(request),directory/'restore','restore')
            try:provider.restore(stage,ctx)
            except GameDataError as error:
                if error.code!='publisher_format_key_unresolved':raise
            else:raise ValueError('Native stage incorrectly restored a prepared language library')
            cases.append({'case':case,'stage':'manifest-format','downloaded_bytes':row['job']['downloaded_bytes'],
                'module_sha256':parsed.module_sha256,'full_apk_verified':True,'mmap_data_parser':True,
                'offline_restart':True,'snapshot_activated':False,'retained_data':True})
        finally:service.close()
    import mmap
    mmap_file=getattr(mmap,'__file__',None)
    mmap_runtime={'android_extension':False}
    if mmap_file and Path(mmap_file).name=='mmap.cpython-312.so':
        path=Path(mmap_file)
        if not 0<path.stat().st_size<=128*1024:raise ValueError('Unexpected mmap native extension size')
        mmap_runtime={'android_extension':True,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return json.dumps({'schema':'toolkit-android-authored-wuwa-bootstrap-v1','passed':True,'cases':cases,
        'fixture_sha256':hashlib.sha256(fixture_json.encode()).hexdigest(),'apk_sha256':fixture['apk_sha256'],
        'original_game_bytes':False,'actual_network':False,'snapshot_ready':False,'crypto_proof':crypto._proof,
        'mmap_runtime':mmap_runtime})


def _library(root, text=TEXT, identity='authored:bridge', *, duration=0.2, game='zzz', records=None, metadata=None, clips=None):
    root.mkdir(parents=True, exist_ok=True)
    clip = root / 'authored-tone.wav'
    with wave.open(str(clip), 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        if not 0 < duration <= 10:
            raise ValueError('Authored fixture duration is outside its bound')
        output.writeframes(b''.join(struct.pack('<h', round(6000 * math.sin(2 * math.pi * 440 * i / 16000))) for i in range(round(16000 * duration))))
    row = dict(text_id=identity, english=text, chinese='沿河走过桥。', source_locale='en',
        source_text=text, texts={'en': text, 'zh-Hans': '沿河走过桥。'}, audio_locale='en',
        audio={'authored-fixture': True}, voice_status='voiced', dialogue_kind='conversation')
    snapshot = dict(format=2, game=game, source_locale='en', records=[row] if records is None else records)
    snapshot.update(metadata or {})
    return write_prepared_library(snapshot, root / 'library.zip', {identity: clip} if clips is None else clips)


def run(root, native=None):
    root = Path(root);root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='shared-core-', dir=root))
    library = _library(work / 'original')
    session = PreparedCaptureSession(work / 'application')
    session.import_library(library)
    generation = session.start()
    first = session.observe(generation, 1, [TEXT], now=1)
    replay = session.observe(generation, 1, [TEXT], now=1.01)
    confirmed = session.observe(generation, 2, [TEXT], now=1.02)
    if len(confirmed) != 1:
        raise ValueError('Shared confirmation fixture failed')
    identity = confirmed[0]['id']
    audio = session.audio_path(identity)
    original_pcm = audio.read_bytes()
    session.history.set_favorite(identity, True)
    session.stop()
    late = session.observe(generation, 3, [TEXT], now=1.03)
    pointer = session.libraries.pointer.read_bytes()
    cancelled = False
    try:
        session.import_library(library, cancelled=lambda: True)
    except InterruptedError:
        cancelled = session.libraries.pointer.read_bytes() == pointer
    broken = work / 'broken.zip';broken.write_bytes(b'not a library')
    rejected = False
    try:
        session.import_library(broken)
    except Exception:
        rejected = session.libraries.pointer.read_bytes() == pointer
    newer = _library(work / 'new', 'The new chapter follows the river.', 'authored:new')
    session.import_library(newer)
    restarted = PreparedCaptureSession(work / 'application')
    retained = restarted.history.get(identity)
    results = {'first_frame_waited': first == [], 'replayed_frame_rejected': replay == [],
        'confirmed_text_id': confirmed[0]['text_id'], 'confirmed_source_locale': confirmed[0]['source_locale'],
        'confirmed_voice_status': confirmed[0]['voice_status'], 'original_audio_source': confirmed[0]['audio_source'],
        'late_result_rejected': late == [], 'cancelled_import_preserved': cancelled,
        'corrupt_import_preserved': rejected, 'restart_is_stopped': not restarted.running,
        'history_retained': restarted.history.count() == 1, 'favorite_retained': retained.favorite,
        'old_recording_sha256': hashlib.sha256(restarted.audio_path(identity).read_bytes()).hexdigest(),
        'recording_retained': restarted.audio_path(identity).read_bytes() == original_pcm,
        'new_generation_text_id': restarted.index._records[0]['text_id']}
    games = {}
    for game in ('zzz', 'genshin', 'starrail', 'endfield', 'wuwa', 'nte'):
        game_identity = 'authored:' + game + ':bridge'
        official = 'Your journey continues beyond the bridge, {PlayerName}.' if game == 'wuwa' else TEXT
        observed = official.replace('{PlayerName}', 'Pilot')
        imported = PreparedCaptureSession(work / ('game-' + game))
        imported.import_library(_library(work / ('input-' + game), official, game_identity, game=game))
        scope = imported.start()
        waited = imported.observe(scope, 1, [observed], now=1)
        emitted = imported.observe(scope, 2, [observed], now=1.1)
        if waited or len(emitted) != 1 or emitted[0]['text_id'] != game_identity or emitted[0]['game'] != game:
            raise ValueError('The packaged shared core did not capture the authored ' + game + ' fixture')
        displayed = emitted[0]['source_text']
        with closing(sqlite3.connect(imported.history.path.as_uri() + '?mode=ro', uri=True)) as database:
            canonical = database.execute('SELECT english FROM transcript_lines WHERE id=?', (emitted[0]['id'],)).fetchone()[0]
        if displayed != observed or canonical != official or imported.index._records[0]['source_text'] != official:
            raise ValueError('Prepared presentation changed canonical publisher identity for ' + game)
        reopened = PreparedCaptureSession(work / ('game-' + game))
        if reopened.history.get(emitted[0]['id']).source_text != observed:
            raise ValueError('Prepared presentation did not survive the authored ' + game + ' restart')
        games[game] = {'text_id': emitted[0]['text_id'], 'voice_status': emitted[0]['voice_status'],
            'displayed_source': displayed, 'canonical_source': canonical,
            'original_audio_sha256': hashlib.sha256(imported.audio_path(emitted[0]['id']).read_bytes()).hexdigest()}
    results['prepared_games'] = games
    results['protected_account_lifecycle'] = run_accounts(work / 'accounts', native)
    from .android_game_probe import run as game_caption_proof
    results['game_caption_policy'] = game_caption_proof(work / 'caption-policy')
    if any(value is False for value in results.values()):
        raise ValueError('Shared lifecycle fixture failed')
    encoded = json.dumps(results, sort_keys=True, separators=(',', ':')).encode()
    from rapidfuzz import fuzz, process
    import rapidfuzz
    import pydantic_core
    choices = ['A publisher authored dialogue near the mountain checkpoint ' + str(number) for number in range(50000)]
    started = time.perf_counter()
    process.extract('A publisher auth0red dialogue near the mountain checkpoint 49999', choices,
        scorer=fuzz.ratio, score_cutoff=88, limit=2)
    fuzzy_ms = (time.perf_counter() - started) * 1000
    return json.dumps({'schema': 'toolkit-android-shared-core-probe-v1', 'results': results,
        'result_sha256': hashlib.sha256(encoded).hexdigest(), 'fixture': 'authored-text-and-generated-tone',
        'runtime': {'python': sys.version.split()[0], 'pydantic_core': pydantic_core.__version__,
            'account_protection': 'android-keystore-authored-alias' if native is not None else 'authored-test-adapter',
            'rapidfuzz': rapidfuzz.__version__, 'fuzzy_scorer': fuzz.ratio.__module__,
            'fuzzy_extractor': process.extract.__module__, 'authored_fuzzy_50000_ms': fuzzy_ms},
        'private_audio_path': str(restarted.audio_path(identity))}, sort_keys=True)


def run_accounts(root, native=None):
    """Maintained stores and production capture; every remote call is mocked."""
    import httpx
    from types import SimpleNamespace
    from .android_accounts import AndroidAccountSessions, AndroidAccountConflict
    from .android_protected_storage import AndroidProtectedBlobs
    calls = []
    def reply(request):
        if request.method != 'GET' or request.url.path != '/v1/me':
            raise ValueError('The authored account proof allows only mocked identity reads')
        calls.append('GET /v1/me')
        owner = 'second' if 'second' in request.headers['Authorization'] else 'first'
        return httpx.Response(200, json={'user': {'id': owner, 'name': owner}})
    if native is None:
        protect = lambda value, decrypt=False: bytes(n ^ 173 for n in value)
    else:
        protect = AndroidProtectedBlobs(SimpleNamespace(protect=native.protectAuthored)).protect
    manager = AndroidAccountSessions(root, protect=protect, transport=httpx.MockTransport(reply))
    first = manager.register('lx_first_authored_account_fixture_only', 'First', 0)['active']
    session = manager.session
    session.import_library(_library(root / 'first-input'))
    generation = session.start()
    session.observe(generation, 1, [TEXT], now=1)
    line = session.observe(generation, 2, [TEXT], now=1.1)[0]
    old_id = manager.qualify_line(line)['id']
    session.history.set_favorite(line['id'], True)
    old_account_generation = manager.accounts.generation
    manager.register('lx_second_authored_account_fixture_only', 'Second', old_account_generation)
    isolated = manager.session.history.count() == 0 and manager.session.index is None
    old_ocr = manager.session.observe(generation, 3, [TEXT], now=1.2) == []
    manager.select(first, manager.accounts.generation)
    old_id_rejected = old_import_rejected = False
    try: manager.local_line(old_id)
    except AndroidAccountConflict: old_id_rejected = True
    try: manager.guard_import(session, old_account_generation)
    except AndroidAccountConflict: old_import_rejected = True
    reopened = AndroidAccountSessions(root, protect=protect)
    restored = reopened.session.history.get(line['id'])
    result = {'separate_account_library_and_history': isolated, 'old_ocr_rejected': old_ocr,
        'old_a_b_a_line_rejected': old_id_rejected, 'old_import_rejected': old_import_rejected,
        'restart_history_and_favorite': bool(restored and restored.favorite and not reopened.session.running),
        'restart_original_audio': reopened.session.audio_path(line['id']).read_bytes() == session.audio_path(line['id']).read_bytes(),
        'credential_free_status': 'lx_' not in json.dumps(reopened.status()),
        'protected_saved_blob': b'lx_first' not in manager.accounts.path.read_bytes(),
        'mocked_identity_calls': len(calls)}
    manager.close();reopened.close()
    if any(value is not True for key, value in result.items() if key != 'mocked_identity_calls') or len(calls) != 2:
        raise ValueError('The authored protected-account lifecycle proof failed')
    return result


def run_ocr(root, raw):
    """Feed actual bundled native OCR into the unchanged production session."""
    root = Path(root);root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='native-ocr-', dir=root))
    native_result = json.loads(raw)
    blocks = native_result['blocks']
    observed = [block['text'] for block in blocks]
    session = PreparedCaptureSession(work / 'application')
    session.import_library(_library(work / 'original'))
    generation = session.start()
    first = session.observe(generation, 1, observed, now=1)
    confirmed = session.observe(generation, 2, observed, now=1.1)
    if first or len(confirmed) != 1 or confirmed[0]['text_id'] != 'authored:bridge':
        raise ValueError('Native OCR did not match the authored shared-core fixture')
    from .android_host import presentation_lines
    spans = presentation_lines(native_result, native_result['width'], native_result['height'])
    return json.dumps({'fixture': 'authored-native-bitmap', 'confirmed_text_id': confirmed[0]['text_id'],
        'presentation_line_count': len(spans), 'minimum_line_confidence': min((span['confidence'] for span in spans), default=None),
        'voice_status': confirmed[0]['voice_status'], 'original_audio_available': session.audio_path(confirmed[0]['id']).is_file()})


def run_zstandard(root, vectors_json):
    """Load the actual C extension and exercise bounded authored manifests.

    The Android debug host supplies its pinned authored asset. This function
    has no publisher network access and does not register a ready game source.
    """
    import zstandard
    from zstandard import backend_c
    from . import sophon_assets
    if len(vectors_json) > 64 * 1024:
        raise ValueError('Authored native extension fixture exceeds its bound')
    vectors = json.loads(vectors_json)
    if (zstandard.__version__ != vectors['version'] or zstandard.backend != 'cext'
            or list(zstandard.ZSTD_VERSION) != vectors['zstd'] or not 1 <= len(vectors['cases']) <= 32):
        raise ValueError('The actual pinned native Zstandard backend is required')
    native = Path(backend_c.__file__)
    if native.suffix not in {'.so', '.pyd'} or not 1 <= native.stat().st_size <= 2 * 1024**2:
        raise ValueError('The actual native extension is absent')
    results = []
    for case in vectors['cases']:
        frame = bytes.fromhex(case['frame_hex'])
        expected = case['result']
        try:
            raw = zstandard.ZstdDecompressor(max_window_size=case['max_window_size_bytes']).decompress(
                frame, max_output_size=case['max_output_size'], allow_extra_data=False)
        except (zstandard.ZstdError, ValueError) as error:
            if expected['accepted'] or type(error).__name__ != expected['error']:
                raise ValueError('The native extension rejected a valid authored manifest') from error
            result = {'name':case['name'], 'accepted':False, 'error':type(error).__name__}
        else:
            digest = hashlib.sha256(raw).hexdigest()
            if not expected['accepted'] or len(raw) != expected['bytes'] or digest != expected['sha256']:
                raise ValueError('The native extension returned different authored bytes')
            result = {'name':case['name'], 'accepted':True, 'bytes':len(raw), 'sha256':digest}
        results.append(result)
    unknown = next(case for case in vectors['cases'] if case['name'] == 'unknown')
    frame = bytes.fromhex(unknown['frame_hex'])
    payload = zstandard.ZstdDecompressor(max_window_size=unknown['max_window_size_bytes']).decompress(
        frame, max_output_size=unknown['max_output_size'], allow_extra_data=False)
    cache = Path(root);cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(payload).hexdigest();calls = []
    def fetch(url, *, limit):
        if url != 'https://publisher.invalid/authored' or limit != len(frame):
            raise ValueError('Unexpected authored manifest request')
        calls.append(True);return frame
    def no_fetch(*args, **kwargs): raise ValueError('A verified cached manifest attempted a transfer')
    actual = sophon_assets._verified(cache, 'https://publisher.invalid/authored', len(frame), len(payload),
        digest, sophon_assets.MAX_CHUNK, fetch=fetch)
    cached = sophon_assets._verified(cache, 'https://publisher.invalid/authored', len(frame), len(payload),
        digest, sophon_assets.MAX_CHUNK, fetch=no_fetch)
    if actual != payload or cached != payload or len(calls) > 1:
        raise ValueError('The shared bounded manifest/cache contract failed')
    return json.dumps({'fixture':'authored-native-zstandard-manifests', 'version':zstandard.__version__,
        'zstd':list(zstandard.ZSTD_VERSION), 'backend':zstandard.backend,
        'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),
        'cases':results, 'sophon_context_and_offline_cache':True, 'publisher_requests':0})


def _crypto_cases(crypto, capi, jca):
    """Run the same bounded authored vectors on the reference and real APK.

    Positive operations traverse the explicit crypto API; envelope rejections
    are separate from native execution. No fixture key or plaintext is returned.
    """
    import io
    import struct
    from .publisher_crypto import MAX_BYTES, RsaPrivateNumbers
    if any(type(raw) is not bytes or not 8 <= len(raw) <= 65536 for raw in (capi,jca)):
        raise ValueError('Authored publisher crypto fixture exceeds its bound')
    def take(stream, size):
        if not 0 <= size <= 65536:raise ValueError('Invalid authored crypto field length')
        raw = stream.read(size)
        if len(raw) != size:raise ValueError('Truncated authored crypto fixture')
        return raw
    def number(stream, fmt):return struct.unpack(fmt,take(stream,struct.calcsize(fmt)))[0]
    def invoke(call, expected):
        try:result = call()
        except ValueError:
            if expected != -2:raise ValueError('The actual crypto runtime rejected a valid authored case') from None
        else:
            if expected == -2 or result != expected:raise ValueError('The actual crypto runtime returned different authored bytes')
    stream = io.BytesIO(capi)
    if take(stream,4) != b'TPC1' or number(stream,'<I') != 16:raise ValueError('Unexpected authored ChaCha cases')
    positives = 0
    for _ in range(16):
        kl,nl,size,claimed,position,accepted = struct.unpack('<IIIQQI',take(stream,32))
        if accepted not in (0,1):raise ValueError('Invalid authored crypto result')
        key,nonce,data = take(stream,kl),take(stream,nl),take(stream,size)
        expected = take(stream,size) if accepted else -2
        def chacha():
            if claimed != len(data) or claimed > MAX_BYTES:raise ValueError('Invalid authored crypto envelope')
            return crypto.chacha20(key,nonce,data,position=position)
        invoke(chacha,expected);positives += accepted
    if stream.read(1) or positives != 8:raise ValueError('Unexpected authored ChaCha inventory')
    stream = io.BytesIO(jca)
    if take(stream,4) != b'PBJ1' or number(stream,'>I') != 41:raise ValueError('Unexpected authored JCA cases')
    operations = {'block':0,'verify':0,'decrypt':0}
    def field(value, nullable=False):
        length = number(value,'>i')
        if nullable and length == -1:return None
        return take(value,length)
    for _ in range(41):
        payload = io.BytesIO(take(stream,number(stream,'>I')))
        operation = take(payload,number(payload,'>H')).decode('ascii')
        if operation == 'block':
            algorithm = take(payload,number(payload,'>H')).decode('ascii')
            mode = take(payload,number(payload,'>H')).decode('ascii')
            decrypt = number(payload,'>B')
            if decrypt not in (0,1):raise ValueError('Invalid authored cipher direction')
            key,iv,data = field(payload),field(payload,True),field(payload)
            call = lambda:crypto.block_cipher(algorithm,mode,key,data,iv=iv,decrypt=bool(decrypt))
        elif operation == 'verify':
            public,data,signature = field(payload),field(payload),field(payload)
            call = lambda:bytes([crypto.rsa_verify_sha256(public,data,signature)])
        elif operation == 'decrypt':
            numbers = [int.from_bytes(field(payload),'big') for _ in range(5)]
            data = field(payload)
            call = lambda:crypto.rsa_decrypt_pkcs1(RsaPrivateNumbers(*numbers),data)
        else:raise ValueError('Unsupported authored crypto operation')
        if payload.read(1):raise ValueError('Extra authored operation bytes')
        length = number(stream,'>i')
        if length < -2:raise ValueError('Invalid authored crypto result length')
        expected = -2 if length == -2 else None if length == -1 else take(stream,length)
        invoke(call,expected);operations[operation] += 1
    if stream.read(1) or operations != {'block':31,'verify':5,'decrypt':5}:
        raise ValueError('Unexpected authored JCA inventory')
    return {'fixture':'authored-packaged-publisher-crypto','passed':True,'capi_cases':16,'jca_cases':41,
        'chacha_positive_cases':positives,'operations':operations,
        'fixtures':{kind:{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'cases':count}
            for kind,raw,count in (('capi',capi,16),('jca',jca,41))},
        'publisher_requests':0,'account_keys_reused':False,'original_client_execution':False}


def _genshin_profile_cases(root, fixture_json, runtime):
    """Authored component checks; the caller establishes the actual runtime."""
    import base64
    from .private_data_paths import _no_links
    if type(fixture_json) is not str or len(fixture_json.encode('utf8')) > 65536:
        raise ValueError('Authored profile input exceeds its bound')
    value = json.loads(fixture_json)
    if (value.get('schema') != 'toolkit-authored-genshin-profile-v1'
            or value.get('original_game_bytes') is not False):
        raise ValueError('Unknown authored profile input')
    expected = value['expected']
    if expected['codec_candidates'] != 2 or expected['accepted_candidates'] != 1:
        raise ValueError('Authored codec selection changed')
    executable = base64.b64decode(value['executable_base64'], validate=True)
    raw = base64.b64decode(value['carrier_base64'], validate=True)
    if (not 512 <= len(executable) <= 32768 or not 84 <= len(raw) <= 4096
            or hashlib.sha256(executable).hexdigest() != expected['executable_sha256']
            or hashlib.sha256(raw).hexdigest() != expected['carrier_sha256']
            or len(raw) != expected['carrier_bytes'] or hashlib.md5(raw).hexdigest() != expected['carrier_md5']):
        raise ValueError('Authored source identity changed')
    root = Path(root); _no_links(root); root.mkdir(parents=True, exist_ok=True)
    active, source, pending = (root/name for name in ('accepted-profile.bin', 'authored.blk', 'profile.pending'))
    for path in (active, source, pending): _no_links(path)
    if not active.exists(): active.write_bytes(b'Prior authored profile must survive malformed input.')
    if not active.is_file() or active.stat().st_size > 4096 or pending.exists():
        raise ValueError('Preserve the existing authored component state')
    previous = hashlib.sha256(active.read_bytes()).hexdigest()
    def prepare(data):
        source.write_bytes(data)
        receipt = {'name':'Assets/'+value['contract']['source_basename'], 'bytes':len(data),
            'sha256':hashlib.sha256(data).hexdigest(), 'md5':hashlib.md5(data).hexdigest()}
        return runtime.channel_profile(executable, source, receipt, value['contract'],
            directory=root, check_cancel=lambda: None)
    malformed = value.get('malformed')
    if (not isinstance(malformed, list) or len(malformed) != 2
            or {row.get('kind') for row in malformed} != {'payload-eof', 'complete-map'}):
        raise ValueError('Authored negative inventory changed')
    rejected = 0
    for row in malformed:
        data = base64.b64decode(row['carrier_base64'], validate=True)
        if not 84 <= len(data) <= 4096: raise ValueError('Authored negative exceeds its bound')
        try: prepare(data)
        except ValueError: rejected += 1
        else: raise ValueError('An incomplete profile was accepted')
        if hashlib.sha256(active.read_bytes()).hexdigest() != previous:
            raise ValueError('A malformed profile replaced the prior state')
    prepared = prepare(raw); proof = prepared.proof
    if (proof['native_executable_sha256'] != expected['executable_sha256']
            or proof['source']['sha256'] != expected['carrier_sha256']
            or proof['body_sha256'] != expected['body_sha256'] or proof['payload_sha256'] != expected['payload_sha256']
            or proof['codec_parameters_sha256'] != expected['parameters_sha256']
            or proof['codec_method_sha256s'] != expected['method_sha256s']
            or proof['helper_identity'] != runtime.identity
            or proof['original_codec_candidates_tested'] != 2 or proof['profile_count'] != expected['profile_count']
            or proof['objects'] != expected['objects'] or proof['named_objects'] != expected['named_objects']
            or proof['complete_named_object_map'] is not True or proof['strict_payload_eof'] is not True
            or proof['profile_only'] is not True or any(proof[key] is not False for key in
                ('complete_dispatch_bootstrap','full_catalog_validated','selected_shards_validated',
                 'later_override_excluded','response_signature_verified','community_numeric_data_used'))
            or hashlib.sha256(prepared.payload).hexdigest() != expected['payload_sha256']
            or list(root.glob('channel-codec-*'))):
        raise ValueError('Authored complete profile differs from its independent reference')
    with pending.open('xb') as output: output.write(prepared.payload)
    pending.replace(active)
    return {'schema':'toolkit-authored-genshin-profile-proof-v1','passed':True,'codec_candidates':2,
        'accepted_candidates':1,'malformed_rejections':rejected,'prior_state_retained_on_failure':True,
        'fixture_sha256':hashlib.sha256(fixture_json.encode('utf8')).hexdigest(),
        'body_sha256':proof['body_sha256'],'payload_sha256':proof['payload_sha256'],
        'parameters_sha256':proof['codec_parameters_sha256'],'method_sha256s':proof['codec_method_sha256s'],
        'complete_named_object_map':True,'strict_payload_eof':True,'profile_only':True,
        'full_catalog_validated':False,'selected_shards_validated':False,'response_signature_verified':False,
        'complete_dispatch_bootstrap':False,'later_override_excluded':False,'community_numeric_data_used':False,
        'original_game_bytes':False,'network_requests':0,'factory_activated':False,
        'runtime_identity':runtime.identity,'runtime_provenance':proof.get('runtime_provenance')}


def run_genshin_profile(root, fixture_json):
    """Called only by DEBUG self-test after the actual native host has started."""
    from . import android_host
    from .genshin_android_runtime import AndroidGenshinRuntime
    with android_host._host_lock:
        host = android_host._host
        if host is None or host.data_decoder is None:
            raise ValueError('The installed host data decoder is required')
        # AndroidGenshinRuntime rechecks exact provider identity, the maintained
        # Java class and all 15 actual decoder contracts. No desktop fallback.
        runtime = AndroidGenshinRuntime(host.data_decoder)
    result = _genshin_profile_cases(root, fixture_json, runtime)
    result['installed_host_decoder'] = True
    return json.dumps(result)


def run_crypto(native, capi_base64, jca_base64):
    import base64
    from .publisher_crypto import create_publisher_crypto
    if any(type(raw) is not str or len(raw) > 90000 for raw in (capi_base64,jca_base64)):
        raise ValueError('Authored publisher crypto input exceeds its bound')
    try:crypto = create_publisher_crypto(platform='android',native=native.publisherCrypto())
    except Exception:raise ValueError('The packaged publisher cryptography runtime is unavailable.') from None
    result = _crypto_cases(crypto,base64.b64decode(capi_base64,validate=True),base64.b64decode(jca_base64,validate=True))
    return json.dumps({**result,'runtime':crypto._proof})


def run_preview(native):
    """Exercise actual Android bitmap/JPEG crops using the shared geometry."""
    from .capture_geometry import picture_bounds, region_bounds
    from .models import CaptureRegion
    results = []
    for width, height in ((1600, 1200), (2400, 1080)):
        picture = picture_bounds((0, 0, width, height), '16:9')
        for half in (False, True):
            region = CaptureRegion(left=.5 if half else 0, top=.5 if half else 0,
                width=.5 if half else 1, height=.5 if half else 1)
            crop = region_bounds(picture, region)
            result = json.loads(str(native.authoredPreviewProbe(width, height, *picture, *crop)))
            ratio = min(1, 1280 / max(crop[2:]))
            if (result['width'], result['height']) != tuple(round(n * ratio) for n in crop[2:]):
                raise ValueError('Native preview dimensions differ from shared crop geometry')
            def color(pixel):
                return ((pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255)
            first, last = color(result['first_pixel']), color(result['last_pixel'])
            if not (last[0] > 240 and last[1] < 15 and last[2] < 15):
                raise ValueError('Native preview did not retain the authored red corner')
            if not ((first[0] > 240 and first[2] < 15) if half else (first[2] > 240 and first[0] < 15)):
                raise ValueError('Native preview included black bars or a different crop')
            results.append({'source': [width, height], 'crop': crop, **result})
    return json.dumps({'fixture': 'authored-native-black-bars-and-quadrants', 'cases': results, 'passed': True})
