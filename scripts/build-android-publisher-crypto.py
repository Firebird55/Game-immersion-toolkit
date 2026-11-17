"""Build only the authenticated original ChaCha C core and owned JNI boundary.

No download, Python crypto loader, original game execution or APK construction.
The separate JCA implementation uses the Android platform, not copied libraries.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.private_data_paths import _no_links


def sha(path):
    _no_links(path)
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def script(name):
    spec = importlib.util.spec_from_file_location('crypto_' + name,ROOT / 'scripts' / (name+'.py'))
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def recipe(policy):
    files = {'elf_helper':'scripts/build-android-python-dependencies.py','builder':'scripts/build-android-publisher-crypto.py',
        'transport':'packaging/android/app/src/main/cpp/publisher_crypto.c',
        'jca':'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/PublisherCryptoOperations.java',
        'loader':'packaging/android/app/src/main/java/io/github/firebird55/gameimmersiontoolkit/PublisherCrypto.java',
        'contract':'backend/publisher_crypto.py','policy':'packaging/android/publisher-crypto-native.json'}
    return {**{name+'_sha256':sha(ROOT / path) for name,path in files.items()},
        'source_sha256':policy['source']['sha256']}


def original_notices(source, policy):
    result = {'publisher-crypto-licenses/LICENSE.rst':(source / policy['source']['license']).read_bytes()}
    for name in policy['source']['notice_sources']:
        raw = (source / name).read_bytes()
        if not raw.startswith(b'/*') or b'*/' not in raw[:16384]:
            raise ValueError('The complete original crypto source notice is absent')
        notice = raw[:raw.index(b'*/')+2] + b'\n'
        result['publisher-crypto-licenses/' + Path(name).name + '.notice'] = notice
    return result


def build(work, archive, ndk, ndk_archive):
    work,archive,ndk,ndk_archive = (Path(path).absolute() for path in (work,archive,ndk,ndk_archive))
    for path in (work,archive,ndk,ndk_archive):_no_links(path)
    policy = json.loads((ROOT / 'packaging/android/publisher-crypto-native.json').read_text())
    if (policy.get('schema') != 'toolkit-android-publisher-crypto-recipe-v1'
            or policy.get('contract') != 'toolkit-publisher-crypto-v1'
            or policy.get('chacha_key_bytes') != 32 or policy.get('chacha_nonce_bytes') != 12
            or policy.get('api') != 24 or policy.get('max_bytes') != 64*1024**2
            or policy.get('abis') != {'arm64-v8a':'aarch64-linux-android','x86_64':'x86_64-linux-android'}
            or any(policy.get(key) is not False for key in ('original_client_execution','cpython','gmp','cffi','account_keys_reused'))):
        raise ValueError('Review the narrow publisher cryptography recipe before building')
    source_helper = script('build-android-data-decoders')
    source = source_helper.source_tree(archive,work / 'source',policy['source'])
    for name,digest in policy['source']['members'].items():
        if sha(source / name) != digest:raise ValueError('An original crypto source member changed')
    inputs = script('build-android-python-dependencies');pins = json.loads(inputs.POLICY.read_text())
    if policy['ndk'] != pins['ndk_revision']:raise ValueError('Use the authenticated existing Android compiler')
    inventory = inputs.verify_ndk(ndk,ndk_archive,pins['ndk'])
    host = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    compiler = ndk / 'toolchains/llvm/prebuilt' / host / 'bin' / ('clang.exe' if os.name == 'nt' else 'clang')
    readelf = compiler.with_name('llvm-readelf.exe' if os.name == 'nt' else 'llvm-readelf')
    transport = ROOT / 'packaging/android/app/src/main/cpp/publisher_crypto.c'
    identity = recipe(policy);libraries = {}
    audit = script('verify-android-apk')
    for abi,target in policy['abis'].items():
        output = work / 'jniLibs' / abi / policy['library'];_no_links(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        command = [str(compiler),'-target',target+str(policy['api']),'-std=c99','-O2','-fPIC','-shared',
            '-fvisibility=hidden','-fno-ident','-Werror','-Wall','-Wextra',
            '-Wl,--as-needed','-Wl,-z,defs','-Wl,-z,max-page-size=16384','-Wl,-z,common-page-size=16384',
            '-Wl,-soname,'+policy['library'],'-ffile-prefix-map='+str(source)+'=/publisher-crypto-source',
            '-ffile-prefix-map='+str(ROOT)+'=/toolkit-source','-I'+str(source / 'src'),
            *['-D'+value for value in policy['source']['definitions']],str(transport),'-o',str(output)]
        subprocess.run(command,cwd=work,check=True,timeout=120)
        raw = output.read_bytes();elf = audit.native(raw,abi)
        parsed = inputs.elf_contract(raw,pins['targets'][abi]['elf_machine'],expected_dependencies=('libc.so',))
        dynamic = subprocess.run([str(readelf),'-d',str(output)],check=True,capture_output=True,text=True).stdout
        needed = re.findall(r'\(NEEDED\).*?\[(.*?)\]',dynamic)
        if needed != parsed['needed']:raise ValueError('Publisher crypto linked an unreviewed native dependency')
        symbols = subprocess.run([str(readelf),'--dyn-syms',str(output)],check=True,capture_output=True,text=True).stdout
        exports = {line.split()[-1] for line in symbols.splitlines() if re.search(r'\bGLOBAL\s+DEFAULT\b',line) and ' UND ' not in line}
        expected = {'toolkit_publisher_chacha20',
            'Java_io_github_firebird55_gameimmersiontoolkit_PublisherCrypto_nativeProof',
            'Java_io_github_firebird55_gameimmersiontoolkit_PublisherCrypto_nativeChaCha20'}
        if exports != expected:raise ValueError('The native cipher exposes an unexpected API')
        libraries[abi] = {**elf,'bytes':len(raw),'needed':needed,'exports':sorted(exports),
            'entry':'lib/'+abi+'/'+policy['library']}
    notices = original_notices(source,policy);licenses = {}
    for name,raw in notices.items():
        target = work / 'assets' / name;_no_links(target);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        licenses[name] = {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    source_helper.source_tree(archive,work / 'source',policy['source'])
    if recipe(policy) != identity:raise ValueError('The publisher crypto recipe changed during compilation')
    manifest = {'schema':'toolkit-android-publisher-crypto-bundle-v1','contract':policy['contract'],
        'source':policy['source']['source'],'source_sha256':policy['source']['sha256'],'version':policy['source']['version'],
        'recipe':identity,'source_members':policy['source']['members'],'ndk':policy['ndk'],'api':policy['api'],
        'ndk_archive_sha256':pins['ndk']['sha256'],'ndk_inventory_sha256':inventory,'compiler_sha256':sha(compiler),
        'library':policy['library'],'libraries':libraries,'licenses':licenses,
        'platform_primitives':'JCA','original_client_execution':False,'account_keys_reused':False,
        'target_runtime_acceptance':'not-established-by-compilation','apk_zip_alignment':'not-established-without-apk'}
    (work / 'assets/publisher-crypto-manifest.json').write_bytes(canonical(manifest))
    verify_bundle(work)
    return manifest


def verify_bundle(work):
    work = Path(work).absolute();_no_links(work)
    policy = json.loads((ROOT / 'packaging/android/publisher-crypto-native.json').read_text())
    path = work / 'assets/publisher-crypto-manifest.json';_no_links(path)
    if path.stat().st_size > 65536:raise ValueError('Publisher crypto manifest exceeds its bound')
    value = json.loads(path.read_text())
    inputs = script('build-android-python-dependencies');pins = json.loads(inputs.POLICY.read_text())
    if (value.get('schema') != 'toolkit-android-publisher-crypto-bundle-v1' or value.get('contract') != policy['contract']
            or value.get('recipe') != recipe(policy) or value.get('source_members') != policy['source']['members']
            or value.get('source_sha256') != policy['source']['sha256'] or value.get('version') != policy['source']['version']
            or value.get('library') != policy['library'] or value.get('platform_primitives') != 'JCA'
            or value.get('source') != policy['source']['source'] or value.get('ndk') != policy['ndk']
            or value.get('api') != policy['api'] or value.get('ndk_archive_sha256') != pins['ndk']['sha256']
            or any(not isinstance(value.get(name),str) or not re.fullmatch('[0-9a-f]{64}',value[name])
                for name in ('compiler_sha256','ndk_inventory_sha256'))
            or value.get('original_client_execution') is not False or value.get('account_keys_reused') is not False
            or set(value.get('libraries',{})) != set(policy['abis'])):
        raise ValueError('The publisher crypto bundle differs from its reviewed recipe')
    audit = script('verify-android-apk')
    expected = {'assets/publisher-crypto-manifest.json'}
    for abi,row in value['libraries'].items():
        path = work / 'jniLibs' / abi / policy['library'];_no_links(path)
        if (not 1 <= row['bytes'] <= 1024**2 or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']
                or audit.native(path.read_bytes(),abi)['minimum_load_alignment'] < 16384
                or row['entry'] != 'lib/'+abi+'/'+policy['library'] or set(row['needed']) != {'libc.so'}):
            raise ValueError('A publisher crypto native ABI changed')
        parsed = inputs.elf_contract(path.read_bytes(),pins['targets'][abi]['elf_machine'],expected_dependencies=('libc.so',))
        if parsed['needed'] != row['needed']:raise ValueError('The actual native crypto dependency list changed')
        expected.add(path.relative_to(work).as_posix())
    notice_names = {'publisher-crypto-licenses/LICENSE.rst',
        *('publisher-crypto-licenses/'+Path(name).name+'.notice' for name in policy['source']['notice_sources'])}
    if set(value.get('licenses',{})) != notice_names:raise ValueError('Original publisher crypto notices are incomplete')
    for name,row in value['licenses'].items():
        path = work / 'assets' / name;_no_links(path)
        if not 1 <= row['bytes'] <= 16384 or path.stat().st_size != row['bytes'] or sha(path) != row['sha256']:
            raise ValueError('An original crypto notice changed')
        expected.add(path.relative_to(work).as_posix())
    actual = set()
    for root in ('assets','jniLibs'):
        for path in (work / root).rglob('*'):
            _no_links(path)
            if path.is_file():actual.add(path.relative_to(work).as_posix())
    if actual != expected:raise ValueError('The native crypto software namespace is not closed')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--verify-only',action='store_true')
    for name in ('source-archive','ndk-root','ndk-archive'):parser.add_argument('--'+name,type=Path)
    args = parser.parse_args()
    if args.verify_only:result = verify_bundle(args.work_dir)
    elif all((args.source_archive,args.ndk_root,args.ndk_archive)):
        result = build(args.work_dir,args.source_archive,args.ndk_root,args.ndk_archive)
    else:parser.error('Supply all original software inputs or --verify-only')
    print(json.dumps({'schema':result['schema'],'libraries':result['libraries'],
        'target_runtime_acceptance':result['target_runtime_acceptance']}))
