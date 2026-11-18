"""Explicit Windows capability for the toolkit's pinned source-built ooz WASM.

The existing closed bundled-resource validator owns software/source/notice/Node
discovery. No game DLL, PATH Node, npm package or network fallback is selected.
Android requires a separate accepted capability and never imports this runtime.
"""
import hashlib
from pathlib import Path
import struct

from .game_data_protocol import GameDataError
from .private_data_paths import _no_links

MAX_PACKED=16*1024**2
MAX_DECODED=1024**2
NODE_SHA256='d702daa815eabbff763c7d3808e235cf031cf2ca70211b56847bc72f51e240e5'
WRAPPER_SHA256='042a89949156d960ccb4ab67026edb35fd9f116b78852d44c7d92889685f4562'
DECODER_SHA256='fda7d49be8ee8f45cf7de2c7411b36627b6c5f358397f86900744f79964aca27'

PROGRAM='''
import {readFileSync} from 'node:fs';
const {decompress}=await import(process.argv[1]);
const source=readFileSync(0), output=[];
let at=0,total=0;
while(at<source.length){
 if(at+8>source.length)throw Error('Invalid batch framing');
 const packed=source.readUInt32LE(at), decoded=source.readUInt32LE(at+4);at+=8;
 if(!packed||!decoded||packed>16777216||decoded>1048576||at+packed>source.length||total+decoded>1048576)
  throw Error('Invalid batch bounds');
 const result=decompress(source.subarray(at,at+packed),decoded);at+=packed;total+=decoded;
 if(!(result instanceof Uint8Array)||result.length!==decoded)throw Error('Invalid decoded output');
 output.push(result);
}
process.stdout.write(Buffer.concat(output,total));
'''


def _check(value):
    if not value:raise GameDataError('publisher_codec_unavailable',
        'The verified toolkit Oodle decoder is unavailable. Repair the toolkit installation.',409)


def _run(command,**options):
    import subprocess
    try:return subprocess.run(command,capture_output=True,**options)
    except subprocess.TimeoutExpired as error:raise TimeoutError('Owned decoder timeout') from error


class WindowsOodle:
    """Ephemeral capability; no paths or provider objects enter durable handles."""
    def __init__(self,layout):
        self.layout=layout
        self._validated()

    def _validated(self):
        # This is a software-container/inventory verifier, not a game adapter.
        from .prebuilt_node_reader import production_zzz_reader
        reader=production_zzz_reader(layout=self.layout)
        node=reader.executable
        module=reader.root/'dependencies/ooz/index.js'
        decoder=reader.root/'dependencies/ooz/build/ooz.js'
        for path,digest in ((node,NODE_SHA256),(module,WRAPPER_SHA256),(decoder,DECODER_SHA256)):
            _no_links(path)
            with path.open('rb') as stream:_check(hashlib.file_digest(stream,'sha256').hexdigest()==digest)
        return reader,module

    @property
    def identity(self):
        reader,_=self._validated()
        return {'schema':'toolkit-owned-oodle-windows/1','container_identity':reader.identity,
            'node_sha256':NODE_SHA256,'wrapper_sha256':WRAPPER_SHA256,'decoder_sha256':DECODER_SHA256}

    def decode(self,blocks,*,work,check):
        _check(isinstance(blocks,(list,tuple)) and len(blocks)<=256)
        framed=[];packed=decoded=0
        for method,data,size in blocks:
            _check(method=='Oodle' and isinstance(data,bytes) and 0<len(data)<=MAX_PACKED and
                type(size) is int and 0<size<=MAX_DECODED)
            packed+=len(data);decoded+=size
            _check(packed<=MAX_PACKED and decoded<=MAX_DECODED)
            framed.append(struct.pack('<II',len(data),size)+data)
        if not blocks:return b''
        work=Path(work).absolute();_no_links(work);_check(work.is_dir() and work==work.resolve())
        check();reader,module=self._validated()
        identity=reader.identity
        try:
            result=_run([str(reader.executable),'--max-old-space-size=64','--input-type=module',
                '-e',PROGRAM,module.as_uri()],input=b''.join(framed),
                cwd=work,env=reader.environment(),timeout=30)
        except (OSError,TimeoutError) as error:
            raise GameDataError('publisher_codec_failed',
                'The toolkit Oodle decoder could not complete. Your previous data is retained.',409) from error
        check();after,_=self._validated();_check(after.identity==identity)
        if result.returncode or len(result.stdout)!=decoded:
            raise GameDataError('publisher_codec_failed',
                'The toolkit Oodle decoder could not verify the original output. Your previous data is retained.',409)
        return result.stdout


def create_compression(*,platform,layout=None):
    if platform not in {'windows','desktop'}:return None
    # Keep Android and other unsupported hosts independent of desktop imports.
    from .runtime_bundle import discover_layout
    from .preparation_errors import PreparationFailure
    layout=layout or discover_layout()
    if layout.mode!='bundle' or layout.profile!='runtime':return None
    try:return WindowsOodle(layout)
    except (PreparationFailure,OSError,ValueError,GameDataError):return None
