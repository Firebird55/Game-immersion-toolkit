"""Generate a small signed authored APK as parser DATA, never an installed game.

Only reviewed fixture function bodies are compiled on the build host. Neither
the fixture generator, Crypto nor test modules enter the Android namespace.
"""
import argparse
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def generate(destination):
    from Crypto.Hash import SHA256
    from Crypto.PublicKey import RSA
    from Crypto.Signature import pkcs1_15
    from Crypto.Util.asn1 import DerSequence
    from backend.publisher_crypto import DesktopPublisherCrypto
    from backend.publisher_apk import CHUNK, verify_stream
    from backend.publisher_apk_zip import ApkMetadata
    from backend.wuthering_elf_bootstrap import CALLBACK, GETTER, REGISTER, default_output
    from backend.private_data_paths import _no_links
    namespace = dict(hashlib=hashlib,struct=struct,io=io,zipfile=zipfile,
        CHUNK=CHUNK,SHA256=SHA256,pkcs1_15=pkcs1_15,DerSequence=DerSequence,
        CALLBACK=CALLBACK,GETTER=GETTER,REGISTER=REGISTER)
    sources = {}
    for name,wanted in (
        ('test_wuthering_elf_bootstrap.py',{'adrp','add','load','branch','original'}),
        ('test_wuthering_native_bootstrap.py',{'manifest','signed_game'}),
        ('test_publisher_apk.py',{'lp','reference_digest'})):
        path=ROOT/'backend/tests'/name;raw=path.read_bytes()
        tree=ast.parse(raw,filename=name)
        selected=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in wanted]
        if {node.name for node in selected} != wanted or any(node.decorator_list for node in selected):
            raise ValueError('Review the changed authored fixture function contract')
        exec(compile(ast.Module(body=selected,type_ignores=[]),name,'exec'),namespace)
        sources['backend/tests/'+name]=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()
    with tempfile.TemporaryDirectory() as directory:
        path,identity=namespace['original'](Path(directory),base=0x10_0000_0000,register=12,vectors=(8,9))
        module=path.read_bytes()
        output=default_output(path,identity)
        apk=namespace['signed_game'](module,RSA.generate(2048))
    if not 1024 <= len(apk) <= 32768:raise ValueError('Authored APK exceeds its bounded probe size')
    crypto=DesktopPublisherCrypto()
    archive=ApkMetadata(lambda at,size:apk[at:at+size],len(apk),allow_signed_zero_tail=True,crypto=crypto)
    verified=verify_stream(io.BytesIO(apk),archive.layout,crypto=crypto)
    value={'schema':'toolkit-authored-wuwa-bootstrap-v1','fixture_sources':sources,
        'apk_base64':base64.b64encode(apk).decode('ascii'),'apk_sha256':verified['apk_sha256'],
        'apk_bytes':len(apk),'module_sha256':identity,'module_bytes':len(module),
        'default_output_sha256':hashlib.sha256(output.parameter).hexdigest(),
        'callback':output.callback,'initializer':output.initializer,'source_address':output.source_address}
    raw=(json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
    if len(raw)>65536:raise ValueError('Authored bootstrap envelope exceeds its bound')
    destination=Path(destination).absolute();_no_links(destination)
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'apk_bytes':len(apk),
        'module_bytes':len(module),'fixture_sources':sources,'original_game_bytes':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(generate(parser.parse_args().output),sort_keys=True))
