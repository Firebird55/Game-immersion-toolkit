"""Independent changed-owner/ID/ABI fixtures, without original game payloads."""
import hashlib
import platform
import struct
import sys
from types import SimpleNamespace

import pytest

from backend import genshin_native_channel as channel, genshin_native_x64 as native


pytestmark = pytest.mark.skipif(not (sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64')),
                                reason='Pinned Windows-amd64 decoder only')


def fixture(generation=0, *, change=None):
    base = 0x1000000 + generation * 0x100000
    cctor, getter, loader, combine = 0x100, 0x200, 0x300, 0x800
    storage, array = 0x2000 + generation * 32, 0x3000 + generation * 32
    source_offset, cache_offset = 0x60 + generation * 8, 0x120 + generation * 8
    identity, slot = 17 + generation, 23 + generation
    node = 0x10203040 + generation * 37
    pieces = {}
    def assemble(entry):
        code = bytearray()
        def add(raw):code.extend(bytes.fromhex(raw))
        def rip(prefix, target):code.extend(bytes.fromhex(prefix) + struct.pack('<i', target - entry - len(code) - 7))
        def call(target):code.extend(b'\xe8' + struct.pack('<i', target - entry - len(code) - 5))
        return code, add, rip, call
    code, add, rip, call = assemble(cctor)
    rip('488b05', storage); rip('488b0d', array + slot * 8)
    add('488988'); code.extend(struct.pack('<i', source_offset)); add('c3')
    pieces[cctor] = bytes(code)
    code, add, rip, call = assemble(getter)
    rip('488b05', storage); add('488b80'); code.extend(struct.pack('<i', cache_offset))
    add('4885c07500'); return_jump = len(code) - 1
    call(loader)
    rip('488b0d', storage + (8 if change == 'cache-owner' else 0))
    add('488981'); code.extend(struct.pack('<i', cache_offset)); add('c3')
    code[return_jump] = len(code) - 1 - return_jump - 1
    pieces[getter] = bytes(code)
    code, add, rip, call = assemble(loader)
    add('554889e5')  # rbp is an owned stable local-frame base.
    call(0x900)
    rip('488b0d', storage + (8 if change == 'source-owner' else 0))
    add('488b91'); code.extend(struct.pack('<i', source_offset)); add('4889c1'); call(combine)
    if change == 'path-clobber':call(0x980)
    add('4889c1'); call(0x920); add('488945f0')
    add('488b4df0ba'); code.extend(struct.pack('<I', node)); call(0x940)
    add('85c07e00'); failure_jump = len(code) - 1
    add('89c2'); call(0x960); add('4889c6')
    if change == 'handle-clobber':add('48c745f000000000')
    add('488b4df0')
    if change == 'id-alias':
        add('41b9'); code.extend(struct.pack('<I', node)); add('4489ca')
    else:
        add('ba'); code.extend(struct.pack('<I', node + (1 if change == 'id-mismatch' else 0)))
    add('4989f0')
    if change == 'argument-clobber':add('31d2')
    call(0x940 if change == 'same-api' else 0x950)
    add('4889f05dc3')
    failure = len(code); add('31c05dc3')
    code[failure_jump] = failure - failure_jump - 1
    if change == 'trailing-unsupported':code.extend(b'\x0f')
    pieces[loader] = bytes(code)
    def instructions(rva):return list(native.decoder().disasm(pieces[rva], base + rva))
    image = SimpleNamespace(base=base, data=b''.join(pieces.values()), sections={'data':(0x1000,0x4000,0,0x4000)},
                            instructions=instructions, window=lambda rva:pieces[rva])
    globals_def, miscs_def, config_def, dispatch_def, path_def = [100 + generation * 10 + n for n in range(5)]
    owners = {('MoleMole','GlobalVars'):globals_def,('MoleMole','Miscs'):miscs_def,
              ('MoleMole','ConfigChannel'):config_def,('MoleMole','ConfigDispatchUrl'):dispatch_def,('System.IO','Path'):path_def}
    def method(name,rva,result,parameters=()):
        return {'index':rva + generation,'name':name,'rva':rva,'return_type':result,
                'parameters':[{'name':str(n),'type':{'kind':kind}} for n,kind in enumerate(parameters)]}
    source = {'index':11 + generation,'name':'channelConfigBlkName','type':{'index':7,'kind':14},'authored_offset_word':4<<24|source_offset}
    cache = {'index':12 + generation,'name':'_configChannel','type':{'index':8,'kind':18,'definition':config_def},'authored_offset_word':4<<24|cache_offset}
    methods = {globals_def:[method('.cctor',cctor,{'kind':1})],miscs_def:[
        method('GetConfigChannel',getter,{'kind':18,'definition':config_def}),
        method('LoadChannelConfigBlk',loader,{'kind':18,'definition':config_def})],
        path_def:[method('Combine',combine,{'kind':14},(14,14))]}
    def fields(definition):
        if definition==config_def:return [{'name':name} for name in ('ChannelName','DispatchConfigs')]
        if definition==dispatch_def:return [{'name':name} for name in ('DispatchName','DispatchUrls')]
        raise AssertionError('Unexpected metadata fields')
    def type_record(index):
        raw=bytearray(16);raw[8:10]=(22 if index==7 else 17).to_bytes(2,'little');return bytes(raw)
    view=SimpleNamespace(image=image,metadata=b'authored metadata',bindings=SimpleNamespace(type_record=type_record),
        named=lambda namespace,name:{'definition':owners[namespace,name],'namespace':namespace,'name':name},
        fields=fields,methods=lambda definition:methods[definition],
        field_offsets=lambda definition:[source] if definition==globals_def else [cache])
    literals=SimpleNamespace(text=lambda index:f'authored_{generation}.blk' if index==identity else pytest.fail('Unowned literal'))
    return view,SimpleNamespace(pairs=[(5,identity,slot)]),{5:{'array_rva':array}},literals,node


@pytest.mark.parametrize('generation',[0,1,7])
@pytest.mark.parametrize('alias',[False,True])
def test_current_typed_loader_owns_changed_basename_pointer_fields_and_object_id(generation,alias):
    view,usages,arrays,literals,node=fixture(generation,change='id-alias' if alias else None)
    result=channel.derive_channel_loader(view,usages,arrays,literals)
    assert result['source_basename']==f'authored_{generation}.blk'
    assert [row['id'] for row in result['object_candidates']]==[node]
    assert result['profile_only'] is True and result['complete_dispatch_bootstrap'] is False
    assert result['later_override_excluded'] is False
    assert all(row['sha256']==hashlib.sha256(view.image.window(row['rva'])).hexdigest() for row in result['methods'])


@pytest.mark.parametrize('change',['cache-owner','source-owner','id-mismatch','same-api','handle-clobber','argument-clobber','path-clobber','trailing-unsupported'])
def test_unowned_or_clobbered_loader_cannot_supply_a_profile_object_id(change):
    view,usages,arrays,literals,_=fixture(change=change)
    with pytest.raises(ValueError):channel.derive_channel_loader(view,usages,arrays,literals)
