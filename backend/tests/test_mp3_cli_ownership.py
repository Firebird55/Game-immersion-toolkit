"""Portable source/profile and owned lifecycle fixtures; no native execution."""
import ast, copy, ctypes as c, difflib, hashlib, importlib.util, io, json, os, shutil, stat, struct, sys, tarfile, tempfile, types, unittest, xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
R=Path(__file__).resolve().parents[2];O=R
spec=importlib.util.spec_from_file_location('owned_mp3_contract',R/'scripts/replay-mp3-codec.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def frame(state='continue',us=100000,size=4096):
 clock='N/A' if us=='N/A' else ('-' if us<0 else '')+'00:00:%02d.%06d'%(abs(us)//1000000,abs(us)%1000000)
 return ('bitrate= 128.0kbits/s\ntotal_size=%s\nout_time_us=%s\nout_time_ms=%s\nout_time=%s\ndup_frames=0\ndrop_frames=0\nspeed= 1.1x\nprogress=%s\n'%(size,us,us,clock,state)).encode()

def mp3():
 # Authored MPEG1/Layer3/128k/44100/mono frame structure, NOT playable native evidence.
 header=(0xfffb90c0).to_bytes(4,'big');return (header+bytes(417-4))*8

class Clock:
 def __init__(self):self.value=0
 def __call__(self):return self.value
 def sleep(self,seconds):self.value+=max(.5,seconds)

class Rig:
 def __init__(self,root,role='encode-440',mode='good'):
  self.root=root;self.role=role;self.mode=mode;self.events=[];self.clock=Clock();self.payload=bytes(105840) if role.startswith('encode-') else mp3();self.prefix,self.suffix=m.split_cli_input(role,self.payload);self.sent=b'';self.eof=False;self.module_calls=0;self.project_calls=0;self.stopped=False;self.handle=object();self.process_handle=object();self.pipe=Pipe(self);self.child=Child(self);self.owner=Owner(self)
 def log(self,value):self.events.append(value)
 def limit_one(self,owner):
  self.log('limit-one');assert owner is self.owner
  if self.mode=='limit-fails':raise OSError('PRIVATE limit')
 def make_pipe(self):self.log('pipe-created');return self.pipe
 def pid(self,child):assert child is self.child;return 19
 def live(self,owner,child):
  assert child is self.child and owner is self.owner
  self.log('retained-live')
  if self.mode=='foreign-job':raise OSError('PRIVATE membership')
  return not self.eof and self.mode!='early-exit'
 def system_directory(self):return self.root/'system'
 def modules(self,child):
  assert child is self.child;assert not self.eof;assert len(self.sent)==len(self.prefix)
  self.module_calls+=1;self.log('snapshot-'+str(self.module_calls))
  if self.mode=='census-timeout':self.clock.value+=11
  return ((1,'selected.exe' if self.mode!='changed-modules' or self.module_calls==1 else 'changed.exe'),)
 def job_zero(self,owner):
  self.log('job-zero');assert owner is self.owner
  if self.mode=='job-query-fails':raise OSError('PRIVATE query')
  return self.mode!='job-not-zero'
 def exit_code(self,child):self.log('exit-code');return 2 if self.mode=='bad-exit' else 0
 def origins(self,*args):return Origins(self)
 def run(self):
  return m.owned_cli_attempt(self.role,self.payload,self.root/'candidate',{'ffmpeg.exe':{}},self.root/'output',self.root,{'explicit':'fixture'},api=self,owner_factory=lambda:self.owner,clock=self.clock,sleep=self.clock.sleep,origin_factory=self.origins)

class Owner:
 def __init__(self,rig):self.r=rig
 def create_suspended(self,command,*,cwd,env):
  self.r.log('create-suspended');assert self.r.events.index('limit-one')<self.r.events.index('create-suspended')
  assert env=={'explicit':'fixture'};self.r.command=command;self.r.progress=Path(command[command.index('-progress')+1]);return self.r.child
 def close(self):
  self.r.log('owner-close')
  if self.r.mode=='owner-close-fails':raise OSError('PRIVATE close')

class Child:
 def __init__(self,rig):self.r=rig
 def resume_once(self):
  self.r.log('resume-once');assert self.r.events.index('create-suspended')<self.r.events.index('resume-once')
  if self.r.mode=='resume-fails':raise OSError('PRIVATE resume')
 def stop_and_wait(self,deadline):
  self.r.log('stop-wait');self.r.stopped=True
  if self.r.mode=='stop-fails':raise OSError('PRIVATE wait')
 def close_after_exit(self):
  self.r.log('child-close');assert self.r.stopped
  if self.r.mode=='child-close-fails':raise OSError('PRIVATE child close')

class Pipe:
 path='fixed-test-pipe'
 def __init__(self,rig):self.r=rig;self.closed=False
 def connect(self):self.r.log('pipe-connect');return self.r.mode!='no-connect'
 def client(self):return 18 if self.r.mode=='wrong-client' else 19
 def write(self,data):
  if self.r.mode=='invalid-count':return len(data)+1
  if len(self.r.sent)>=len(self.r.prefix):
   assert self.r.module_calls==self.r.project_calls==2;self.r.log('suffix-written')
  self.r.sent+=data
  if len(self.r.sent)==len(self.r.prefix) and self.r.mode not in ('no-progress','zero-progress'):
   self.r.progress.write_bytes(frame('end' if self.r.mode=='early-end' else 'continue'))
  if len(self.r.sent)==len(self.r.prefix) and self.r.mode=='zero-progress':self.r.progress.write_bytes(frame(us=0,size=0))
  if len(self.r.sent)>len(self.r.prefix) and self.r.mode=='end-before-eof':self.r.progress.write_bytes(frame('end'))
  return len(data)
 def close(self):
  self.r.log('pipe-close')
  if self.r.mode=='pipe-close-fails':raise OSError('PRIVATE pipe close')
  if self.closed:return
  self.closed=True
  if self.r.stopped:return
  assert len(self.r.sent)==len(self.r.payload);assert self.r.module_calls==2
  self.r.progress.write_bytes(frame()+frame('end'));self.r.eof=True

class Origins:
 def __init__(self,rig):self.r=rig
 def project(self,rows):self.r.project_calls+=1;self.r.log('project-'+str(self.r.project_calls));return [{'origin':'application','file':rows[0][1],'bytes':1,'sha256':'0'*64}]
 def close(self):
  self.r.log('origins-close')
  if self.r.mode=='origin-close-fails':raise OSError('PRIVATE origin close')

class CliContracts(unittest.TestCase):
 def setUp(self):m.RETAINED_CLI_OWNERS.clear()
 def tearDown(self):m.RETAINED_CLI_OWNERS.clear()
 def test_real_controller_four_operations_bind_genuine_handles_before_nonempty_suffix(self):
  for role in ('encode-440','encode-880','decode-440','decode-880'):
   with self.subTest(role=role),tempfile.TemporaryDirectory() as name:
    r=Rig(Path(name).resolve(),role);d=r.run();self.assertEqual(d['operation'],role);self.assertEqual(r.sent,r.payload);self.assertTrue(r.prefix and r.suffix)
    self.assertLess(r.events.index('project-2'),r.events.index('suffix-written'));self.assertLess(r.events.index('stop-wait'),r.events.index('child-close'));self.assertLess(r.events.index('job-zero'),r.events.index('owner-close'));self.assertFalse(m.RETAINED_CLI_OWNERS)
    self.assertEqual(r.command[r.command.index('-analyzeduration')+1],'100000');self.assertEqual(r.command[r.command.index('-probesize')+1],'4096');self.assertIn('-flush_packets',r.command)
 def test_controller_refuses_before_suffix_and_still_cleans_same_owner(self):
  for mode in ('limit-fails','resume-fails','wrong-client','early-exit','foreign-job','no-connect','no-progress','zero-progress','early-end','invalid-count','changed-modules','census-timeout','end-before-eof','bad-exit'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as name:
    r=Rig(Path(name).resolve(),mode=mode)
    with self.assertRaises((ValueError,OSError)) as error:r.run()
    self.assertNotIn('PRIVATE',str(error.exception));self.assertIn('job-zero',r.events);self.assertIn('owner-close',r.events)
    if mode not in ('end-before-eof','bad-exit'):self.assertNotIn('suffix-written',r.events)
    self.assertFalse(m.RETAINED_CLI_OWNERS)
    if mode in ('no-connect','no-progress','zero-progress','census-timeout'):self.assertGreaterEqual(r.clock.value,20)
 def test_uncertain_cleanup_is_sticky_keeps_exact_objects_and_attempts_independent_resources(self):
  for mode in ('stop-fails','job-query-fails','job-not-zero','pipe-close-fails','origin-close-fails','child-close-fails','owner-close-fails'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as name:
    r=Rig(Path(name).resolve(),mode=mode)
    with self.assertRaises(m.CliOwnershipUnconfirmed) as error:r.run()
    self.assertNotIn('PRIVATE',str(error.exception));held=error.exception.retained;self.assertIs(held['owner'],r.owner);self.assertIs(held['child'],r.child);self.assertIs(held['pipe'],r.pipe);self.assertEqual(len(m.RETAINED_CLI_OWNERS),1)
    for event in ('stop-wait','job-zero','pipe-close','origins-close'):self.assertIn(event,r.events)
    if mode not in ('child-close-fails','owner-close-fails'):self.assertNotIn('child-close',r.events)
    if mode!='owner-close-fails':self.assertNotIn('owner-close',r.events)
    m.RETAINED_CLI_OWNERS.clear()
 def test_unknown_cleanup_keeps_work_tree_and_previous_complete_publication(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();old=root/'voice.mp3';old.write_bytes(b'previous')
   def run(p):
    p.write_bytes(b'ID3'+bytes(200));r=Rig(p.parent,mode='stop-fails');r.run()
   with patch.object(m.shutil,'rmtree',side_effect=AssertionError('Unconfirmed ownership must retain tree')),self.assertRaises(m.CliOwnershipUnconfirmed):m.publish_encoded(run,lambda p:b'',old,440)
   self.assertEqual(old.read_bytes(),b'previous');self.assertTrue(any(root.glob('owned tones-*')))
 def test_cleanup_metadata_is_fixed_and_publication_failure_does_not_release_owner(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();error=m.CliOwnershipUnconfirmed({'PRIVATE-path':'secret'})
   with patch.object(m,'finish_native',side_effect=error),self.assertRaises(m.CliOwnershipUnconfirmed):m.finish(root,root)
   d=json.loads((root/'FAILED-CLI-OWNERSHIP.json').read_bytes());self.assertEqual(d['category'],'cleanup-unconfirmed');self.assertIsNone(d['source_commit']);self.assertNotIn('PRIVATE',json.dumps(d));self.assertIs(d['r19_complete'],False)
   with patch.object(m,'finish_native',side_effect=error),patch.object(m,'write',side_effect=OSError('PRIVATE-write')),self.assertRaises(m.CliOwnershipUnconfirmed) as caught:m.finish(root,root)
   self.assertIs(caught.exception,error);self.assertFalse((root/'MP3-DRAFT-RECEIPT.json').exists())
 def test_progress_matches_pinned_audio_formatter_requires_positive_complete_and_terminal(self):
  p=m.ProgressFrames();p.feed(frame(us=0,size=0));self.assertFalse(p.ready);p.feed(frame(us='N/A',size='N/A'));self.assertFalse(p.ready)
  for part in (frame()[:5],frame()[5:]):p.feed(part)
  self.assertTrue(p.ready);self.assertFalse(p.ended)
  with self.assertRaises(ValueError):p.terminal()
  p.feed(frame('end').replace(b'\n',b'\r\n'));p.terminal()
  with self.assertRaises(ValueError):p.feed(frame())
 def test_progress_refuses_unknown_duplicate_partial_bytes_records_and_inconsistent_time(self):
  mutations=(frame().replace(b'bitrate=',b'PRIVATE='),frame().replace(b'out_time_ms=100000',b'out_time_ms=100001'),frame().replace(b'00:00:00.100000',b'00:00:00.100001'),frame().replace(b'dup_frames=0',b'dup_frames=1'),frame().replace(b'speed= 1.1x',b'speed=NaNx'),frame().replace(b'progress=continue',b'progress=PRIVATE'),frame().replace(b'\n',b'\0\n',1),frame()+b'bitrate=1\nbitrate=2\n',b'A'*32769,frame()*129)
  for bad in mutations:
   with self.subTest(size=len(bad)),self.assertRaises(ValueError) as error:m.ProgressFrames().feed(bad)
   self.assertNotIn('PRIVATE',str(error.exception))
  p=m.ProgressFrames();p.feed(frame('end')[:-1])
  with self.assertRaises(ValueError):p.terminal()
 def test_input_split_requires_sample_or_mpeg_frame_alignment_and_bounded_nonempty_tail(self):
  prefix,suffix=m.split_cli_input('encode-440',bytes(105840));self.assertEqual(len(suffix),4608);self.assertEqual(len(prefix)%2,len(suffix)%2)
  a,b=m.split_cli_input('decode-440',mp3());self.assertEqual((len(a),len(b)),(6*417,2*417))
  for role,data in (('arbitrary',mp3()),('encode-440',b'odd'),('decode-440',mp3()[:-1]),('decode-440',mp3()[:417*5]),('decode-440',b'ID3'+b'\0'*6+b'\x80'+mp3()),('decode-440',mp3()+b'TAG'+bytes(125)),('decode-440',bytes(262145))):
   with self.subTest(role=role,size=len(data)),self.assertRaises(ValueError):m.split_cli_input(role,data)
 def test_fixed_policy_budgets_primitive_license_and_finite_system_labels_refuse_drift(self):
  p=m.policy()
  for mutate in (lambda v:v['cli_child'].update(operation_deadline_seconds=21),lambda v:v['cli_child'].update(job_active_process_limit=True),lambda v:v['cli_child'].update(analyze_duration_us=0),lambda v:v['cli_child']['owned_primitive']['license_record'].update(bytes=0),lambda v:v['cli_child'].update(system_module_allowlist=['../private.dll']),lambda v:v['cli_child'].update(system_module_allowlist=['kernel32.dll','kernel32.dll'])):
   bad=copy.deepcopy(p);mutate(bad)
   def recipe(path):return bad if Path(path)==m.PIN else p
   with self.subTest(mutate=mutate),patch.object(m.base,'recipe_json',side_effect=recipe),patch.object(m.base,'policy',return_value=m.base.policy()),self.assertRaises(ValueError):m.policy()
 def test_duplicate_or_aliased_project_inputs_are_refused_before_any_file_read(self):
  for name in ('LICENSE','license','scripts/../LICENSE','./LICENSE','scripts\\LICENSE'):
   with self.subTest(name=name),patch.object(m,'PROJECT_INPUTS',m.PROJECT_INPUTS+(name,)),patch.object(m.base,'recipe_bytes',side_effect=AssertionError('No input read on duplicate or alias')),self.assertRaises(ValueError):m.project_bytes()
  self.assertEqual(len(m.project_names()),len(set(m.project_names())))
 def test_bounded_media_output_refuses_before_unbounded_content_read(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();p=root/'output';p.write_bytes(b'authored');self.assertEqual(m.bounded_media_bytes(p),b'authored');p.write_bytes(bytes(262145))
   with patch.object(Path,'open',side_effect=AssertionError('Oversized contents must remain unread')),self.assertRaises(ValueError):m.bounded_media_bytes(p)
 def test_origins_unknown_path_refused_before_stat_lstat_open(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();unknown=root/'private/unknown.dll';o=m.CliOrigins(root/'candidate',{},root/'system',{'kernel32.dll'})
   with patch.object(Path,'lstat',side_effect=AssertionError('Unknown metadata')),patch.object(Path,'stat',side_effect=AssertionError('Unknown stat')),patch.object(Path,'open',side_effect=AssertionError('Unknown content')),self.assertRaises(ValueError):o.project(((7,str(unknown)),))
 def test_origins_actual_owned_files_retained_and_replaced_hash_link_or_unknown_refused(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();candidate=root/'candidate';system=root/'system';candidate.mkdir();system.mkdir();app=candidate/'ffmpeg.exe';app.write_bytes(b'authored executable bytes NOT executable');dll=system/'kernel32.dll';dll.write_bytes(b'authored system-role bytes NOT executable');expected={'ffmpeg.exe':m.record(app.read_bytes())};rows=((1,str(app)),(2,str(dll)));o=m.CliOrigins(candidate,expected,system,{'kernel32.dll'})
   first=o.project(rows);self.assertEqual(first,o.project(rows));self.assertEqual({r['origin'] for r in first},{'application','windows-system-observed'})
   replacement=candidate/'new';replacement.write_bytes(app.read_bytes());replacement.replace(app)
   with self.assertRaises(ValueError):o.project(rows)
   o.close();o=m.CliOrigins(candidate,expected,system,{'kernel32.dll'});app.write_bytes(b'changed')
   with self.assertRaises(ValueError):o.project(rows)
   o.close();app.write_bytes(b'authored executable bytes NOT executable');outside=root/'outside';outside.mkdir();(outside/'kernel32.dll').write_bytes(b'private');system.rmdir() if not tuple(system.iterdir()) else None;dll.unlink();system.rmdir();system.symlink_to(outside,target_is_directory=True);linked=system/'kernel32.dll';old=Path.lstat
   def guard(path,*a,**kw):
    if path==linked:raise AssertionError('Linked descendant metadata')
    return old(path,*a,**kw)
   o=m.CliOrigins(candidate,expected,system,{'kernel32.dll'})
   with patch.object(Path,'lstat',guard),self.assertRaises(ValueError):o.project(((1,str(linked)),))
   o.close()
 def test_private_progress_rejects_parentlink_before_descendant_metadata_and_cumulative_oversize(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();outside=root/'outside';outside.mkdir();(outside/'progress').write_bytes(frame());link=root/'linked';link.symlink_to(outside,target_is_directory=True);leaf=link/'progress';old=Path.lstat
   def guard(path,*a,**kw):
    if path==leaf:raise AssertionError('Linked descendant metadata')
    return old(path,*a,**kw)
   with patch.object(Path,'lstat',guard),self.assertRaises(ValueError):m.PrivateProgress(leaf).read()
   p=root/'normal';p.write_bytes(frame());reader=m.PrivateProgress(p);reader.read();p.write_bytes(b'A'*32769)
   with self.assertRaises(ValueError):reader.read()

U=c.c_uint32

B=c.c_int32

H=c.c_void_p

class Basic(c.Structure):_fields_=[('flags',U),('active_process_limit',U)]

class Limits(c.Structure):_fields_=[('basic',Basic)]

class Counts(c.Structure):_fields_=[('active_processes',U)]

class Call:
 def __init__(self,action):self.action=action
 def __call__(self,*args):return self.action(*args)

class Kernel:
 def __init__(self):
  self.error=536;self.closed=[];self.fail_close=False;self.process=object();self.membership=True;self.wait=258;self.active=0;self.count=16;self.calls=[]
  funcs={'CreateNamedPipeW':self.create,'ConnectNamedPipe':lambda *a:0,'GetNamedPipeClientProcessId':lambda h,p:self.set(p,U,19),'GetProcessId':self.pid,'WriteFile':self.write,'CloseHandle':self.close,'GetExitCodeProcess':lambda h,p:self.set(p,U,0),'GetSystemDirectoryW':self.system,'K32EnumProcessModulesEx':self.modules,'K32GetModuleFileNameExW':self.name,'SetInformationJobObject':self.limit,'IsProcessInJob':lambda p,j,v:self.set(v,B,int(self.membership)),'WaitForSingleObject':lambda *a:self.wait,'QueryInformationJobObject':self.counts}
  for n,f in funcs.items():setattr(self,n,Call(f))
 def set(self,p,kind,v):c.cast(p,c.POINTER(kind)).contents.value=v;return 1
 def create(self,*args):self.pipeargs=args;return 99
 def write(self,h,p,n,count,event):return self.set(count,U,n)
 def pid(self,p):assert p is self.process;return 19
 def close(self,h):self.closed.append(h);return not self.fail_close
 def system(self,b,n):b.value='/authoritative/system';return len(b.value)
 def modules(self,p,array,n,need,filter):
  assert p is self.process;assert filter==2;array[0]=111;array[1]=222;return self.set(need,U,self.count)
 def name(self,p,h,b,n):assert p is self.process;b.value='/authoritative/system/kernel32.dll' if h==222 else '/candidate/ffmpeg.exe';return len(b.value)
 def limit(self,job,kind,raw,n):
  assert kind==9;value=c.cast(raw,c.POINTER(Limits)).contents;self.seen_limit=(value.basic.flags,value.basic.active_process_limit);return 1
 def counts(self,job,kind,raw,n,ret):assert kind==1;c.cast(raw,c.POINTER(Counts)).contents.active_processes=self.active;return 1

class Win32Doubles(unittest.TestCase):
 def make(self):
  k=Kernel();core=types.SimpleNamespace(_ExtendedLimits=Limits,_Accounting=Counts,wintypes=types.SimpleNamespace(BOOL=B));api=m.NativeCliApi(core);owner=types.SimpleNamespace(kernel=k,handle=999);child=types.SimpleNamespace(process_handle=k.process);return k,api,owner,child
 def setUp(self):
  self.k=Kernel();self.win=patch.object(c,'WinDLL',return_value=self.k,create=True);self.win.start();self.err=patch.object(c,'get_last_error',side_effect=lambda:self.k.error,create=True);self.err.start()
  core=types.SimpleNamespace(_ExtendedLimits=Limits,_Accounting=Counts,wintypes=types.SimpleNamespace(BOOL=B));self.api=m.NativeCliApi(core);self.owner=types.SimpleNamespace(kernel=self.k,handle=999);self.child=types.SimpleNamespace(process_handle=self.k.process)
 def tearDown(self):self.err.stop();self.win.stop()
 def test_adapter_enforces_limit_and_uses_only_genuine_process_handle(self):
  self.api.limit_one(self.owner);self.assertEqual(self.k.seen_limit,(0x2008,1));self.assertEqual(self.api.pid(self.child),19);self.assertTrue(self.api.live(self.owner,self.child));self.assertEqual(self.api.exit_code(self.child),0);self.assertTrue(self.api.job_zero(self.owner));self.assertEqual(self.api.system_directory(),Path('/authoritative/system'))
  self.assertEqual(self.api.modules(self.child),((111,'/candidate/ffmpeg.exe'),(222,'/authoritative/system/kernel32.dll')))
  self.k.wait=0;self.assertFalse(self.api.live(self.owner,self.child));self.k.membership=False
  with self.assertRaises(OSError):self.api.live(self.owner,self.child)
  for count in (0,1,1025):
   self.k.count=count
   with self.subTest(count=count),self.assertRaises(OSError):self.api.modules(self.child)
  self.k.active=1;self.assertFalse(self.api.job_zero(self.owner));self.k.wait=0xffffffff;self.k.membership=True
  with self.assertRaises(OSError):self.api.live(self.owner,self.child)
 def test_first_instance_local_nonblocking_pipe_write_binding_and_exactly_once_close(self):
  pipe=self.api.make_pipe();self.assertTrue(pipe.path.startswith('\\\\.\\pipe\\R19-MP3-'));self.assertEqual(self.k.pipeargs[1:7],(0x80002,9,1,65536,0,0));self.assertFalse(pipe.connect());self.k.error=535;self.assertTrue(pipe.connect());self.assertEqual(pipe.client(),19);self.assertEqual(pipe.write(b'authored'),8)
  pipe.close();pipe.close();self.assertEqual(self.k.closed,[99])
  pipe=self.api.make_pipe();self.k.fail_close=True
  with self.assertRaises(OSError):pipe.close()
  self.k.fail_close=False
  with self.assertRaises(OSError):pipe.close()
  self.assertEqual(self.k.closed,[99,99]);self.assertFalse(pipe.closed)
 def test_native_pipe_unknown_errors_or_overcounts_never_become_progress(self):
  pipe=self.api.make_pipe();self.k.error=5
  with self.assertRaises(OSError):pipe.connect()
  self.k.WriteFile.action=lambda h,p,n,count,event:self.k.set(count,U,n+1)
  with self.assertRaises(OSError):pipe.write(b'owned')
  self.k.WriteFile.action=lambda *a:0
  with self.assertRaises(OSError):pipe.write(b'owned')
  self.k.error=232;self.assertEqual(pipe.write(b'owned'),0);pipe.close()
 def test_exact_dependency_source_is_unchanged_but_new_ordinary_license_input(self):
  raw=(O/'backend/windows_preparation_process.py').read_bytes();self.assertEqual(m.record(raw.replace(b'\r\n',b'\n')),{'bytes':25651,'sha256':'24a6995cc1d4d9260a9afe3049fbdf5d927cfddcfd405095ebcd49674e7234d0'});self.assertEqual(m.record(raw.replace(b'\r\n',b'\n'))['sha256'],m.policy()['cli_child']['owned_primitive']['canonical_lf_sha256']);core=m.owned_primitive();self.assertTrue(callable(core.WindowsPreparationProcess));self.assertEqual(m.license_boundary()['ordinary_dependency_inputs'],['backend/windows_preparation_process.py']);self.assertEqual(len(m.project_names()),17);self.assertEqual(m.project_names().count('LICENSE'),1);self.assertEqual(len(m.source_kit_names(m.policy())),26)

def load(path):
 spec=importlib.util.spec_from_file_location('mp3_bootstrap_owned',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class Bootstrap(unittest.TestCase):
 def test_first_helper_read_refuses_leaf_symlink_without_target_content_access(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();(root/'scripts').mkdir();driver=root/'scripts/replay-mp3-codec.py';driver.write_bytes((O/'scripts/replay-mp3-codec.py').read_bytes());target=root/'owned-private';target.write_bytes(b'PRIVATE authored fixture');helper=root/'scripts/replay-game-codec.py';helper.symlink_to(target);read=Path.read_bytes;op=Path.open
   def checked_read(path,*a,**kw):
    if path in (helper,target):raise AssertionError('Linked helper contents read')
    return read(path,*a,**kw)
   def checked_open(path,*a,**kw):
    if path in (helper,target):raise AssertionError('Linked helper opened')
    return op(path,*a,**kw)
   with patch.object(Path,'read_bytes',checked_read),patch.object(Path,'open',checked_open),self.assertRaises(ValueError):load(driver)
 def test_import_guard_rejects_linked_ancestor_before_helper_descendant_metadata(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();outside=root/'owned-outside';outside.mkdir();(outside/'replay-mp3-codec.py').write_bytes((O/'scripts/replay-mp3-codec.py').read_bytes());(outside/'replay-game-codec.py').write_bytes(b'PRIVATE authored helper');scripts=root/'scripts';scripts.symlink_to(outside,target_is_directory=True);helper=scripts/'replay-game-codec.py';ls=Path.lstat;st=Path.stat;op=Path.open
   def checked_lstat(path,*a,**kw):
    if path==helper:raise AssertionError('Helper descendant metadata traversed link')
    return ls(path,*a,**kw)
   def checked_stat(path,*a,**kw):
    if path==helper:raise AssertionError('Helper descendant stat traversed link')
    return st(path,*a,**kw)
   def checked_open(path,*a,**kw):
    if path==helper:raise AssertionError('Helper descendant content traversed link')
    return op(path,*a,**kw)
   with patch.object(Path,'lstat',checked_lstat),patch.object(Path,'stat',checked_stat),patch.object(Path,'open',checked_open),self.assertRaises(ValueError):load(scripts/'replay-mp3-codec.py')
 def test_simulated_windows_reparse_or_nonregular_helper_fails_before_read(self):
  for kind in ('parent-reparse','leaf-reparse','leaf-directory','leaf-fifo','leaf-oversized'):
   with self.subTest(kind=kind),tempfile.TemporaryDirectory() as name:
    root=Path(name).resolve();(root/'scripts').mkdir();driver=root/'scripts/replay-mp3-codec.py';driver.write_bytes((O/'scripts/replay-mp3-codec.py').read_bytes());helper=root/'scripts/replay-game-codec.py';helper.write_bytes(b'PRIVATE owned helper');ls=Path.lstat;op=Path.open;read=Path.read_bytes
    def checked_lstat(path,*a,**kw):
     if path==helper and kind=='parent-reparse':raise AssertionError('Reparse descendant metadata')
     if path==(helper.parent if kind=='parent-reparse' else helper):return types.SimpleNamespace(st_mode=stat.S_IFDIR if kind in ('parent-reparse','leaf-directory') else stat.S_IFIFO if kind=='leaf-fifo' else stat.S_IFREG,st_file_attributes=0x400 if 'reparse' in kind else 0,st_size=2*1024*1024+1 if kind=='leaf-oversized' else 0)
     return ls(path,*a,**kw)
    def checked_open(path,*a,**kw):
     if path==helper:raise AssertionError('Untrusted helper content opened')
     return op(path,*a,**kw)
    def checked_read(path,*a,**kw):
     if path==helper:raise AssertionError('Untrusted helper content read')
     return read(path,*a,**kw)
    with patch.object(Path,'lstat',checked_lstat),patch.object(Path,'open',checked_open),patch.object(Path,'read_bytes',checked_read),self.assertRaises(ValueError):load(driver)

class Process:
 returncode=None
 def __init__(self,fail):self.fail=fail;self.polls=0;self.kills=0;self.waits=0
 def poll(self):
  self.polls+=1
  if 'poll' in self.fail:raise OSError('PRIVATE poll')
  return self.returncode
 def kill(self):
  self.kills+=1
  if 'kill' in self.fail:raise OSError('PRIVATE kill')
  self.returncode=1
 def wait(self,timeout):
  self.waits+=1
  if 'wait' in self.fail:raise OSError('PRIVATE wait')
  return self.returncode

class Supplementary(unittest.TestCase):
 def setUp(self):m.RETAINED_CLI_OWNERS.clear()
 def tearDown(self):
  for held in m.RETAINED_CLI_OWNERS:
   for n in ('stdout','stderr'):
    if held.get(n) is not None:
     try:held[n].close()
     except OSError:pass
  m.RETAINED_CLI_OWNERS.clear()
 def test_unknown_kill_wait_or_poll_keeps_same_process_open_files_and_worktree(self):
  for failures in ({'kill'},{'wait'},{'poll'},{'kill','wait','poll'}):
   with self.subTest(failures=failures),tempfile.TemporaryDirectory() as name:
    root=Path(name).resolve();p=Process(failures);created={}
    def start(*a,**kw):created.update(kw);return p
    with patch.object(m.subprocess,'Popen',side_effect=start),patch.object(m.time,'monotonic',side_effect=[0,21]),self.assertRaises(m.CliOwnershipUnconfirmed) as caught:
     with m.retained_probe_work(root) as work:m.native_run(['inert fixture; never executed'],work,{'explicit':'fixture'})
    held=caught.exception.retained;self.assertIs(held['process'],p);self.assertIs(held['stdout'],created['stdout']);self.assertIs(held['stderr'],created['stderr']);self.assertFalse(held['stdout'].closed);self.assertFalse(held['stderr'].closed);self.assertTrue(work.exists());self.assertEqual((p.kills,p.waits),(1,1));self.assertNotIn('PRIVATE',str(caught.exception))
    held['stdout'].close();held['stderr'].close();m.RETAINED_CLI_OWNERS.clear()
 def test_first_poll_exception_remains_sticky_after_later_exit_and_wait_succeed(self):
  class FirstPollFails(Process):
   def poll(self):
    self.polls+=1
    if self.polls==1:raise OSError('PRIVATE first observation')
    self.returncode=0;return 0
  with tempfile.TemporaryDirectory() as name:
   root=Path(name).resolve();process=FirstPollFails(set());streams={}
   def create(*a,**kw):streams.update(kw);return process
   with patch.object(m.subprocess,'Popen',side_effect=create),self.assertRaises(m.CliOwnershipUnconfirmed) as caught:
    with m.retained_probe_work(root) as work:m.native_run(['not executed'],work,{})
   self.assertEqual((process.polls,process.kills,process.waits),(2,0,1));held=caught.exception.retained;self.assertIs(held['process'],process);self.assertIs(held['stdout'],streams['stdout']);self.assertIs(held['stderr'],streams['stderr']);self.assertFalse(held['stdout'].closed);self.assertFalse(held['stderr'].closed);self.assertTrue(work.exists());self.assertNotIn('PRIVATE',str(caught.exception))
 def test_known_exit_closes_both_files_even_when_one_close_is_uncertain(self):
  p=Process(set());p.returncode=0;files=[];original=tempfile.TemporaryFile;closes=[]
  class File:
   def __init__(self,index):self.index=index;self.raw=original();files.append(self)
   def __getattr__(self,n):return getattr(self.raw,n)
   def close(self):
    closes.append(self.index)
    if self.index==0:raise OSError('PRIVATE close')
    self.raw.close()
  def file():return File(len(files))
  with patch.object(m.tempfile,'TemporaryFile',side_effect=file),patch.object(m.subprocess,'Popen',return_value=p),self.assertRaises(m.CliOwnershipUnconfirmed) as caught:m.native_run(['not executed'],'.',{})
  self.assertEqual(closes,[0,1]);self.assertIs(caught.exception.retained['stdout'],files[0]);self.assertIs(caught.exception.retained['stderr'],files[1]);self.assertEqual(p.waits,1);files[0].raw.close();m.RETAINED_CLI_OWNERS.clear()
 def test_creation_failure_retains_files_without_retry_or_success(self):
  with patch.object(m.subprocess,'Popen',side_effect=OSError('PRIVATE argv/path')) as start,self.assertRaises(m.CliOwnershipUnconfirmed) as caught:m.native_run(['not executed'],'.',{})
  self.assertEqual(start.call_count,1);self.assertIsNone(caught.exception.retained['process']);self.assertFalse(caught.exception.retained['stdout'].closed);self.assertFalse(caught.exception.retained['stderr'].closed);self.assertNotIn('PRIVATE',str(caught.exception))

if __name__=='__main__':unittest.main()
