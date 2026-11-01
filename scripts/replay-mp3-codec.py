"""Fixed MP3 recipe: additional BSD-3-Clause option for approved original portions.

See packaging/codecs/MP3-BUILD-RECIPES-LICENSE.txt for exact scope and terms.
The ordinary-license Windows helper and all upstream rights remain separate.
No runtime or complete-source approval follows.
"""
import argparse, contextlib, difflib, hashlib, importlib.util, io, json, math, os
from pathlib import Path, PurePosixPath
import re, shutil, stat, struct, subprocess, sys, tarfile, tempfile, time, urllib.request, wave, zipfile
def bootstrap_regular(path):
    # The unchanged helper cannot guard its own first read. Walk raw ancestors
    # here before any descendant metadata or recipe import; never resolve links.
    path=Path(path).absolute()
    if '..' in path.parts:raise ValueError('Noncanonical bootstrap path refused.')
    for item in (*reversed(path.parents),path):
        try:info=item.lstat()
        except OSError:raise ValueError('Bootstrap input unavailable.') from None
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400 or (item!=path and not stat.S_ISDIR(info.st_mode)):
            raise ValueError('Bootstrap link or nonordinary ancestor refused.')
    if not stat.S_ISREG(info.st_mode):raise ValueError('Bootstrap recipe is not an ordinary file.')
    if info.st_size>2*1024*1024:raise ValueError('Bootstrap recipe exceeds its fixed bound.')
    return info

_DRIVER=Path(__file__).absolute()
bootstrap_regular(_DRIVER)
ROOT=_DRIVER.parents[1]
PIN=ROOT/'packaging/codecs/ffmpeg-mp3-replay.json'
BASE_PATH=ROOT/'scripts/replay-game-codec.py'
BASE_SHA='41a578f87ff9fccc776a5807dfc1e292c5356d523052aa203947458c61099d6a'
bootstrap_regular(BASE_PATH)
with BASE_PATH.open('rb') as _stream:_helper=_stream.read(2*1024*1024+1)
if len(_helper)>2*1024*1024:raise ValueError('Bootstrap read exceeds its fixed bound.')
_helper=_helper.replace(b'\r\n',b'\n')
if b'\r' in _helper or b'\0' in _helper or hashlib.sha256(_helper).hexdigest()!=BASE_SHA:
    raise ValueError('Exact unchanged helper input required.')
spec=importlib.util.spec_from_file_location('unchanged_mp3_recipe_helpers',BASE_PATH)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
FUNCTIONAL_INPUTS=('packaging/codecs/ffmpeg-mp3-replay.json','scripts/replay-mp3-codec.py',
 'scripts/build-mp3-codec-replay.ps1','scripts/fixtures/mp3-codec-origin.c',
 'packaging/codecs/patches/lame-4.0-mpg123-prelink-guard.patch')
DEPENDENCY_INPUTS=('backend/windows_preparation_process.py',)
MP3_GRANT='packaging/codecs/MP3-BUILD-RECIPES-LICENSE.txt'
MP3_APPROVED_BASELINES={'packaging/codecs/ffmpeg-mp3-replay.json': {'bytes': 15933, 'sha256': '8274d8842d05596f49f644f313dd0f885b19b37240fa21dc877fd3b3ff36f4e4'}, 'scripts/replay-mp3-codec.py': {'bytes': 48280, 'sha256': '615ea978748aa692381bb592628743fbf4b9a4c9ad449be51d929c796a3f4db7'}, 'scripts/build-mp3-codec-replay.ps1': {'bytes': 35311, 'sha256': 'a0d6f92af1bf7e7377b6eafba902f1c16e120bbee7edd770dcfc76e46676d638'}, 'scripts/fixtures/mp3-codec-origin.c': {'bytes': 1571, 'sha256': 'c26d6d6c5285c73934fbe214d528b8efea2d5596a65cb8ab57578eb93f1853c3'}}
MP3_PROJECT_LICENSE={'schema': 'proxy-r19-mp3-recipe-additional-license-v1', 'identifier': 'BSD-3-Clause', 'scope': 'four-approved-original-project-revisions-and-necessary-notice-source-delivery-wiring', 'approved_on': '2026-11-01', 'approval_proposal_sha256': '3adc6e4775f8bb5f53e2d63ec031eec8222c80c319fc0c268906d1533b80601c', 'grant': {'path': 'packaging/codecs/MP3-BUILD-RECIPES-LICENSE.txt', 'bytes': 4588, 'sha256': 'f470deb41e0feea5f564b739e79c1378e457d6a7a6512f4c71a9e39958c476d1'}}
PROJECT_INPUTS=base.PROJECT_INPUTS+FUNCTIONAL_INPUTS+DEPENDENCY_INPUTS+(MP3_GRANT,)
OVERRIDES=['--build-suffix=-r19-audio-lame','--enable-ffmpeg','--disable-ffplay',
 '--disable-ffprobe','--enable-w32threads','--enable-avfilter','--enable-libmp3lame',
 '--enable-encoder=libmp3lame,pcm_s16le','--enable-demuxer=s16le','--enable-muxer=mp3,wav,s16le',
 '--enable-protocol=file','--enable-filter=aresample,aformat,anull,atrim,adelay,amix,pan,volume']
FF_DLLS=('avcodec-r19-audio-lame-63.dll','avformat-r19-audio-lame-63.dll',
 'avutil-r19-audio-lame-61.dll','swresample-r19-audio-lame-7.dll','avfilter-r19-audio-lame-12.dll')
DLLS=FF_DLLS+('libmp3lame.dll',)
PHASES=base.BUILD_PHASES+('build-lame','install-lame')
FLAGS={'source_delivery_approved':False,'runtime_collection_allowed':False,
 'production_execution_allowed':False,'r19_complete':False,
 'native_windows_11_acceptance':'unavailable','installer':'not-built'}
sha=base.digest
record=lambda b:{'bytes':len(b),'sha256':sha(b)}
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
write=base.write_json

