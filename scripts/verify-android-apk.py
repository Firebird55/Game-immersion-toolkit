"""Check an actual candidate APK as data, including nested Python native modules."""
import argparse
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import re
import zipfile


def native(data, abi):
    if data[:6] != b'\x7fELF\x02\x01' or len(data) < 64:
        raise ValueError('Not an Android ELF64 library')
    machine = struct.unpack_from('<H', data, 18)[0]
    if machine != {'arm64-v8a': 183, 'x86_64': 62}[abi]:
        raise ValueError('Wrong Android ABI')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or not 0 < count <= 64 or offset + size * count > len(data):
        raise ValueError('Invalid ELF program headers')
    loads = [struct.unpack_from('<Q', data, offset + size * i + 48)[0] for i in range(count)
             if struct.unpack_from('<I', data, offset + size * i)[0] == 1]
    if not loads or min(loads) < 16384:
        raise ValueError('The native library does not support 16-KiB pages')
    return {'machine': machine, 'minimum_load_alignment': min(loads), 'sha256': hashlib.sha256(data).hexdigest()}


def verify_bootstrap_native(archive):
    result = {}
    prefix = 'assets/chaquopy/bootstrap-native/'
    for name in archive.namelist():
        if name.startswith(prefix) and name.endswith('.so'):
            parts = name.removeprefix(prefix).split('/')
            if (parts[0] not in {'arm64-v8a','x86_64'}
                    or not (len(parts)==2 or parts[1:]==['java','chaquopy.so'])):
                raise ValueError('Unexpected Android bootstrap-native namespace')
            result[name] = native(archive.read(name),parts[0])
    for abi in ('arm64-v8a','x86_64'):
        if prefix+abi+'/mmap.cpython-312.so' not in result:
            raise ValueError('The actual mmap Android bootstrap extension is required')
    return result


def verify_native_inventory(archive):
    """Cover the actual Android software containers, including CPython stdlib.

    No game archives belong here. New embedding/package namespaces require a
    reviewed policy change instead of silently hiding an uninspected library.
    """
    abis={'arm64-v8a','x86_64'}
    if len(archive.namelist())!=len(set(archive.namelist())):
        raise ValueError('Duplicate native/software container member')
    pure={'app','bootstrap','requirements-common','stdlib-common'}
    containers={'assets/chaquopy/'+name+'.imy':(None,'pure') for name in pure}
    containers.update({'assets/chaquopy/'+kind+'-'+abi+'.imy':(abi,kind)
        for abi in abis for kind in ('requirements','stdlib')})
    actual={name for name in archive.namelist() if name.endswith('.imy')}
    if actual!=set(containers):raise ValueError('Unexpected or missing Android software container')
    result=verify_bootstrap_native(archive)
    summary={'apk-native':{'kind':'directory','native_count':0},
        'assets/chaquopy/bootstrap-native':{'kind':'directory','native_count':len(result)}}
    root_abis=set()
    for name in archive.namelist():
        if not name.endswith('.so') or name in result:continue
        parts=name.split('/')
        if len(parts)!=3 or parts[0]!='lib' or parts[1] not in abis or not re.fullmatch(r'lib[a-zA-Z0-9_+.-]+\.so',parts[2]):
            raise ValueError('Unexpected native library outside reviewed Android software namespaces')
        info=archive.getinfo(name)
        if not 64<=info.file_size<=128*1024**2:raise ValueError('Native library exceeds its software bound')
        result[name]=native(archive.read(name),parts[1]);root_abis.add(parts[1])
        summary['apk-native']['native_count']+=1
    if root_abis!=abis:raise ValueError('Both native APK ABI directories are required')
    for container,(abi,kind) in sorted(containers.items()):
        info=archive.getinfo(container)
        if info.file_size>128*1024**2:raise ValueError('Android software container exceeds its bound')
        count=0
        with zipfile.ZipFile(io.BytesIO(archive.read(container))) as software:
            names=software.namelist()
            if len(names)!=len(set(names)):raise ValueError('Duplicate Android software member')
            for member in names:
                if not member.endswith('.so'):continue
                if (kind=='pure' or member.startswith('/') or '\\' in member or
                        any(part in ('','..','.') for part in member.split('/'))):
                    raise ValueError('A native extension was placed in a pure or unsafe software namespace')
                if kind=='stdlib' and not re.fullmatch(r'[a-z_][a-z0-9_]*\.cpython-312\.so',member):
                    raise ValueError('Unexpected standard-library native namespace')
                if kind=='requirements' and not (member=='pydantic_core/_pydantic_core.cpython-312.so'
                        or member=='zstandard/backend_c.cpython-312.so'
                        or re.fullmatch(r'rapidfuzz/(?:distance/)?[a-zA-Z0-9_]+\.so',member)):
                    raise ValueError('Unexpected maintained dependency native namespace')
                info=software.getinfo(member)
                if not 64<=info.file_size<=128*1024**2:raise ValueError('Native extension exceeds its software bound')
                result[container+'/'+member]=native(software.read(member),abi);count+=1
            if kind=='stdlib' and not {'_ssl.cpython-312.so','_sqlite3.cpython-312.so'}<=set(names):
                raise ValueError('The actual TLS and transcript standard-library extensions are required')
        summary[container]={'kind':kind,'abi':abi,'native_count':count}
    return {'schema':'toolkit-android-native-software-inventory-v1','files':result,
        'containers':summary,'root_abis':sorted(root_abis)}


