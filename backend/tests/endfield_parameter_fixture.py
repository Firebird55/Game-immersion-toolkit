"""Entirely authored instruction records, identities and encrypted index data."""
import base64
import struct
from types import SimpleNamespace as NS

from backend.endfield_client_contract import VFS, DEFINE

REGISTERS = {name: i + 1 for i, name in enumerate(
    ['rax', 'rbx', 'rcx', 'rdx', 'r8', 'eax', 'ecx', 'edx', 'dl', 'r8d', 'rdi', 'rip',
     'rsp', 'r9', 'r10', 'r14', 'rsi'])}


def register(name):
    return NS(type=1, reg=REGISTERS[name], size=8)


def immediate(value):
    return NS(type=2, imm=value, size=4)


def memory(name, offset=0, *, size=8):
    return NS(type=3, mem=NS(base=REGISTERS[name], index=0, disp=offset, scale=1), size=size)


def instruction(name, *operands, literal=None, owner=None, text=None):
    def reg_name(value):
        return next((name for name, number in REGISTERS.items() if number == value), '')
    def operand_text(value):
        if value.type == 1:
            return reg_name(value.reg)
        if value.type == 2:
            return hex(value.imm)
        return f'[{reg_name(value.mem.base)} + {value.mem.disp:#x}]'
    return NS(mnemonic=name, operands=list(operands), literal=literal, owner=owner,
              address=0, size=1, reg_name=reg_name,
              op_str=text or ', '.join(operand_text(v) for v in operands))


def move(destination, source, **options):
    return instruction('mov', destination, source, **options)


def static_store(owner, offset, operand, *, literal=None):
    rows = [move(register('rax'), memory('rip'), owner=owner),
            move(register('rcx'), memory('rax', 0xb8))]
    if literal is not None:
        rows.append(move(operand, memory('rip'), literal=literal))
    rows.append(move(memory('rcx', offset), operand))
    return rows


class Fixture:
    def __init__(self, *, key=bytes(range(32)), mask='owned mask', labels=None):
        self.key, self.mask = key, mask
        self.fields = {VFS: {'CHACHA_KEY': 0x60, 'CHACHA_KEYS': 0x68},
                       DEFINE: {'s_vfsTypeNameMap': 0x80, 'VFS_PROTO_VERSION': 0x98, 'KEY_LEN': 0xa4}}
        self.field_types = {'CHACHA_KEY': 'System.String', 'CHACHA_KEYS': ('array', 'System.String'),
                            's_vfsTypeNameMap': ('generic', 'System.Collections.Generic.Dictionary`2',
                                                ('Beyond.VFS.EVFSBlockType', 'System.String')),
                            'VFS_PROTO_VERSION': 'System.Int32', 'KEY_LEN': 'System.Int32'}
        self.labels = labels or {1: 'FixtureInitial', 21: 'FixtureHotfix',
                                 101: 'FixtureChinese', 102: 'FixtureEnglish',
                                 103: 'FixtureJapanese', 104: 'FixtureKorean'}
        encoded = base64.b64encode(bytes((v + mask.encode()[n % len(mask.encode())]) & 255
                                        for n, v in enumerate(key))).decode()
        pieces = [encoded[:11], 'unused authored fragment', encoded[11:28], encoded[28:-1]]
        ctor = static_store(VFS, 0x60, register('rax'), literal=encoded[-1:])
        for index, text in enumerate(pieces):
            ctor += [move(register('r8'), memory('rip'), literal=text),
                     move(register('edx'), immediate(index)), move(register('rcx'), register('rbx')),
                     instruction('call', immediate(0x700))]
        ctor += static_store(VFS, 0x68, register('rbx'))
        getter = []
        for index in (0, 2, 3):
            getter += [move(register('rax'), memory('rip'), owner=VFS),
                       move(register('rcx'), memory('rax', 0xb8)),
                       move(register('rax'), memory('rcx', 0x68)),
                       instruction('test', register('rax'), register('rax')),
                       move(register('rdi'), memory('rax', 0x20 + 8 * index))]
        getter += [move(register('r8'), memory('rip'), literal=mask), instruction('call', immediate(0x800))]
        transform = [instruction('call', immediate(0x810)), instruction('call', immediate(0x820)),
                     instruction('idiv', register('r8d')),
                     instruction('sub', register('eax'), register('ecx'), text='eax, ecx'),
                     instruction('add', register('eax'), immediate(0x100), text='eax, 0x100'),
                     instruction('and', register('eax'), immediate(0x800000ff), text='eax, 0x800000ff')]
        map_ctor = []
        for block, label in self.labels.items():
            map_ctor += [move(register('dl'), immediate(block)),
                         move(register('r8'), memory('rip'), literal=label),
                         move(register('rcx'), register('rbx')), instruction('call', immediate(0x900))]
        map_ctor += static_store(DEFINE, 0x80, register('rbx'))
        map_ctor += static_store(DEFINE, 0x98, immediate(3))
        map_ctor += static_store(DEFINE, 0xa4, immediate(32))
        self.methods = {
            (VFS, '.cctor'): ctor,
            (VFS, 'GetCommonChachaKeyBs'): getter,
            ('Fixture.PrivateTransform', 'ChangedName'): transform,
            (DEFINE, '.cctor'): map_ctor,
        }
        self.names = {(VFS, '.cctor'): 0x1000, (VFS, 'GetCommonChachaKeyBs'): 0x2000,
                      ('Fixture.PrivateTransform', 'ChangedName'): 0x800,
                      ('System.Convert', 'TryFromBase64Chars'): 0x810,
                      ('System.Text.Encoding', 'get_UTF8'): 0x820, (DEFINE, '.cctor'): 0x3000}
        wrapper = ('Beyond.Cryptor.Crc32Utils', 'XXHash64')
        helper = (DEFINE, 'GetVFSBlockHashFileName')
        formatter = ('Beyond.Byte.ByteHelper', 'GetHexString')
        self.names.update({wrapper: 0x4000, helper: 0x5000, formatter: 0x6000,
                           (DEFINE, 'GetVFSBlockHashDir'): 0x7000,
                           ('Unity.Collections.xxHash3', 'Hash64'): 0x7100})
        self.methods[wrapper] = [instruction('call', immediate(0x820)), instruction('call', immediate(0x7100))]
        self.methods[DEFINE, 'GetVFSBlockHashDir'] = [instruction('call', immediate(0x4000)),
            instruction('shr', register('rcx'), immediate(32), text='rcx, 0x20'),
            instruction('xor', register('ecx'), register('eax'), text='ecx, eax'),
            instruction('jmp', immediate(0x5000))]
        self.methods[helper] = [instruction('shr', register('eax'), immediate(n)) for n in (8, 16, 24)]
        self.methods[helper] += [instruction('call', immediate(0x6000))]
        self.methods[formatter] = [move(register('eax'), immediate(n)) for n in (0x30, 0x37, 10, 15, 4)]
        self.methods[formatter] += [instruction('cmovae', register('eax'), register('ecx')),
                                   move(memory('rbx', size=2), register('eax'))]

    def owner_reader(self, *_):
        fixture = self
        class Owners:
            def method(self, owner, name, _parameters=None):
                return {'owner': owner, 'name': name, 'pointer': fixture.names[owner, name]}
            def method_at(self, pointer, _parameters=None):
                names = [key for key, value in fixture.names.items() if value == pointer]
                assert len(names) == 1
                return self.method(*names[0])
            def field(self, owner, name):
                return {'offset': fixture.fields[owner][name]}
            def field_type(self, owner, name):
                return fixture.field_types[name]
            def called(self, rows, owner, name, parameters=None):
                method = self.method(owner, name, parameters)
                assert any(row.mnemonic in {'call', 'jmp'} and row.operands[0].type == 2 and
                           row.operands[0].imm == method['pointer'] for row in rows)
                return method
            def is_owner_usage(self, row, owner):
                return row.owner == owner
            def literal_usage(self, row):
                if row.literal is None:
                    raise ValueError('No authored literal')
                return {'text': row.literal, 'index': 0, 'slot': 0}
            def method_usage(self, row):
                if not hasattr(row, 'method_spec'):
                    raise ValueError('No authored MethodSpec')
                return row.method_spec
        return Owners()

    def code_reader(self, *_):
        return NS(linear=lambda method: self.methods[method['owner'], method['name']])