def policy():
    p=base.recipe_json(PIN);bootstrap_regular(base.PIN);old=base.policy()
    if (p.get('schema')!='proxy-r19-mp3-functional-draft-inputs-v1'
        or p.get('audio_cli_overrides')!=OVERRIDES
        or p.get('build_recipe_license')!=MP3_PROJECT_LICENSE
        or p.get('helper_binding')!={'path':'scripts/replay-game-codec.py','sha256':BASE_SHA}
        or p.get('original_dependency_profile',{}).get('sha256')!=sha(base.PIN.read_bytes().replace(b'\r\n',b'\n'))
        or p.get('sources',[])[:2]!=old['sources'] or len(p.get('sources',[]))!=3
        or p['sources'][2]!={'component':'lame','version':'4.0','filename':'lame-4.0.tar.gz',
            'source':'https://downloads.sourceforge.net/project/lame/lame/4.0/lame-4.0.tar.gz',
            'bytes':1496810,'sha256':'3df5124d5ad3a98312ffd7ba6a9b36230e4f8a3e66d3ce0f425e336c32d216eb','root':'lame-4.0'}
        or p.get('original_recipes')!=old['original_recipes']
        or p.get('host')!=old['host'] or p.get('build_tools')!=old['build_tools']
        or any(p.get(k) is not v for k,v in FLAGS.items() if type(v) is bool)):
        raise ValueError('Fixed MP3 profile or inherited input identity differs.')
    if record(base.recipe_bytes(ROOT/MP3_GRANT))!={k:MP3_PROJECT_LICENSE['grant'][k] for k in ('bytes','sha256')}:raise ValueError('Exact scoped MP3 license notice differs.')
    child=p.get('cli_child',{})
    exact={'job_active_process_limit':1,'operation_deadline_seconds':20,'cleanup_wait_seconds':5,
        'input_bytes_cap':262144,'progress_bytes_cap':32768,'progress_records_cap':128,
        'progress_period_seconds':'0.1','analyze_duration_us':100000,'probe_bytes':4096}
    if any(type(child.get(k)) is not type(v) or child.get(k)!=v for k,v in exact.items()):
        raise ValueError('Fixed CLI observation budget differs.')
    primitive=child.get('owned_primitive',{})
    if primitive.get('path')!='backend/windows_preparation_process.py' or primitive.get('canonical_lf_sha256')!='24a6995cc1d4d9260a9afe3049fbdf5d927cfddcfd405095ebcd49674e7234d0' or primitive.get('license_record')!={'path':'LICENSE','bytes':1492,'canonical_lf_sha256':'1d2f36f13b16b401e4bbf81e955ea185d50c6b5de281d89915e240138b7bb396'}:
        raise ValueError('Exact ordinary-license owned primitive differs.')
    names=child.get('system_module_allowlist')
    if type(names) is not list or not names or len(names)>128 or any(type(n) is not str or not re.fullmatch(r'[a-z0-9_]+(?:\.[a-z0-9_]+)*\.dll',n) for n in names) or names!=sorted(set(names)):
        raise ValueError('Finite system observation labels differ.')
    return p

def inputs(p,tools=True):
    return p['sources']+[dict(x,source=x['download']) for x in p['original_recipes']]+(p['build_tools'] if tools else [])

def project_names():
    names=[];seen=set()
    for n in PROJECT_INPUTS:
        if type(n) is not str or not n or '\\' in n or ':' in n or PurePosixPath(n).is_absolute() or str(PurePosixPath(n))!=n or any(x in ('.','..') for x in PurePosixPath(n).parts) or n.casefold() in seen:
            raise ValueError('Duplicate or noncanonical project input refused before access.')
        seen.add(n.casefold());names.append(n)
    return tuple(names)

def project_bytes():
    return {n:base.recipe_bytes(ROOT/n) for n in project_names()}

def source_kit_names(p):
    names=['original-inputs/'+r['filename'] for r in inputs(p,False)]+['project-orchestration/'+n for n in project_names()]+['BASE-BSD-COPIES.json','FUNCTIONAL-LICENSE-BOUNDARY.json','MP3-BSD-COPIES.json']
    if len(names)!=len({n.casefold() for n in names}):raise ValueError('Duplicate source-kit destination refused.')
    return set(names)

def patch_lame(original,patch,p):
    v=p['lame_variant']
    if record(original)!=v['preimage'] or record(patch)!={k:v['patch'][k] for k in ('bytes','sha256')}:
        raise ValueError('LAME guard patch preimage or patch identity differs.')
    modified=original
    for arch in ('Win32','x64'):
        old=f'Condition="!Exists(\'$(Mpg123Path)libmpg123-0.lib\') And \'$(Platform)\' == \'{arch}\'"'.encode()
        if modified.count(old)!=1:raise ValueError('Two exact original prelink conditions required.')
        modified=modified.replace(old,old.replace(b'Condition="',b'Condition="\'$(HaveMpg123)\' == \'true\' And '))
    expected=''.join(difflib.unified_diff(original.decode().splitlines(True),modified.decode().splitlines(True),
        fromfile='a/vc_solution/vs2019_libmpg123_config.props',tofile='b/vc_solution/vs2019_libmpg123_config.props')).encode()
    if patch!=expected or record(modified)!=v['postimage']:
        raise ValueError('Exact two-condition derived source differs.')
    return modified

def acquire(input_root,*,include_tools=True):
    # Defined for a later authorized build-host run; never invoked in this draft.
    if include_tools and sys.platform!='win32':raise ValueError('Native build tools belong on the declared Windows build host only.')
    p=policy();target=Path(input_root).absolute();base.no_links(target)
    if target.exists():raise ValueError('Acquisition requires a fresh owned directory.')
    held={}
    for item in inputs(p,include_tools):
        if not item['source'].startswith('https://'):raise ValueError('Pinned HTTPS source required.')
        with urllib.request.urlopen(item['source'],timeout=90) as stream:data=stream.read(64*1024*1024+1)
        if len(data)>64*1024*1024 or sha(data)!=item['sha256'] or 'bytes' in item and len(data)!=item['bytes']:
            raise ValueError('Acquired input differs from its exact pin.')
        held[item['filename']]=data
    target.mkdir(parents=True)
    for name,data in held.items():(target/name).write_bytes(data)

def validate_inputs(input_root,tools=True):
    p=policy();input_root=Path(input_root).absolute();base.no_links(input_root)
    for r in inputs(p,tools):
        f=input_root/r['filename'];base.regular_file(f)
        if sha(f.read_bytes())!=r['sha256'] or 'bytes' in r and f.stat().st_size!=r['bytes']:
            raise ValueError('Source/tool input differs from fixed identity.')
    for r in p['sources']:
        base.validate_source(input_root/r['filename'],r,[n for n in p['notices'] if n['component']==r['component']])
    return p

def license_boundary():
    return {'original_unchanged_base_grant':base.PROJECT_LICENSE,
        'new_functional_inputs':list(FUNCTIONAL_INPUTS),'ordinary_dependency_inputs':list(DEPENDENCY_INPUTS),
        'ordinary_dependency_license':{'path':'LICENSE',**record(base.recipe_bytes(ROOT/'LICENSE'))},'new_functional_license':'Additional BSD-3-Clause option only for four approved original portions and necessary notice/source wiring; ordinary LICENSE remains an alternative','additional_original_mp3_grant':MP3_PROJECT_LICENSE,
        'derived_upstream_patch':'LAME project-wide license scope; no Firebird grant of upstream rights',
        'fft_provenance':'unresolved; no automatic GPL conclusion',**FLAGS}