def verify_wuwa_fixture(archive, repository):
    raw=archive.read('assets/wuwa-authored-bootstrap.json')
    if not 1<=len(raw)<=65536:raise ValueError('Authored bootstrap fixture exceeds its bound')
    value=json.loads(raw)
    if value.get('schema')!='toolkit-authored-wuwa-bootstrap-v1':raise ValueError('Unknown authored bootstrap fixture')
    apk=base64.b64decode(value['apk_base64'],validate=True)
    if not 1024<=len(apk)<=32768 or len(apk)!=value['apk_bytes'] or hashlib.sha256(apk).hexdigest()!=value['apk_sha256']:
        raise ValueError('Authored bootstrap carrier changed')
    expected={'backend/tests/'+name for name in ('test_wuthering_elf_bootstrap.py','test_wuthering_native_bootstrap.py','test_publisher_apk.py')}
    if set(value['fixture_sources'])!=expected:raise ValueError('Authored fixture source inventory changed')
    for name,digest in value['fixture_sources'].items():
        if hashlib.sha256((repository/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
            raise ValueError('Authored fixture no longer matches maintained source')
    for name in ('module_sha256','default_output_sha256'):
        if not isinstance(value.get(name),str) or not re.fullmatch('[0-9a-f]{64}',value[name]):raise ValueError('Invalid authored member identity')
    if value['module_bytes']!=14336 or any(type(value[name]) is not int or not 0<=value[name]<2**64 for name in ('callback','initializer','source_address')):
        raise ValueError('Authored source-data fixture contract changed')
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'apk_sha256':value['apk_sha256'],
        'apk_bytes':len(apk),'module_bytes':value['module_bytes'],'module_sha256':value['module_sha256'],
        'original_game_bytes':False,'fixture_sources':value['fixture_sources']}


def verify_decoder(archive, native_files, repository):
    decoder = json.loads(archive.read('assets/native-decoder-manifest.json'))
    decoder_policy = json.loads((repository / 'packaging/android/native-decoders.json').read_text())
    compiler_policy = json.loads((repository / 'packaging/android/python-dependencies.json').read_text())
    recipe = {'policy_sha256': hashlib.sha256((repository / 'packaging/android/native-decoders.json').read_bytes()).hexdigest(),
        'transport_sha256': hashlib.sha256((repository / 'packaging/android/app/src/main/cpp/x64_decoder.c').read_bytes()).hexdigest(),
        'builder_sha256': hashlib.sha256((repository / 'scripts/build-android-data-decoders.py').read_bytes()).hexdigest(),
        'source_sha256': decoder_policy['capstone']['sha256'],
        'ndk_policy_sha256': hashlib.sha256(json.dumps(compiler_policy['ndk'], sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()}
    if (decoder.get('schema') != 'toolkit-android-native-decoders-v1'
            or decoder.get('source_sha256') != decoder_policy['capstone']['sha256']
            or decoder.get('version') != decoder_policy['capstone']['version']
            or decoder.get('source') != decoder_policy['capstone']['source']
            or decoder.get('ndk') != decoder_policy['ndk'] or decoder.get('api') != decoder_policy['api']
            or decoder.get('ndk_archive_sha256') != compiler_policy['ndk']['sha256']
            or not isinstance(decoder.get('ndk_inventory_sha256'), str)
            or not re.fullmatch('[0-9a-f]{64}', decoder['ndk_inventory_sha256'])
            or decoder.get('original_client_execution') is not False
            or decoder.get('recipe') != recipe
            or set(decoder.get('libraries', {})) != set(decoder_policy['abis'])):
        raise ValueError('The APK data decoder does not match its pinned owned software recipe')
    for abi, receipt in decoder['libraries'].items():
        name = 'lib/' + abi + '/' + decoder_policy['library']
        entry = archive.getinfo(name)
        if (receipt['entry'] != name or entry.file_size != receipt['bytes'] or entry.compress_type != zipfile.ZIP_STORED
                or native_files[name]['sha256'] != receipt['sha256']):
            raise ValueError('Packaged decoder bytes differ from their compiled receipt')
    expected_licenses = {'native-decoder-licenses/' + str(index) + '-' + Path(name).name
        for index, name in enumerate(decoder_policy['capstone']['licenses'])}
    if set(decoder.get('licenses', {})) != expected_licenses:
        raise ValueError('The complete decoder notices are required')
    for name, receipt in decoder['licenses'].items():
        raw = archive.read('assets/' + name)
        if len(raw) != receipt['bytes'] or hashlib.sha256(raw).hexdigest() != receipt['sha256']:
            raise ValueError('An original decoder notice is absent or changed')
    return decoder


def verify_publisher_sources(archive, core, repository):
    policy = json.loads(archive.read('assets/publisher-source-policy.json'))
    expected = json.loads((repository / 'packaging/android/publisher-sources.json').read_text())
    if policy != expected or policy.get('schema') != 'toolkit-android-publisher-sources-v1' or policy.get('source_normalization') != 'utf8-lf':
        raise ValueError('The packaged publisher policy differs from the reviewed closure')
    declared = {'backend/' + name + '.py' for provider in policy['providers'].values() for name in provider['modules']}
    declared |= {'backend/' + name + '.py' for name in policy.get('context_modules', {})}
    if declared != set(policy['files']) or not declared <= set(core['files']):
        raise ValueError('An actual publisher dependency is missing from the APK core')
    for name, receipt in policy['files'].items():
        raw = (repository / name).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(raw).hexdigest() != receipt['sha256_lf']:
            raise ValueError('A publisher source changed without a closure review')
    return policy


def verify_publisher_crypto(archive, native_files, repository):
    raw = archive.read('assets/publisher-crypto-manifest.json')
    if len(raw) > 65536:raise ValueError('Publisher crypto manifest exceeds its bound')
    value = json.loads(raw)
    spec = importlib.util.spec_from_file_location('apk_publisher_crypto', repository / 'scripts/build-android-publisher-crypto.py')
    software = importlib.util.module_from_spec(spec);spec.loader.exec_module(software)
    policy,pins = software.validate_manifest(value)
    inputs = software.script('build-android-python-dependencies')
    for abi,row in value['libraries'].items():
        name = 'lib/'+abi+'/'+policy['library'];entry = archive.getinfo(name)
        actual = archive.read(name)
        if (row.get('entry') != name or not 1 <= row['bytes'] <= 1024**2 or entry.file_size != row['bytes']
                or entry.compress_type != zipfile.ZIP_STORED or native_files[name]['sha256'] != row['sha256']
                or row.get('needed') != ['libc.so']):
            raise ValueError('The packaged publisher crypto differs from its compiled ABI receipt')
        inputs.elf_contract(actual,pins['targets'][abi]['elf_machine'],expected_dependencies=('libc.so',))
    expected = {'publisher-crypto-licenses/LICENSE.rst',
        *('publisher-crypto-licenses/'+Path(name).name+'.notice' for name in policy['source']['notice_sources'])}
    if set(value.get('licenses',{})) != expected:raise ValueError('Complete original publisher crypto notices are required')
    for name,row in value['licenses'].items():
        actual = archive.read('assets/'+name)
        if not 1 <= row['bytes'] <= 16384 or len(actual) != row['bytes'] or hashlib.sha256(actual).hexdigest() != row['sha256']:
            raise ValueError('A complete original publisher crypto notice changed')
    fixtures = {}
    for kind,count in (('capi',16),('jca',41)):
        fixture = archive.read('assets/publisher-crypto-authored-'+kind+'.bin')
        magic,endian = (b'TPC1','<') if kind == 'capi' else (b'PBJ1','>')
        if (not 8 <= len(fixture) <= 65536 or fixture[:4] != magic
                or struct.unpack_from(endian+'I',fixture,4)[0] != count):
            raise ValueError('The authored publisher crypto fixture envelope changed')
        fixtures[kind] = {'bytes':len(fixture),'sha256':hashlib.sha256(fixture).hexdigest(),'cases':count}
    return {**value,'manifest_sha256':hashlib.sha256(raw).hexdigest(),'authored_fixtures':fixtures}


def verify_publisher_hash(archive, native_files, repository):
    if not 1 <= archive.getinfo('assets/publisher-hash-manifest.json').file_size <= 65536:
        raise ValueError('Publisher hash manifest exceeds its bound')
    raw = archive.read('assets/publisher-hash-manifest.json')
    if not 1 <= len(raw) <= 65536: raise ValueError('Publisher hash manifest exceeds its bound')
    value = json.loads(raw)
    spec = importlib.util.spec_from_file_location('apk_publisher_hash', repository/'scripts/build-android-publisher-hash.py')
    software = importlib.util.module_from_spec(spec); spec.loader.exec_module(software)
    policy, pins = software.validate_manifest(value)
    inputs = software.script('build-android-python-dependencies')
    for abi, row in value['libraries'].items():
        name = 'lib/'+abi+'/'+policy['library']; entry = archive.getinfo(name)
        if not 1 <= entry.file_size <= 1024**2: raise ValueError('Publisher hash library exceeds its bound')
        actual = archive.read(name)
        if (row.get('entry') != name or not 1 <= row['bytes'] <= 1024**2 or entry.file_size != row['bytes']
                or entry.compress_type != zipfile.ZIP_STORED or native_files[name] != native(actual, abi)
                or native_files[name]['sha256'] != row['sha256'] or row.get('needed') != ['libc.so']
                or row.get('machine') != pins['targets'][abi]['elf_machine']
                or row.get('minimum_load_alignment') != native_files[name]['minimum_load_alignment']):
            raise ValueError('The packaged publisher hash differs from its compiled ABI receipt')
        inputs.elf_contract(actual, pins['targets'][abi]['elf_machine'], expected_dependencies=('libc.so',))
    expected = {'publisher-hash-licenses/xxhash-LICENSE':policy['source']['members']['deps/xxhash/LICENSE'],
        'publisher-hash-licenses/python-xxhash-LICENSE':policy['source']['members']['LICENSE']}
    expected_assets = {'assets/publisher-hash-manifest.json', 'assets/publisher-hash-authored-vectors.json',
        *('assets/'+name for name in expected)}
    if {name for name in archive.namelist() if name.startswith('assets/publisher-hash-') and not name.endswith('/')} != expected_assets:
        raise ValueError('The publisher hash APK asset namespace is not closed')
    actual_names = {name.removeprefix('assets/') for name in archive.namelist()
        if name.startswith('assets/publisher-hash-licenses/') and not name.endswith('/')}
    if set(value.get('licenses', {})) != set(expected) or actual_names != set(expected):
        raise ValueError('Complete original publisher hash notices are required')
    for name, digest in expected.items():
        if not 1 <= archive.getinfo('assets/'+name).file_size <= 16384:
            raise ValueError('Publisher hash notice exceeds its bound')
        actual = archive.read('assets/'+name); row = value['licenses'][name]
        if not 1 <= len(actual) <= 16384 or len(actual) != row['bytes'] or row['sha256'] != digest or hashlib.sha256(actual).hexdigest() != digest:
            raise ValueError('An original publisher hash notice changed')
    if not 1 <= archive.getinfo('assets/publisher-hash-authored-vectors.json').file_size <= 65536:
        raise ValueError('Publisher hash vectors exceed their bound')
    fixture = archive.read('assets/publisher-hash-authored-vectors.json')
    if not 1 <= len(fixture) <= 65536 or fixture != (repository/policy['authored_vectors']).read_bytes():
        raise ValueError('The authored publisher hash vectors changed')
    vectors = json.loads(fixture)
    if len(vectors.get('cases', [])) != 47 or vectors.get('original_game_bytes') is not False:
        raise ValueError('Review the authored publisher hash fixture contract')
    return {**value, 'manifest_sha256':hashlib.sha256(raw).hexdigest(),
        'authored_fixture':{'bytes':len(fixture), 'sha256':hashlib.sha256(fixture).hexdigest(), 'cases':47}}


def verify_genshin_profile_component(archive, repository):
    """Only authored profile input and one original software notice, no client."""
    name='assets/genshin-profile-authored.json'
    if not 1 <= archive.getinfo(name).file_size <= 65536:
        raise ValueError('Authored profile fixture exceeds its bound')
    raw=archive.read(name);value=json.loads(raw)
    if value.get('schema')!='toolkit-authored-genshin-profile-v1' or value.get('original_game_bytes') is not False:
        raise ValueError('Unsupported authored profile fixture')
    sources={'scripts/prepare-android-genshin-profile-probe.py',
        'backend/tests/test_genshin_blb_native.py','backend/tests/test_genshin_blb_portable.py',
        'backend/tests/test_genshin_original_containers.py','backend/tests/test_genshin_original_bootstrap.py'}
    if set(value.get('fixture_sources',{}))!=sources:raise ValueError('Authored profile fixture source inventory changed')
    for path,digest in value['fixture_sources'].items():
        if hashlib.sha256((repository/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:
            raise ValueError('Authored profile fixture source changed')
    executable=base64.b64decode(value['executable_base64'],validate=True)
    carrier=base64.b64decode(value['carrier_base64'],validate=True);expected=value['expected']
    if (not 512<=len(executable)<=32768 or not 84<=len(carrier)<=4096
            or hashlib.sha256(executable).hexdigest()!=expected['executable_sha256']
            or hashlib.sha256(carrier).hexdigest()!=expected['carrier_sha256']
            or len(carrier)!=expected['carrier_bytes'] or hashlib.md5(carrier).hexdigest()!=expected['carrier_md5']
            or expected['codec_candidates']!=2 or expected['accepted_candidates']!=1
            or expected['profile_count']!=1 or expected['named_objects']!=1 or expected['objects']!=2):
        raise ValueError('Authored profile fixture identities changed')
    for key in ('body_sha256','decoded_sha256','payload_sha256','parameters_sha256'):
        if not isinstance(expected.get(key),str) or not re.fullmatch('[0-9a-f]{64}',expected[key]):
            raise ValueError('Missing authored profile independent expectation')
    methods=expected.get('method_sha256s')
    if (not isinstance(methods,list) or len(methods)!=3 or methods!=sorted(set(methods))
            or any(not re.fullmatch('[0-9a-f]{64}',value) for value in methods)):
        raise ValueError('Authored native method ownership changed')
    if len(value.get('malformed',[]))!=2 or {row.get('kind') for row in value['malformed']}!={'payload-eof','complete-map'}:
        raise ValueError('Authored profile negative inventory changed')
    for row in value['malformed']:
        if not 84<=len(base64.b64decode(row['carrier_base64'],validate=True))<=4096:
            raise ValueError('Authored profile negative exceeds its bound')
    inputs=json.loads((repository/'packaging/genshin-reader/inputs.json').read_text())
    notice='assets/genshin-profile-licenses/AnimeStudio-LICENSE.txt'
    expected_assets={name,notice}
    if {path for path in archive.namelist() if path.startswith('assets/genshin-profile-') and not path.endswith('/')}!=expected_assets:
        raise ValueError('The authored profile asset namespace is not closed')
    if not 1<=archive.getinfo(notice).file_size<=16384:raise ValueError('Original profile software notice exceeds its bound')
    original=(repository/'packaging/genshin-reader/AnimeStudio-LICENSE.txt').read_bytes()
    if (inputs['license']['expression']!='MIT' or archive.read(notice)!=original
            or hashlib.sha256(original).hexdigest()!=inputs['license']['sha256']):
        raise ValueError('The complete original profile software notice changed')
    return {'schema':'toolkit-android-genshin-profile-component-v1','bytes':len(raw),
        'sha256':hashlib.sha256(raw).hexdigest(),'expected':expected,'fixture_sources':value['fixture_sources'],
        'software_notice':{'bytes':len(original),'sha256':inputs['license']['sha256'],'expression':'MIT'},
        'original_game_bytes':False,'profile_only':True,'factory_activated':False}


def verify_zstandard_package(archive, native_files, repository):
    extension_raw = archive.read('assets/python-runtime-extensions.json')
    if extension_raw != (repository / 'packaging/android/python-runtime-extensions.json').read_bytes():
        raise ValueError('The native extension policy differs from reviewed source')
    spec = importlib.util.spec_from_file_location('apk_runtime_extensions', repository / 'scripts/prepare-android-runtime-wheels.py')
    software = importlib.util.module_from_spec(spec);spec.loader.exec_module(software)
    _, pins = software.policy()
    receipt = json.loads(archive.read('assets/zstandard-build-receipt.json'))
    policy = software.validate_zstandard_receipt(receipt, pins)
    if archive.read('assets/zstandard-authored-vectors.json') != (repository / 'packaging/android/zstandard-authored-vectors.json').read_bytes():
        raise ValueError('The authored native-extension vectors changed')
    with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/requirements-common.imy'))) as common:
        for abi, row in receipt['abis'].items():
            name = 'assets/chaquopy/requirements-' + abi + '.imy/' + policy['native_member']
            if name not in native_files or native_files[name]['sha256'] != row['native_sha256']:
                raise ValueError('The actual packaged native extension differs from its compiled ABI receipt')
            for member, expected in row['notices'].items():
                raw = common.read('zstandard-0.25.0.dist-info/licenses/' + member)
                if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
                    raise ValueError('The packaged complete original extension notices changed')
    return receipt


def verify_zzz_catalogue_component(archive, repository):
    spec = importlib.util.spec_from_file_location('apk_zzz_catalogue', repository / 'scripts/android-zzz-catalogue-assets.py')
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    proof = catalogue.verify_apk(archive, repository)
    fixture = 'assets/zzz-catalogue-authored.json'
    if proof['present']:
        expected = (repository / 'packaging/android/zzz-catalogue/authored-operation.json').read_bytes().replace(b'\r\n', b'\n')
        raw = catalogue.zip_member(archive, fixture, 4096)
        if raw != expected:
            raise ValueError('The authored ZZZ catalogue fixture differs from its maintained input')
        proof['authored_fixture_sha256'] = hashlib.sha256(raw).hexdigest()
    elif fixture in archive.namelist():
        raise ValueError('The authored ZZZ catalogue fixture has no verified runtime')
    return proof


def verify_zzz_wem_component(archive, repository):
    spec = importlib.util.spec_from_file_location('apk_zzz_wem', repository / 'scripts/build-android-zzz-wem.py')
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    return decoder.verify_apk(archive)


def verify(path):
    result, abis, python_abis, rapidfuzz_abis = {}, set(), set(), {}
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None or len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError('Corrupt or duplicate APK members')
        inventory=verify_native_inventory(archive)
        result.update(inventory['files'])
        abis.update(inventory['root_abis'])
        for required in ('AndroidManifest.xml', 'classes.dex', 'assets/core-source-manifest.json', 'assets/reader.bundle'):
            if required not in archive.namelist():
                raise ValueError('Incomplete native/shared-reader APK')
        for name in archive.namelist():
            if name.startswith('assets/chaquopy/requirements-') and name.endswith('.imy'):
                abi = name.removeprefix('assets/chaquopy/requirements-').removesuffix('.imy')
                if abi not in {'arm64-v8a', 'x86_64'}:
                    continue
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as requirements:
                    for member in requirements.namelist():
                        if member.endswith('.so'):
                            if '/_pydantic_core' in member:
                                python_abis.add(abi)
                            if member.startswith('rapidfuzz/'):
                                rapidfuzz_abis.setdefault(abi, set()).add(member)
        if abis != {'arm64-v8a', 'x86_64'} or python_abis != abis:
            raise ValueError('Both full Android core ABIs are required')
        required = {'rapidfuzz/' + name + '.so' for name in ('utils_cpp', 'fuzz_cpp', 'process_cpp_impl',
            'distance/_initialize_cpp', 'distance/metrics_cpp')}
        if any(not required <= rapidfuzz_abis.get(abi, set()) for abi in abis):
            raise ValueError('Both actual native RapidFuzz ABIs are required')
        core = json.loads(archive.read('assets/core-source-manifest.json'))
        repository = Path(__file__).resolve().parents[1]
        zzz_catalogue = verify_zzz_catalogue_component(archive, repository)
        zzz_wem = verify_zzz_wem_component(archive, repository)
        decoder = verify_decoder(archive, result, repository)
        publishers = verify_publisher_sources(archive, core, repository)
        zstandard = verify_zstandard_package(archive, result, repository)
        crypto = verify_publisher_crypto(archive, result, repository)
        hashing = verify_publisher_hash(archive, result, repository)
        genshin_profile = verify_genshin_profile_component(archive,repository)
        wuwa_fixture = verify_wuwa_fixture(archive,repository)
        notices = json.loads((repository / 'packaging/android/account-python-notices.json').read_text(encoding='utf8'))
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/requirements-common.imy'))) as common:
            for package in notices['packages'].values():
                for name, digest in package['included_notices'].items():
                    if hashlib.sha256(common.read(name)).hexdigest() != digest:
                        raise ValueError('A maintained account dependency notice is absent or changed')
        for name, digest in core['files'].items():
            if not re.fullmatch(r'backend/[a-z0-9_]+\.py', name) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('Invalid owned Python source receipt')
            if hashlib.sha256((repository / name).read_bytes()).hexdigest() != digest:
                raise ValueError('The packaged source receipt differs from the current maintained core')
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/app.imy'))) as owned:
            actual_python = {name for name in owned.namelist() if not name.endswith('/')}
            if actual_python != {name + 'c' for name in core['files']}:
                raise ValueError('The delivered Python namespace differs from its closed source manifest')
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/reader.bundle'))) as reader:
            frontend = json.loads(reader.read('desktop-manifest.json'))
            actual_web = {name for name in reader.namelist() if name != 'desktop-manifest.json'}
            if len(reader.namelist()) != len(actual_web) + 1 or actual_web != set(frontend['files']):
                raise ValueError('The APK reader inventory differs from the shared frontend')
            for name, expected in frontend['files'].items():
                value = reader.read(name)
                if len(value) != expected['bytes'] or hashlib.sha256(value).hexdigest() != expected['sha256']:
                    raise ValueError('A packaged shared reader resource changed')
    return {'schema': 'toolkit-android-apk-audit-v1', 'apk_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'apk_bytes': Path(path).stat().st_size, 'abis': sorted(abis), 'native_files': result,
        'native_software_inventory':{key:value for key,value in inventory.items() if key!='files'},
        'core_sources': core, 'frontend_build_id': frontend['build_id'],
        'frontend': {'source_commit': frontend['source_commit'], 'version': frontend['version']},
        'native_data_decoder': decoder, 'native_zstandard': zstandard, 'native_publisher_crypto': crypto,
        'native_publisher_hash':hashing,
        'zzz_catalogue_component': zzz_catalogue,
        'zzz_wem_component': zzz_wem,
        'genshin_profile_component':genshin_profile,
        'publisher_source_policy': publishers,
        'wuwa_authored_fixture':wuwa_fixture,
        'target_runtime_acceptance': 'not-established-by-archive-validation', 'release_eligibility': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verify(args.apk), sort_keys=True, indent=2) + '\n', encoding='utf8')
