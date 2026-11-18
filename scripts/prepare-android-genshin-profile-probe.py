"""Generate bounded authored PE/BLB profile data, never original client inputs."""
import argparse
from collections import Counter
import base64
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.private_data_paths import _no_links

FIXTURE_SOURCES = (
    'scripts/prepare-android-genshin-profile-probe.py',
    'backend/tests/test_genshin_blb_native.py',
    'backend/tests/test_genshin_blb_portable.py',
    'backend/tests/test_genshin_original_containers.py',
    'backend/tests/test_genshin_original_bootstrap.py',
)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def executable(toy):
    """Serialize the existing authored image with actual unwind-owned ranges."""
    header = bytearray(512)
    header[:2] = b'MZ'; struct.pack_into('<I', header, 0x3c, 0x80)
    header[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', header, 0x84, 0x8664, 2)
    struct.pack_into('<H', header, 0x94, 240)
    optional = 0x98
    struct.pack_into('<H', header, optional, 0x20b)
    struct.pack_into('<Q', header, optional+24, toy.base)
    struct.pack_into('<I', header, optional+108, 16)
    exception = toy.rdata+0x1f00
    struct.pack_into('<II', header, optional+112+24, exception, len(toy.methods)*12)
    for index, (name, (rva, virtual, raw, size)) in enumerate(toy.sections.items()):
        at = optional+240+index*40
        struct.pack_into('<8sIIII', header, at, name.encode(), virtual, rva, size, raw+512)
        struct.pack_into('<I', header, at+36, 0x60000020 if name=='.text' else 0x40000040)
    data = bytearray(toy.data)
    for index, (start, code) in enumerate(sorted(toy.methods.items())):
        struct.pack_into('<III', data, toy.offset(exception)+index*12, start, start+len(code), 0)
    return bytes(header+data)


def compressed_body(raw):
    """Independent two-sequence LZ4 writer for the fixture's proved zero padding."""
    assert len(raw)>4096 and raw[511:4096]==bytes(4096-511)
    def extension(length):
        return bytes([255])*(length//255)+bytes([length%255])
    first = b'\xff'+extension(512-15)+raw[:512]+struct.pack('<H', 1)+extension(4096-512-4-15)
    tail = raw[4096:]
    return first+bytes([min(15,len(tail))<<4])+(extension(len(tail)-15) if len(tail)>=15 else b'')+tail


def carrier(raw, parameters, encode_prefix):
    packed = compressed_body(raw)
    header = bytearray(72)
    struct.pack_into('<II', header, 0, 28+len(header)+len(packed), len(raw)); header[21]=22
    struct.pack_into('<ii', header, 24, 1, 1)
    struct.pack_into('<q', header, 32, 24); struct.pack_into('<I', header, 56, len(packed))
    struct.pack_into('<q', header, 40, 24); struct.pack_into('<ii', header, 64, 0, len(raw))
    key = bytes((i*13+5)&255 for i in range(16))
    prefix = b'Blb\x03'+struct.pack('<I', len(header))+bytes(4)+key
    encode = lambda value: encode_prefix(value[:128], parameters, key, Counter())+value[128:]
    return prefix+encode(bytes(header))+encode(packed), prefix+bytes(header)+packed


def fixture():
    # Fixture construction is host-only. These test modules are never shipped.
    from backend.tests.test_genshin_blb_native import ToyImage
    from backend.tests.test_genshin_blb_portable import encode_prefix, parameters as standard_reference
    from backend.tests.test_genshin_original_containers import bundle
    from backend.tests.test_genshin_original_bootstrap import profile, contract
    from backend.genshin_blb_native import standard_tables
    toy = ToyImage(keys=(b'toy-key1', b'new-key2'))
    pe = executable(toy)
    # Independently assemble the known authored arrays, not discovered candidates.
    parameters = {**standard_reference(), **standard_tables(),
        'Blb3SBox':bytes((i*73+11)&255 for i in range(1024)),
        'Blb3ShiftRow':bytes(range(48)), 'Blb3Key':b'toy-key1',
        'Blb3Mul':b'12345678', 'Blb3RC4Key':bytes((i*5+3)&255 for i in range(256))}
    payload = json.dumps(profile(), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    body = bundle(payload=payload)
    encoded, decoded = carrier(body, parameters, encode_prefix)
    recipe = contract(); recipe['source_field']['executable_sha256']=sha(pe)
    method_sha = sorted({sha(code) for code in toy.methods.values()})
    assert len(method_sha)==3
    parameter_bytes = json.dumps({name:base64.b64encode(raw).decode() for name,raw in parameters.items()},
        sort_keys=True,separators=(',', ':')).encode()
    negative = []
    for name, broken in [('payload-eof',bundle(payload=payload+b'{}')),
                          ('complete-map',bundle(payload=payload,entries=[('12345678',1),('deadbeef',99)]))]:
        value, _ = carrier(broken, parameters, encode_prefix)
        negative.append({'kind':name,'carrier_base64':base64.b64encode(value).decode()})
    result = {'schema':'toolkit-authored-genshin-profile-v1', 'original_game_bytes':False,
        'executable_base64':base64.b64encode(pe).decode(), 'carrier_base64':base64.b64encode(encoded).decode(),
        'contract':recipe, 'malformed':negative,
        'expected':{'executable_sha256':sha(pe),'carrier_sha256':sha(encoded),'carrier_bytes':len(encoded),
            'carrier_md5':hashlib.md5(encoded).hexdigest(),'decoded_sha256':sha(decoded),'body_sha256':sha(body),
            'payload_sha256':sha(payload),'parameters_sha256':sha(parameter_bytes),
            'method_sha256s':method_sha,'codec_candidates':2,'accepted_candidates':1,
            'profile_count':1,'named_objects':1,'objects':2},
        'fixture_sources':{name:sha((ROOT/name).read_bytes().replace(b'\r\n',b'\n')) for name in FIXTURE_SOURCES}}
    raw = json.dumps(result,sort_keys=True,separators=(',', ':'),ensure_ascii=False).encode()
    if len(raw)>65536:raise ValueError('The authored profile fixture exceeds its delivery bound')
    return raw


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();_no_links(args.output)
    raw=fixture()
    if args.output.exists():
        if args.output.stat().st_size>65536 or args.output.read_bytes()!=raw:
            raise ValueError('Preserve changed authored fixture attempts')
    else:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_bytes(raw)
    print(json.dumps({'schema':'toolkit-authored-genshin-profile-fixture-build-v1','bytes':len(raw),'sha256':sha(raw),
        'original_game_bytes':False,'apk_or_android_runtime_acceptance':False}))