def mp3_copy_inventory(files,p):
    if set(files)!=set(project_names()) or p.get('build_recipe_license')!=MP3_PROJECT_LICENSE or MP3_GRANT not in files:
        raise ValueError('Scoped MP3 grant identity missing.')
    if record(files[MP3_GRANT])!={k:MP3_PROJECT_LICENSE['grant'][k] for k in ('bytes','sha256')}:
        raise ValueError('Scoped MP3 grant notice bytes differ.')
    copies={}
    for name in MP3_APPROVED_BASELINES:
        raw=files[name];lf=raw.replace(b'\r\n',b'\n')
        if b'\r' in lf or b'\0' in lf:raise ValueError('Unsupported final MP3 text transform.')
        copies[name]={'raw':record(raw),'canonical_lf':record(lf)}
    return {'schema':'proxy-r19-mp3-final-bsd-copies-v1','license':MP3_PROJECT_LICENSE,
        'approved_baselines':MP3_APPROVED_BASELINES,'copies':copies,
        'scope':'Byte bindings only; no future-functional, helper, upstream or complete-source approval',**FLAGS}

def verify_source_kit(kit,p,files):
    base.check_named_tree(kit,source_kit_names(p))
    for r in inputs(p,False):base.bound_bytes(kit/'original-inputs'/r['filename'],r)
    for n,b in files.items():
        if base.recipe_bytes(kit/'project-orchestration'/n)!=b:raise ValueError('Source delivery copy differs.')
    expected={'BASE-BSD-COPIES.json':base.bsd_copy_inventory({n:files[n] for n in base.PROJECT_INPUTS},base.policy()),
        'FUNCTIONAL-LICENSE-BOUNDARY.json':license_boundary(),'MP3-BSD-COPIES.json':mp3_copy_inventory(files,p)}
    for n,value in expected.items():
        if canonical(base.recipe_json(kit/n))!=canonical(value):raise ValueError('Source license/copy binding differs.')

def verify_lame_work(root,p,require_config):
    work=base.inventory(root/'lame-build-source');before=base.recipe_json(root/'LAME-WORKING-INPUTS.json')
    if base.tree_identity(before)!=p['lame_working_source_tree']:raise ValueError('Derived source receipt differs from fixed source identity.')
    if 'config.h' in work:
        if work.pop('config.h')!=record(base.recipe_bytes(root/'upstream/lame-4.0/configMS.h')):
            raise ValueError('Generated config differs from original configMS.h.')
    elif require_config:raise ValueError('Actual generated LAME config missing.')
    if work!=before:raise ValueError('Working source changed beyond one exact generated config.')

def prepare(input_root,output,*,include_tools=True):
    """Declared source preparation; NOT RUN during this ignored draft review."""
    p=validate_inputs(input_root,include_tools);output=Path(output).absolute();base.no_links(output)
    if output.exists():raise ValueError('Fresh quarantine required.')
    files=project_bytes();old_files={n:files[n] for n in base.PROJECT_INPUTS}
    old_grant=base.bsd_copy_inventory(old_files,base.policy())
    options=base.original_options((Path(input_root)/'vgmstream-ffmpeg_options.txt').read_bytes())
    if len(options)!=36:raise ValueError('Original dependency recipe must remain36 options.')
    output.mkdir(parents=True);kit=output/'source-review';(kit/'original-inputs').mkdir(parents=True)
    upstream=output/'upstream';upstream.mkdir()
    for r in inputs(p,False):shutil.copyfile(Path(input_root)/r['filename'],kit/'original-inputs'/r['filename'])
    for n,b in files.items():
        f=kit/'project-orchestration'/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b)
    for r in p['sources']:
        with tarfile.open(Path(input_root)/r['filename']) as tar:tar.extractall(upstream,filter='data')
    original=base.inventory(upstream);write(output/'PREPARED-SOURCE.json',original)
    work=output/'lame-build-source';shutil.copytree(upstream/'lame-4.0',work)
    target=work/'vc_solution/vs2019_libmpg123_config.props'
    target.write_bytes(patch_lame(target.read_bytes(),files[p['lame_variant']['patch']['path']],p))
    write(output/'LAME-WORKING-INPUTS.json',base.inventory(work))
    write(output/'PROJECT-INPUTS.json',{n:record(b) for n,b in files.items()})
    write(output/'ORIGINAL-OPTIONS.json',options);write(output/'AUDIO-OPTIONS.json',options+OVERRIDES)
    write(kit/'BASE-BSD-COPIES.json',old_grant)
    write(kit/'FUNCTIONAL-LICENSE-BOUNDARY.json',license_boundary())
    write(kit/'MP3-BSD-COPIES.json',mp3_copy_inventory(files,p))
    verify_sources(output)

def verify_sources(root,require_config=False):
    p=policy();root=Path(root).absolute();base.no_links(root)
    current=base.inventory(root/'upstream')
    if base.tree_identity(current)!=p['original_source_tree'] or current!=base.recipe_json(root/'PREPARED-SOURCE.json'):
        raise ValueError('Original supplier sources changed.')
    files=project_bytes();expected={n:record(b) for n,b in files.items()}
    if canonical(expected)!=canonical(base.recipe_json(root/'PROJECT-INPUTS.json')):
        raise ValueError('Draft inputs changed after preparation.')
    verify_source_kit(root/'source-review',p,files)
    verify_lame_work(root,p,require_config)
    return p

def copy_regular(source,target):
    base.regular_file(source);base.no_links(target)
    if target.exists():raise ValueError('Fresh staged output required.')
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)

def install_lame(root):
    root=Path(root);verify_sources(root,True);out=root/'out/lame'
    for n in ('libmp3lame.dll','libmp3lame.lib','libmp3lame-static.lib'):base.regular_file(out/'bin'/n)
    copy_regular(root/'upstream/lame-4.0/include/lame.h',out/'include/lame/lame.h')
    write(root/'LAME-INSTALLED.json',base.inventory(out))

def verify_lame_install(root):
    observed=base.inventory(root/'out/lame')
    if observed!=base.recipe_json(root/'LAME-INSTALLED.json'):
        raise ValueError('Selected LAME header/import/library output changed.')
    return observed

def stage_candidate(root):
    root=Path(root);verify_sources(root,True);verify_lame_install(root);candidate=root/'candidate'
    if candidate.exists():raise ValueError('Candidate staging must be fresh.')
    prefix=root/'out/ffmpeg-vs-64/bin';base.no_links(prefix);actual={x.name for x in prefix.iterdir() if x.suffix.lower() in {'.exe','.dll'}}
    if actual!=set(FF_DLLS)|{'ffmpeg.exe'}:raise ValueError('Unexpected installed executable/DLL closure.')
    candidate.mkdir()
    for n in (*FF_DLLS,'ffmpeg.exe'):copy_regular(prefix/n,candidate/n)
    copy_regular(root/'out/lame/bin/libmp3lame.dll',candidate/'libmp3lame.dll')
    copy_regular(ROOT/MP3_GRANT,candidate/'notices/project/MP3-BUILD-RECIPES-LICENSE.txt')