class MemorySource:
    def __init__(self, data):
        self.data, self.reads = data, []
    def read(self, offset, length):
        self.reads.append((offset, length))
        if not 0 <= offset <= len(self.data) - length:
            raise ValueError('Owned fixture range bounds')
        return self.data[offset:offset + length]


def toy_metadata():
    strings = bytearray()
    def string(value):
        at = len(strings)
        strings.extend(value.encode() + b'\0')
        return at
    names = {name: string(name) for name in ['Client', 'Owned', 'Prepare', 'Seed', 'Owned.dll']}
    method = struct.pack('<6I4H', names['Prepare'], 0, 0, 0, 0, 0x06000001, 0, 0, 0, 0)
    types = [0] * 23
    types[0], types[1], types[17], types[18] = names['Client'], names['Owned'], 1, 1
    image = struct.pack('<IiiI6I', names['Owned.dll'], 0, 0, 1, *([0] * 6))
    sections = {2: struct.pack('<II', 5, 0), 4: b'owned', 6: bytes(strings),
                12: method, 22: bytes(12), 24: struct.pack('<3I', names['Seed'], 0, 0x04000001),
                40: struct.pack('<23I', *types), 42: image}
    raw, header = bytearray(256), [0] * 64
    header[:2] = [0xfab11baf, 29]
    for index, data in sections.items():
        header[index:index + 2] = len(raw), len(data)
        raw.extend(data)
    struct.pack_into('<64I', raw, 0, *header)
    return bytes(raw)


def toy_pe():
    raw, pe = bytearray(0x1700), 0x80
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 0x3c, pe)
    raw[pe:pe + 4] = b'PE\0\0'
    struct.pack_into('<HH', raw, pe + 4, 0x8664, 4)
    struct.pack_into('<H', raw, pe + 20, 240)
    optional = pe + 24
    struct.pack_into('<H', raw, optional, 0x20b)
    struct.pack_into('<Q', raw, optional + 24, 0x190000000)
    for n, (name, rva, size, offset) in enumerate([
            (b'.text', 0x1000, 64, 0x1000), (b'.rdata', 0x2000, 128, 0x1400),
            (b'.data', 0x3000, 128, 0x1500), (b'.pdata', 0x4000, 12, 0x1600)]):
        struct.pack_into('<8sIIII', raw, optional + 240 + n * 40, name, size, rva, size, offset)
        struct.pack_into('<I', raw, optional + 240 + n * 40 + 36, 0x60000020 if n == 0 else 0x40000040)
    raw[0x1000:0x1004] = b'\x90\x90\x90\xc3'  # Authored inert instruction fixture.
    struct.pack_into('<3I', raw, 0x1600, 0x1000, 0x1004, 0x2050)
    raw[0x1450:0x1454] = b'\x01\0\0\0'
    return bytes(raw)
