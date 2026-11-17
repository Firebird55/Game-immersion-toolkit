"""Prepare tiny authored C API and ART/JCA probes; no APK or game inputs.

Device execution is a separate explicitly authorized step. Fresh authored RSA
numbers occur only in private fixture files, never in source or public output.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.private_data_paths import _no_links
from backend.publisher_crypto import CHACHA_LIMIT,DesktopPublisherCrypto,RsaPrivateNumbers


def sha(path):
    _no_links(path)
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def text(value):
    raw=value.encode('ascii');return struct.pack('>H',len(raw))+raw


def binary(value):return struct.pack('>i',-1 if value is None else len(value))+(value or b'')


def authored_vectors(output):
    reference=DesktopPublisherCrypto();key=bytes(range(32));nonce=bytes(range(12));data=bytes(range(256))*3
    cases=[]
    for position in (0,1,63,64,65,2**32+17,CHACHA_LIMIT-len(data)):
        cases.append((key,nonce,data,len(data),position,reference.chacha20(key,nonce,data,position=position)))
    cases.append((key,nonce,b'',0,CHACHA_LIMIT,b''))
    for k,n,raw,claimed,position in ((bytes(31),nonce,b'x',1,0),(bytes(33),nonce,b'x',1,0),
        (key,bytes(8),b'x',1,0),(key,bytes(13),b'x',1,0),(key,nonce,b'x',1,CHACHA_LIMIT),
        (key,nonce,b'',0,CHACHA_LIMIT+1),(key,nonce,b'',0,2**53+1),(key,nonce,b'x',64*1024**2+1,0)):
        cases.append((k,n,raw,claimed,position,None))
    capi=bytearray(b'TPC1'+struct.pack('<I',len(cases)))
    for k,n,raw,claimed,position,expected in cases:
        capi+=struct.pack('<IIIQQI',len(k),len(n),len(raw),claimed,position,int(expected is not None))
        capi+=k+n+raw+(expected or b'')
    (output/'authored-capi.bin').write_bytes(capi)
    jca=[]
    def block(algorithm,mode,k,iv,raw,decrypt=True):
        value=text('block')+text(algorithm)+text(mode)+bytes([decrypt])+b''.join(binary(x) for x in (k,iv,raw))
        try:expected=reference.block_cipher(algorithm,mode,k,raw,iv=iv,decrypt=decrypt)
        except ValueError:expected=-2
        jca.append((value,expected))
    for algorithm,width in (('AES',16),('AES',24),('AES',32),('DES',8)):
        size=16 if algorithm=='AES' else 8
        for mode in ('ECB','CBC'):
            k=bytes(range(width));iv=bytes(range(size)) if mode=='CBC' else None;plain=bytes(range(size*3))
            encoded=reference.block_cipher(algorithm,mode,k,plain,iv=iv,decrypt=False)
            block(algorithm,mode,k,iv,plain,False);block(algorithm,mode,k,iv,encoded)
            block(algorithm,mode,k,iv,b'')
    for args in (('AES','CTR',bytes(32),None,bytes(16)),('DESede','ECB',bytes(24),None,bytes(16)),
        ('AES','ECB',bytes(15),None,bytes(16)),('AES','CBC',bytes(32),None,bytes(16)),
        ('DES','CBC',bytes(8),bytes(16),bytes(16)),('AES','ECB',bytes(32),bytes(16),bytes(16)),
        ('AES','ECB',bytes(32),None,bytes(15))):block(*args)
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    from Crypto.Hash import SHA256
    from Crypto.Signature import pkcs1_15
    private=RSA.generate(1024);numbers=RsaPrivateNumbers(private.n,private.e,private.d,private.p,private.q)
    unsigned=lambda v:v.to_bytes((v.bit_length()+7)//8,'big')
    encoded_numbers=[unsigned(v) for v in (numbers.n,numbers.e,numbers.d,numbers.p,numbers.q)]
    spki=private.public_key().export_key(format='DER');plain=b'Authored publisher integrity and cipher fixture'
    signature=pkcs1_15.new(private).sign(SHA256.new(plain))
    for public,raw,sig in ((spki,plain,signature),(spki,plain+b'changed',signature),(spki,plain,signature[:-1]),
        (spki,plain,b''),(b'not DER',plain,signature)):
        try:expected=bytes([reference.rsa_verify_sha256(public,raw,sig)])
        except ValueError:expected=-2
        jca.append((text('verify')+b''.join(binary(v) for v in (public,raw,sig)),expected))
    for plain_data in (plain,b''):
        encrypted=PKCS1_v1_5.new(private.public_key()).encrypt(plain_data)
        jca.append((text('decrypt')+b''.join(binary(v) for v in (*encoded_numbers,encrypted)),plain_data))
    jca.append((text('decrypt')+b''.join(binary(v) for v in (*encoded_numbers,bytes(128))),None))
    jca.append((text('decrypt')+b''.join(binary(v) for v in (*encoded_numbers,bytes(127))),-2))
    corrupt=[*encoded_numbers];corrupt[2]=unsigned(numbers.d+2)
    jca.append((text('decrypt')+b''.join(binary(v) for v in (*corrupt,bytes(128))),-2))
    batch=bytearray(b'PBJ1'+struct.pack('>I',len(jca)))
    for raw,expected in jca:
        size=-2 if expected == -2 else -1 if expected is None else len(expected)
        batch+=struct.pack('>I',len(raw))+raw+struct.pack('>i',size)+(expected if size>=0 else b'')
    (output/'authored-jca.bin').write_bytes(batch)
    return {'capi_cases':len(cases),'jca_cases':len(jca),'original_game_inputs':False,'real_account_keys':False}


def prepare(work,bundle,ndk,sdk,java):
    work,bundle,ndk,sdk,java=(Path(p).absolute() for p in (work,bundle,ndk,sdk,java))
    for path in (work,bundle,ndk,sdk,java):_no_links(path)
    spec=importlib.util.spec_from_file_location('owned_crypto_bundle',ROOT/'scripts/build-android-publisher-crypto.py')
    owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
    software=owned.verify_bundle(bundle)
    work.mkdir(parents=True,exist_ok=True);(work/'temp').mkdir(exist_ok=True)
    env=dict(os.environ,JAVA_HOME=str(java),JAVA_TOOL_OPTIONS='-Djava.io.tmpdir='+str(work/'temp'))
    source=ROOT/'packaging/android/test-support';package=ROOT/'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit'
    compiler=ndk/'toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe'
    if sha(compiler)!=software['compiler_sha256']:raise ValueError('The authored probe must use the verified crypto compiler')
    policy=json.loads((ROOT/'packaging/android/publisher-crypto-native.json').read_text())
    for abi,target in policy['abis'].items():
        out=work/abi;out.mkdir(exist_ok=True)
        subprocess.run([str(compiler),'-target',target+'24','-std=c99','-O2','-fPIE','-pie','-Werror','-Wall','-Wextra',
            '-Wl,--as-needed','-Wl,-z,defs','-Wl,-z,max-page-size=16384','-Wl,-z,common-page-size=16384',
            '-ffile-prefix-map='+str(ROOT)+'=/toolkit-source',str(source/'publisher_crypto_probe.c'),'-ldl',
            '-o',str(out/'publisher-crypto-probe')],check=True,cwd=work,timeout=60)
    classes=work/'classes';classes.mkdir(exist_ok=True)
    names=[package/'PublisherCryptoOperations.java',source/'PublisherCryptoProbe.java',source/'PublisherCryptoBatchProbe.java']
    subprocess.run([str(java/'bin/javac.exe'),'--release','17','-d',str(classes),*[str(p) for p in names]],
        check=True,env=env,capture_output=True,timeout=60)
    # Compile the real Android loader against the installed actual SDK as a
    # source/ABI check, but do not include it in the standalone ART fixture.
    loader=work/'loader-classes';loader.mkdir(exist_ok=True)
    android=sdk/'platforms/android-36/android.jar'
    subprocess.run([str(java/'bin/javac.exe'),'--release','17','-cp',str(android),'-d',str(loader),
        str(package/'PublisherCryptoOperations.java'),str(package/'PublisherCrypto.java')],
        check=True,env=env,capture_output=True,timeout=60)
    dex=work/'dex';dex.mkdir(exist_ok=True)
    d8=sdk/'build-tools/36.0.0/d8.bat'
    subprocess.run([str(d8),'--min-api','24','--lib',str(android),'--output',str(dex),
        *[str(path) for path in sorted(classes.rglob('*.class'))]],check=True,env=env,capture_output=True,timeout=60)
    vectors=authored_vectors(work)
    inputs=[*names,source/'publisher_crypto_probe.c',ROOT/'scripts/prepare-publisher-crypto-probes.py']
    files=[work/'dex/classes.dex',work/'authored-capi.bin',work/'authored-jca.bin',
        *[work/abi/'publisher-crypto-probe' for abi in policy['abis']]]
    result={'schema':'toolkit-publisher-crypto-authored-probes-v1','bundle_manifest_sha256':sha(bundle/'assets/publisher-crypto-manifest.json'),
        'source_files':{p.relative_to(ROOT).as_posix():sha(p) for p in inputs},
        'compiler_sha256':sha(compiler),'javac_sha256':sha(java/'bin/javac.exe'),
        'd8_jar_sha256':sha(sdk/'build-tools/36.0.0/lib/d8.jar'),
        'files':{p.relative_to(work).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in files},
        'vectors':vectors,'android_execution':'not-established-by-preparation','apk_or_app_data_changed':False}
    (work/'authored-probe-receipt.private.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('work-dir','bundle','ndk-root','sdk-root','java-home'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.work_dir,args.bundle,args.ndk_root,args.sdk_root,args.java_home)
    print(json.dumps({'schema':result['schema'],'vectors':result['vectors'],'files':result['files']}))