def tone(frequency,rate=44100):
    count=52920
    return b''.join(struct.pack('<h',round(12000*math.sin(2*math.pi*frequency*i/rate)*min(1,i/441,(count-i-1)/441))) for i in range(count))

def check_tone(raw,frequency):
    if len(raw)%2 or not 44100<=len(raw)//2<=61740:raise ValueError('Decoded duration outside authored delay tolerance.')
    samples=struct.unpack('<'+'h'*(len(raw)//2),raw);rms=math.sqrt(sum(v*v for v in samples)/len(samples))
    def energy(hz):
        a=sum(v*math.cos(2*math.pi*hz*i/44100) for i,v in enumerate(samples))
        b=sum(v*math.sin(2*math.pi*hz*i/44100) for i,v in enumerate(samples))
        return a*a+b*b
    if rms<500 or energy(frequency)<16*energy(880 if frequency==440 else 440):
        raise ValueError('Wrong authored signal or silent output.')

def bounded_media_bytes(path):
    info=base.regular_file(path)
    if info.st_nlink!=1 or not 0<info.st_size<=262144:raise ValueError('Authored media output boundary differs.')
    with Path(path).open('rb') as stream:data=stream.read(info.st_size+1)
    if len(data)!=info.st_size:raise ValueError('Authored media output changed while reading.')
    return data

def publish_encoded(run,decode,previous,frequency):
    """Only validated actual MPEG output can replace the previous owned result."""
    previous=Path(previous);base.no_links(previous.parent)
    prior=base.no_links(previous)
    if prior is not None and not stat.S_ISREG(prior.st_mode):raise ValueError('Previous owned output is not a regular file.')
    with retained_probe_work(previous.parent) as work:
        pending=work/'voice.mp3';run(pending)
        base.regular_file(pending)
        b=bounded_media_bytes(pending)
        if len(b)<100 or not (b.startswith(b'ID3') or b[:1]==b'\xff'):
            raise ValueError('Encoded MPEG audio container missing.')
        check_tone(decode(pending),frequency)
        pending.replace(previous)

def failure(root,phase,exit_code,log,offset):
    if phase not in PHASES or type(exit_code) is not int or exit_code==0 or not -(2**31)<=exit_code<2**32 or type(offset) is not int or offset<0:raise ValueError('Invalid fixed failure identity.')
    root=Path(root);base.no_links(root);base.regular_file(log)
    with Path(log).open('rb') as f:
        f.seek(0,2);size=f.tell()
        if offset>size:raise ValueError('Invalid log offset.')
        start=max(offset,size-base.FAILURE_LOG_LIMIT);f.seek(start);raw=f.read(size-start)
    if start>offset:raw=raw.partition(b'\n')[2]
    codes,categories=base.classify_failure(raw,phase)
    commit=os.environ.get('GITHUB_SHA','')
    report={'schema':'proxy-r19-mp3-draft-failure-v1','status':'failed','phase':phase,'exit_code':exit_code,
        'source_commit':commit if re.fullmatch('[a-f0-9]{40}',commit) else None,
        'profile_manifest':record(base.recipe_bytes(PIN)),'diagnostic_codes':codes,'diagnostic_categories':categories,
        'log_truncated':start>offset,'raw_log_published':False,**FLAGS}
    write(root/'FAILED-STAGE.json',report)

def preflight_failure(root,observed):
    # Reuse the exact numeric observer's validation in private storage only.
    root=Path(root);base.no_links(root)
    if root.exists():raise ValueError('Fresh failure output required.')
    with tempfile.TemporaryDirectory(prefix='mp3-preflight-',dir=root.parent) as name:
        hidden=Path(name)/'private-observation'
        report=base.preflight_failure(hidden,observed)
    report.update(schema='proxy-r19-mp3-draft-preflight-failure-v1',source_commit=None,draft_base_commit='0f9353137bdc8c57adbe275b4d245a6a1f136796',input_manifest={'path':str(PIN.relative_to(ROOT)),**record(base.recipe_bytes(PIN))},**FLAGS)
    root.mkdir();write(root/'FAILED-STAGE.json',report)

# Fixed owned CLI operation; this is not a general process/codec interface.
class CliRefused(ValueError):
    pass

class CliOwnershipUnconfirmed(OSError):
    def __init__(self, retained):
        super().__init__('Owned CLI cleanup is unconfirmed; ownership remains retained.')
        self.retained=retained

RETAINED_CLI_OWNERS=[]

def owned_primitive():
    name='backend/windows_preparation_process.py';raw=base.recipe_bytes(ROOT/name)
    expected=policy()['cli_child']['owned_primitive']['canonical_lf_sha256']
    normalized=raw.replace(b'\r\n',b'\n')
    if b'\r' in normalized or sha(normalized)!=expected:raise CliRefused('Exact owned creation primitive differs.')
    spec=importlib.util.spec_from_file_location('mp3_owned_creation',ROOT/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class ProgressFrames:
    KEYS=('bitrate','total_size','out_time_us','out_time_ms','out_time','dup_frames','drop_frames','speed','progress')
    def __init__(self):self.data=b'';self.partial=b'';self.fields=[];self.frames=0;self.ready=False;self.ended=False
    def feed(self,data):
        if type(data) is not bytes or len(self.data)+len(data)>32768:raise CliRefused('Progress byte cap exceeded.')
        self.data+=data;self.partial+=data
        while b'\n' in self.partial:
            raw,self.partial=self.partial.split(b'\n',1)
            if raw.endswith(b'\r'):raw=raw[:-1]
            if not raw or len(raw)>128:raise CliRefused('Malformed bounded progress line.')
            try:key,value=raw.decode('ascii').split('=',1)
            except (UnicodeError,ValueError):raise CliRefused('Malformed progress frame.') from None
            if self.ended or len(self.fields)>=9 or key!=self.KEYS[len(self.fields)]:raise CliRefused('Progress keys/order differ.')
            self.fields.append(value)
            if key!='progress':continue
            self.frames+=1
            if self.frames>128:raise CliRefused('Progress record cap exceeded.')
            b,size,us,ms,clock,dup,drop,speed,state=self.fields
            if not re.fullmatch(r'N/A| {0,8}[0-9]{1,7}\.[0-9]kbits/s',b):raise CliRefused('Invalid bitrate projection.')
            if size!='N/A' and not re.fullmatch(r'[0-9]{1,6}',size):raise CliRefused('Invalid output count.')
            if size!='N/A' and int(size)>262144:raise CliRefused('Output byte cap exceeded.')
            if (us,ms,clock)!=('N/A','N/A','N/A'):
                if not re.fullmatch(r'-?[0-9]{1,7}',us) or us!=ms or not re.fullmatch(r'-?[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}',clock):raise CliRefused('Invalid progress time.')
                sign=-1 if clock.startswith('-') else 1;parts=clock.lstrip('-').replace(':','.').split('.')
                hours,minutes,seconds,micros=map(int,parts)
                if minutes>=60 or seconds>=60 or sign*((hours*3600+minutes*60+seconds)*1000000+micros)!=int(us) or not -1000000<=int(us)<=2000000:raise CliRefused('Progress time correspondence differs.')
            if dup!='0' or drop!='0':raise CliRefused('Unexpected video progress in audio operation.')
            if speed!='N/A':
                if not re.fullmatch(r' {0,8}[0-9]{1,8}(?:\.[0-9]{1,8})?(?:e[+-]?[0-9]{1,2})?x',speed) or not math.isfinite(float(speed[:-1])) or float(speed[:-1])>1e9:raise CliRefused('Invalid progress speed.')
            if state not in ('continue','end'):raise CliRefused('Unknown progress terminal state.')
            if state=='end':self.ended=True
            if state=='continue' and size!='N/A' and us!='N/A' and int(size)>0 and int(us)>0:self.ready=True
            self.fields=[]
    def terminal(self):
        if not self.ended or self.partial or self.fields:raise CliRefused('Missing exact terminal progress frame.')

def split_cli_input(role,data):
    if role not in ('encode-440','decode-440','encode-880','decode-880'):raise CliRefused('Unknown fixed input role.')
    if type(data) is not bytes or not 0<len(data)<=262144:raise CliRefused('Authored input cap exceeded.')
    if role.startswith('encode-'):
        if len(data)!=105840 or len(data)%2:raise CliRefused('Exact sample-aligned authored PCM required.')
        return data[:-4608],data[-4608:]
    if not role.startswith('decode-'):raise CliRefused('Unknown fixed CLI role.')
    offset=0
    if data.startswith(b'ID3'):
        if len(data)<10 or data[5]&0x10 or any(x&0x80 for x in data[6:10]):raise CliRefused('Unsupported authored ID3 header.')
        offset=10+sum(x<<(7*(3-i)) for i,x in enumerate(data[6:10]))
    frames=[];rates=(0,32,40,48,56,64,80,96,112,128,160,192,224,256,320)
    while offset<len(data):
        if offset+4>len(data):raise CliRefused('Partial authored MP3 frame.')
        h=int.from_bytes(data[offset:offset+4],'big');version=(h>>19)&3;layer=(h>>17)&3;rate=(h>>12)&15;sample=(h>>10)&3;channels=(h>>6)&3
        if h>>21!=0x7ff or version!=3 or layer!=1 or not 1<=rate<=14 or sample!=0 or channels!=3:raise CliRefused('Only produced MPEG1 mono44100 frames are admitted.')
        length=144000*rates[rate]//44100+((h>>9)&1)
        if offset+length>len(data):raise CliRefused('Truncated authored MP3 frame.')
        frames.append(offset);offset+=length
    if len(frames)<6:raise CliRefused('Insufficient complete frames for held MP3 suffix.')
    boundary=frames[-2]
    if boundary<=0 or not data[boundary:]:raise CliRefused('Nonempty frame-aligned suffix required.')
    return data[:boundary],data[boundary:]

class NativePipe:
    def __init__(self,api):
        import uuid
        self.api=api;self.path='\\\\.\\pipe\\R19-MP3-'+uuid.uuid4().hex;self.closed=False;self.close_attempted=False
        self.handle=api.k.CreateNamedPipeW(self.path,2|0x80000,1|8,1,65536,0,0,None)
        if self.handle in (None,0,api.c.c_void_p(-1).value):raise OSError('Owned input pipe creation failed.')
    def connect(self):
        if self.api.k.ConnectNamedPipe(self.handle,None):return True
        error=self.api.c.get_last_error()
        if error==535:return True
        if error==536:return False
        raise OSError('Owned pipe connection failed.')
    def client(self):
        value=self.api.u();self.api.check(self.api.k.GetNamedPipeClientProcessId(self.handle,self.api.c.byref(value)));return value.value
    def write(self,data):
        count=self.api.u();buf=self.api.c.create_string_buffer(data)
        ok=self.api.k.WriteFile(self.handle,buf,len(data),self.api.c.byref(count),None)
        if not ok and self.api.c.get_last_error() not in (232,536):raise OSError('Owned pipe write failed.')
        if count.value>len(data):raise OSError('Owned pipe write count differs.')
        return count.value
    def close(self):
        if self.closed:return
        if self.close_attempted:raise OSError('Owned pipe close remains uncertain.')
        self.close_attempted=True
        self.api.check(self.api.k.CloseHandle(self.handle));self.closed=True

class NativeCliApi:
    def __init__(self,core):
        import ctypes
        if struct.calcsize('P')!=8:raise OSError('Exact x64 CLI observation host required.')
        self.c=ctypes;self.u=ctypes.c_uint32;self.core=core;self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        H=ctypes.c_void_p;P=ctypes.c_void_p;U=self.u;W=ctypes.c_wchar_p;B=ctypes.c_int
        signatures={'CreateNamedPipeW':([W,U,U,U,U,U,U,P],H),'ConnectNamedPipe':([H,P],B),
            'GetNamedPipeClientProcessId':([H,P],B),'GetProcessId':([H],U),'WriteFile':([H,P,U,P,P],B),
            'CloseHandle':([H],B),'GetExitCodeProcess':([H,P],B),'GetSystemDirectoryW':([W,U],U),
            'K32EnumProcessModulesEx':([H,P,U,P,U],B),'K32GetModuleFileNameExW':([H,H,W,U],U)}
        for name,(args,result) in signatures.items():getattr(self.k,name).argtypes=args;getattr(self.k,name).restype=result
    def check(self,result):
        if not result:raise OSError('Bounded CLI Win32 observation failed.')
        return result
    def limit_one(self,owner):
        limits=self.core._ExtendedLimits();limits.basic.flags=0x2000|8;limits.basic.active_process_limit=1
        self.check(owner.kernel.SetInformationJobObject(owner.handle,9,self.c.byref(limits),self.c.sizeof(limits)))
    def make_pipe(self):return NativePipe(self)
    def pid(self,child):return self.check(self.k.GetProcessId(child.process_handle))
    def live(self,owner,child):
        member=self.core.wintypes.BOOL();self.check(owner.kernel.IsProcessInJob(child.process_handle,owner.handle,self.c.byref(member)))
        state=owner.kernel.WaitForSingleObject(child.process_handle,0)
        if not member.value or state not in (0,258):raise OSError('Genuine CLI identity or liveness is unconfirmed.')
        return state==258
    def job_zero(self,owner):
        counts=self.core._Accounting();self.check(owner.kernel.QueryInformationJobObject(owner.handle,1,self.c.byref(counts),self.c.sizeof(counts),None));return counts.active_processes==0
    def exit_code(self,child):
        result=self.u();self.check(self.k.GetExitCodeProcess(child.process_handle,self.c.byref(result)));return result.value
    def system_directory(self):
        b=self.c.create_unicode_buffer(32768);n=self.k.GetSystemDirectoryW(b,len(b))
        if not 0<n<len(b):raise OSError('Authoritative Windows system directory unavailable.')
        return Path(b.value)
    def modules(self,child):
        H=self.c.c_void_p;array=(H*128)();needed=self.u();self.check(self.k.K32EnumProcessModulesEx(child.process_handle,array,self.c.sizeof(array),self.c.byref(needed),2))
        if not needed.value or needed.value%self.c.sizeof(H) or needed.value>self.c.sizeof(array):raise OSError('Bounded CLI module set is unavailable.')
        rows=[]
        for handle in array[:needed.value//self.c.sizeof(H)]:
            b=self.c.create_unicode_buffer(32768);n=self.k.K32GetModuleFileNameExW(child.process_handle,handle,b,len(b))
            if not 0<n<len(b)-1:raise OSError('CLI module path unavailable.')
            rows.append((handle,b.value))
        if len({v for v,n in rows})!=len(rows):raise OSError('Duplicate CLI module address.')
        return tuple(sorted(rows))

class CliOrigins:
    def __init__(self,candidate,expected,system,allowlist):
        self.candidate=Path(candidate);self.expected=expected;self.system=Path(system);self.allow=set(allowlist);self.files={}
    def classify(self,raw):
        path=Path(raw)
        if not path.is_absolute() or '..' in path.parts:raise CliRefused('Noncanonical loaded image refused before access.')
        if path.parent==self.candidate and path.name in self.expected:return path,('application',path.name)
        if path.parent==self.system and path.name.lower() in self.allow:return path,('windows-system-observed',path.name.lower())
        raise CliRefused('Unknown loaded origin refused before content access.')
    def project(self,rows):
        result=[];seen=set()
        for address,raw in rows:
            path,identity=self.classify(raw)
            if identity in seen:raise CliRefused('Ambiguous duplicate loaded origin.')
            seen.add(identity);named=base.regular_file(path)
            if path not in self.files:
                stream=path.open('rb');self.files[path]=stream
            stream=self.files[path];info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=64*1024*1024:raise CliRefused('Loaded image file is not bounded ordinary data.')
            identity_before=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)
            if (named.st_dev,named.st_ino)!=(info.st_dev,info.st_ino):raise CliRefused('Loaded image name no longer refers to retained data.')
            stream.seek(0);data=stream.read(info.st_size+1)
            after=os.fstat(stream.fileno())
            if len(data)!=info.st_size or identity_before!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):raise CliRefused('Loaded image changed during measurement.')
            row=record(data)
            if identity[0]=='application' and row!=self.expected[identity[1]]:raise CliRefused('Loaded app image differs from selected bytes.')
            result.append({'origin':identity[0],'file':identity[1],**row})
        if {n for role,n in seen if role=='application'}!=set(self.expected):raise CliRefused('Actual CLI app module closure incomplete.')
        return sorted(result,key=lambda r:(r['origin'],r['file']))
    def close(self):
        errors=[]
        for stream in self.files.values():
            try:stream.close()
            except BaseException:errors.append(True)
        if errors:raise OSError('Loaded-image handle close is unconfirmed.')

class PrivateProgress:
    def __init__(self,path):self.path=Path(path);self.offset=0;self.parser=ProgressFrames()
    def read(self):
        info=base.no_links(self.path)
        if info is None:return
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not self.offset<=info.st_size<=32768:raise CliRefused('Private progress file boundary differs.')
        with self.path.open('rb') as stream:
            stream.seek(self.offset);data=stream.read(info.st_size-self.offset)
        if len(data)!=info.st_size-self.offset:raise CliRefused('Progress file shrank while reading.')
        self.offset+=len(data);self.parser.feed(data)

def owned_cli_attempt(role,payload,candidate,expected,output,work,env,*,api=None,owner_factory=None,clock=time.monotonic,sleep=time.sleep,origin_factory=CliOrigins):
    if role not in ('encode-440','decode-440','encode-880','decode-880'):raise CliRefused('Unknown fixed native operation.')
    prefix,suffix=split_cli_input(role,payload)
    if not prefix or not suffix:raise CliRefused('Input suffix must remain nonempty.')
    deadline=clock()+20;owner=child=pipe=origins=None;cleanup=[];attempt=Path(tempfile.mkdtemp(prefix='cli child-',dir=work));progress=PrivateProgress(attempt/'progress.txt');answer=None
    def budget():
        if clock()>=deadline:raise CliRefused('Single CLI operation deadline exceeded.')
    def send(data):
        count=pipe.write(data)
        if type(count) is not int or not 0<=count<=len(data):raise CliRefused('Input pipe write count differs.')
        return count
    try:
        if api is None:
            if sys.platform!='win32':raise CliRefused('Owned CLI operation requires Windows.')
            core=owned_primitive();api=NativeCliApi(core);owner_factory=core.WindowsPreparationProcess
        owner=owner_factory();api.limit_one(owner);pipe=api.make_pipe()
        command=[str(Path(candidate)/'ffmpeg.exe'),'-hide_banner','-loglevel','quiet','-nostdin','-y',
            '-analyzeduration','100000','-probesize','4096','-f','s16le' if role.startswith('encode-') else 'mp3']
        if role.startswith('encode-'):command+=['-ar','44100','-ac','1']
        command+=['-i',pipe.path,'-progress',str(progress.path),'-stats_period','0.1','-flush_packets','1']
        command+=['-codec:a','libmp3lame','-q:a','2'] if role.startswith('encode-') else ['-f','s16le','-c:a','pcm_s16le','-ac','1','-ar','44100']
        command+=[str(output)]
        child=owner.create_suspended(command,cwd=work,env=env);child.resume_once();sent=0;connected=False
        while True:
            budget()
            if not api.live(owner,child):raise CliRefused('CLI exited before held-input census.')
            if not connected:
                if not pipe.connect():sleep(.01);continue
                if pipe.client()!=api.pid(child):raise CliRefused('Input pipe client is not the genuine CLI.')
                connected=True
            if sent<len(prefix):sent+=send(prefix[sent:min(sent+16384,len(prefix))])
            progress.read()
            if progress.parser.ended:raise CliRefused('CLI ended before census release.')
            if sent==len(prefix) and progress.parser.ready:break
            sleep(.01)
        origins=origin_factory(candidate,expected,api.system_directory(),policy()['cli_child']['system_module_allowlist'])
        budget();first=api.modules(child);one=origins.project(first)
        if not api.live(owner,child):raise CliRefused('CLI exited during first origin snapshot.')
        budget();second=api.modules(child);two=origins.project(second)
        if first!=second or one!=two or not api.live(owner,child):raise CliRefused('Live CLI module snapshots differ.')
        # No suffix byte or EOF is released until both genuine-child snapshots pass.
        sent=0
        while sent<len(suffix):
            budget()
            if not api.live(owner,child):raise CliRefused('CLI exited before the held suffix was delivered.')
            sent+=send(suffix[sent:min(sent+16384,len(suffix))]);progress.read()
            if progress.parser.ended:raise CliRefused('CLI ended before all held input and EOF were released.')
            sleep(.01)
        pipe.close()
        while api.live(owner,child):budget();progress.read();sleep(.01)
        budget();progress.read();progress.parser.terminal()
        if api.exit_code(child)!=0:raise CliRefused('Observed CLI conversion failed.')
        answer={'operation':role,'loaded_native':two,'scope':'two stable snapshots of this live CLI operation only'}
    except BaseException:
        # OS/primitive exceptions may contain private paths. They are not diagnostics.
        raise CliRefused('Fixed authored CLI operation refused; no passing result.') from None
    finally:
        # Every independent cleanup is attempted; uncertainty retains the same owner.
        if child is not None:
            try:child.stop_and_wait(clock()+5)
            except BaseException:cleanup.append(True)
        if owner is not None:
            try:
                if not api.job_zero(owner):cleanup.append(True)
            except BaseException:cleanup.append(True)
        for resource in (pipe,origins):
            if resource is not None:
                try:resource.close()
                except BaseException:cleanup.append(True)
        if not cleanup:
            if child is not None:
                try:child.close_after_exit()
                except BaseException:cleanup.append(True)
            if owner is not None and not cleanup:
                try:owner.close()
                except BaseException:cleanup.append(True)
        if cleanup:
            retained={'owner':owner,'child':child,'pipe':pipe,'origins':origins};RETAINED_CLI_OWNERS.append(retained)
            raise CliOwnershipUnconfirmed(retained) from None
    return answer


def hold_cli_owner_failure():
    # Entry-point failure containment only. Never converts unknown cleanup to pass.
    while True:time.sleep(1)

@contextlib.contextmanager
def retained_probe_work(root):
    work=Path(tempfile.mkdtemp(prefix='owned tones-',dir=root))
    try:yield work
    finally:
        if not RETAINED_CLI_OWNERS:shutil.rmtree(work)

def native_run(args,cwd,env):
    # Supplementary observer/fault calls retain their own Popen and files on
    # uncertainty. They supply neither a Job census nor main CLI-origin proof.
    process=out=err=None;uncertain=False
    try:
        out=tempfile.TemporaryFile();err=tempfile.TemporaryFile()
        try:process=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
        except BaseException:
            uncertain=True
            raise
        deadline=time.monotonic()+20
        while True:
            try:live=process.poll() is None
            except BaseException:
                uncertain=True  # A later successful poll cannot repair this observation.
                raise
            if not live:break
            if time.monotonic()>=deadline or os.fstat(out.fileno()).st_size>32768 or os.fstat(err.fileno()).st_size>32768:
                raise ValueError('Native probe deadline/output bound exceeded.')
            time.sleep(.05)
        if process.returncode:raise ValueError('Bounded native codec operation failed.')
        out.seek(0);err.seek(0);data=out.read(32769);error=err.read(32769)
        if len(data)>32768 or len(error)>32768:raise ValueError('Native output exceeds fixed cap.')
        return data
    except BaseException:
        raise ValueError('Fixed supplementary native operation refused.') from None
    finally:
        if process is not None:
            try:live=process.poll() is None
            except BaseException:live=True;uncertain=True
            if live:
                try:process.kill()
                except BaseException:uncertain=True
            try:process.wait(timeout=5)
            except BaseException:uncertain=True
        # Keep streams open if process cleanup is unconfirmed. If exit is
        # confirmed, attempt both independent closes even when one close fails.
        if not uncertain:
            for stream in (out,err):
                if stream is not None:
                    try:stream.close()
                    except BaseException:uncertain=True
        if uncertain:
            retained={'process':process,'stdout':out,'stderr':err,'scope':'supplementary-observer-or-fault-only'}
            RETAINED_CLI_OWNERS.append(retained)
            raise CliOwnershipUnconfirmed(retained) from None

def finish(root,cmake_root):
    try:return finish_native(root,cmake_root)
    except CliOwnershipUnconfirmed:
        # Failure publication is best effort and cannot release unknown ownership.
        try:
            report={'schema':'proxy-r19-mp3-cli-cleanup-refusal-v1','status':'failed',
                'phase':'authored-cli-ownership','category':'cleanup-unconfirmed',
                'source_commit':None,'draft_base_commit':'0f9353137bdc8c57adbe275b4d245a6a1f136796',
                'profile_manifest':record(base.recipe_bytes(PIN)),
                'project_inputs':{n:record(b) for n,b in project_bytes().items()},**FLAGS}
            write(Path(root)/'FAILED-CLI-OWNERSHIP.json',report)
        except BaseException:pass
        raise

def finish_native(root,cmake_root):
    if sys.platform!='win32':raise ValueError('Actual Windows build/probe required; draft has no native pass.')
    root=Path(root);p=verify_sources(root,True);lame_installed=verify_lame_install(root)
    tools=base.recipe_json(root/'BUILD-TOOLS.json')
    if tools!=base.recipe_json(root/'BUILD-TOOLS-AFTER.json'):raise ValueError('Selected supplier tools changed.')
    spec=importlib.util.spec_from_file_location('exact_build_cmake',ROOT/'scripts/pinned-build-cmake.py');cm=importlib.util.module_from_spec(spec);spec.loader.exec_module(cm);supplier=cm.verify(cmake_root)
    candidate=root/'candidate';before=base.inventory(candidate)
    expected=set(DLLS)|{'ffmpeg.exe','mp3-codec-origin.exe','notices/project/MP3-BUILD-RECIPES-LICENSE.txt'}|{'notices/'+n['component']+'/'+n['path'] for n in p['notices']}
    if set(before)!=expected:raise ValueError('Exact MP3 candidate set differs.')
    if before['notices/project/MP3-BUILD-RECIPES-LICENSE.txt']!={k:MP3_PROJECT_LICENSE['grant'][k] for k in ('bytes','sha256')}:raise ValueError('Candidate MP3 BSD notice differs.')
    for n in p['notices']:
        if before['notices/'+n['component']+'/'+n['path']]!={k:n[k] for k in ('bytes','sha256')}:raise ValueError('Candidate notice bytes differ.')
    env={k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP') if k in os.environ};env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    def run(args,cwd):
        return native_run(args,cwd,env)
    metadata=run([str(candidate/'mp3-codec-origin.exe')],candidate).decode().splitlines();modules={};configs=[];cli_observations=[]
    cli_expected={n:before[n] for n in (*DLLS,'ffmpeg.exe')}
    for line in metadata:
        fields=line.split('\t')
        if fields[0]=='module' and len(fields)==3:
            n,path=fields[1:];base.no_links(Path(path))
            if n not in DLLS or n in modules or Path(path).resolve()!=(candidate/n).resolve():raise ValueError('Foreign native origin.')
            modules[n]={'origin':'quarantined-candidate-observer-process',**record((candidate/n).read_bytes())}
        elif fields[0]=='configuration' and len(fields)==2:configs.append(fields[1])
    options=base.recipe_json(root/'AUDIO-OPTIONS.json')+['--target-os=win64','--toolchain=msvc','--arch=x86_64','--prefix=/c/r19-mp3-codec-replay/out/ffmpeg-vs-64']
    import shlex
    if len(configs)!=5 or any(shlex.split(x)!=options for x in configs) or set(modules)!=set(DLLS) or 'lame-version\t4.0' not in metadata or 'ffmpeg-version\t9.0.2' not in metadata or 'mp3-encoder\tlibmp3lame' not in metadata or 'license\tLGPL version 2.1 or later' not in metadata:raise ValueError('Actual codec/version/configuration differs.')
    with retained_probe_work(root) as work:
        for freq in (440,880):
            source=work/'authored tone.wav'
            with wave.open(str(source),'wb') as f:f.setparams((1,2,44100,0,'NONE','not compressed'));f.writeframes(tone(freq))
            previous=work/'complete.mp3';previous.write_bytes(b'previous-complete')
            def encode(out):
                cli_observations.append(owned_cli_attempt('encode-'+str(freq),tone(freq),candidate,cli_expected,out,work,env))
            def decode(encoded):
                out=work/'decoded.pcm'
                cli_observations.append(owned_cli_attempt('decode-'+str(freq),bounded_media_bytes(encoded),candidate,cli_expected,out,work,env))
                return bounded_media_bytes(out)
            publish_encoded(encode,decode,previous,freq);saved=previous.read_bytes()
            source.write_bytes(b'RIFFbad-owned-input')
            def damaged(out):run([str(candidate/'ffmpeg.exe'),'-hide_banner','-loglevel','quiet','-nostdin','-y','-i',str(source),'-codec:a','libmp3lame','-q:a','2',str(out)],work)
            try:publish_encoded(damaged,decode,previous,freq)
            except ValueError:pass
            else:raise ValueError('Malformed input unexpectedly published.')
            if previous.read_bytes()!=saved:raise ValueError('Failure replaced previous output.')
    if base.inventory(candidate)!=before:raise ValueError('Native probes modified candidate inputs.')
    if verify_lame_install(root)!=lame_installed:raise ValueError('Selected LAME installation changed during probes.')
    verify_sources(root,True)
    correspondence={'sources':p['sources'],'original_recipes':p['original_recipes'],'notices':p['notices'],
        'project_inputs':base.recipe_json(root/'PROJECT-INPUTS.json'),'mp3_project_license':MP3_PROJECT_LICENSE,
        'mp3_project_copies':base.recipe_json(root/'source-review/MP3-BSD-COPIES.json'),'source_review_files':base.inventory(root/'source-review'),
        'original_sources':base.recipe_json(root/'PREPARED-SOURCE.json'),'lame_working_inputs':base.recipe_json(root/'LAME-WORKING-INPUTS.json'),
        'lame_installed':base.recipe_json(root/'LAME-INSTALLED.json'),'build_tools':tools,'cmake_supplier':supplier,
        'ffmpeg_generated':base.public_generated_configuration(root),'candidate_files':before}
    report={'schema':'proxy-r19-mp3-functional-draft-native-v1','status':'quarantined-build-host-probe-passed',
        'source_commit':None,'draft_base_commit':'0f9353137bdc8c57adbe275b4d245a6a1f136796',
        'source_binding_scope':'ignored functional draft plus exact input cohort; not clean0f evidence','identity':'quarantined-mp3-'+sha(canonical(correspondence)),
        'source_correspondence':correspondence,'native_imports':{n:base.pe_imports((candidate/n).read_bytes()) for n in (*DLLS,'ffmpeg.exe','mp3-codec-origin.exe')},
        'loaded_origins':modules,'origin_scope':'supplementary observer plus four real CLI creation-handle censuses',
        'cli_child_origins':cli_observations,'cli_scope':'two stable live snapshots during each authored encode/decode only; not all possible CLI paths',
        'authored_two_tones':'actual CLI encode/decode and forbidden-other-tone check passed','malformed_input':'rejected; previous complete output preserved',
        'ordinary_voiced_mobile_export':'not-run','runtime_integration':'not-implemented','fft_provenance':'unresolved',**FLAGS}
    # New native artifacts remain private. Source kit export waits for separate review.
    write(root/'MP3-DRAFT-RECEIPT.json',report)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['acquire','prepare','install-lame','stage-candidate','finish','failure','preflight-failure']);parser.add_argument('--input-root',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--cmake-root',type=Path);parser.add_argument('--source-only',action='store_true');parser.add_argument('--phase',choices=PHASES);parser.add_argument('--exit-code',type=int);parser.add_argument('--log',type=Path);parser.add_argument('--log-offset',type=int);a=parser.parse_args()
    if a.command=='acquire':acquire(a.input_root,include_tools=not a.source_only)
    elif a.command=='prepare':prepare(a.input_root,a.output,include_tools=not a.source_only)
    elif a.command=='install-lame':install_lame(a.output)
    elif a.command=='stage-candidate':stage_candidate(a.output)
    elif a.command=='failure':failure(a.output,a.phase,a.exit_code,a.log,a.log_offset)
    elif a.command=='preflight-failure':preflight_failure(a.output,base.read_preflight_observation(sys.stdin.buffer))
    else:finish(a.output,a.cmake_root)

if __name__=='__main__':
    try:main()
    except CliOwnershipUnconfirmed:
        # No passing metadata is written; retain original creation/job objects.
        hold_cli_owner_failure()
