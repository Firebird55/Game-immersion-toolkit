"""Owned bounded Capstone CAPI contract, supplied only by the signed Android APK.

This is not a CPU emulator or a general plugin loader. Original x64 client bytes
are inert input. No Capstone import/path spoof or downloaded library is used.
"""
from dataclasses import dataclass
import hashlib
import json
import re

SOURCE_SHA256 = '796bdd69b05fa124fc2aa2e74b9a0b3d4c4e7f3e02add5e583cf2f3bca282ede'
MAX_INPUT = 65536
MAX_OUTPUT = 32 * 1024**2
U64 = 2**64 - 1


def _check(value):
    if not value: raise ValueError('The packaged original-data decoder did not verify.')


def _integer(value, low, high):
    _check(type(value) is int and low <= value <= high)
    return value


def _json(raw):
    raw = str(raw)
    _check(len(raw) <= MAX_OUTPUT)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _check(key not in result); result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: _check(False))


@dataclass(frozen=True)
class Memory:
    segment: int = 0
    base: int = 0
    index: int = 0
    scale: int = 0
    disp: int = 0


@dataclass(frozen=True)
class Operand:
    type: int
    size: int
    access: int
    reg: int = 0
    imm: int = 0
    mem: Memory = Memory()


@dataclass(frozen=True)
class Instruction:
    address: int
    size: int
    id: int
    mnemonic: str
    op_str: str
    bytes: bytes
    operands: tuple
    groups: tuple
    _reads: tuple
    _writes: tuple
    _decoder: object

    def reg_name(self, identifier): return self._decoder.reg_name(identifier)
    def regs_access(self): return list(self._reads), list(self._writes)
    def group(self, identifier): return identifier in self.groups


class PackagedX64Decoder:
    def __init__(self, native, proof):
        _check(isinstance(proof, dict) and proof.get('schema') == 'toolkit-x64-capi-v1'
            and proof.get('version') == '5.0.7' and proof.get('source_sha256') == SOURCE_SHA256
            and proof.get('abi') in {'arm64-v8a', 'x86_64'} and proof.get('pointer_bits') == 64
            and proof.get('api_major') == 5 and proof.get('api_minor') == 0
            and proof.get('apk_entry_verified') is True and proof.get('licenses_verified') is True
            and proof.get('system_fallback') is False and proof.get('original_client_execution') is False)
        for name in ('api_major', 'api_minor', 'pointer_bits'): _integer(proof[name], 0, 64)
        _check(all(isinstance(proof.get(name), str) and re.fullmatch('[0-9a-f]{64}', proof[name])
            for name in ('library_sha256', 'manifest_sha256')))
        names = proof.get('register_names')
        _check(isinstance(names, list) and 100 <= len(names) <= 1024
            and all(name is None or isinstance(name, str) and re.fullmatch(r'(?:[a-z0-9_]{1,32}|st\([0-7]\))', name) for name in names))
        self._native, self._proof, self._names, self._verified = native, dict(proof), tuple(names), False

    @classmethod
    def from_native(cls, native):
        # Only the actual maintained Java object can enable the global native
        # provider. Host reference fixtures may exercise parsing, never this gate.
        try:
            from java import jclass
            _check(isinstance(native, jclass('io.github.firebird55.gameimmersiontoolkit.FrameOcr')))
            _check(jclass('android.os.Process').is64Bit())
            result = cls(native, _json(native.x64DecoderProof()))
            result.verify_contract()
            result._verified = True
            return result
        except (ImportError, AttributeError, TypeError) as error:
            raise ValueError('The signed Android decoder provider is unavailable.') from error

    @property
    def verified(self): return self._verified
    def require_android(self):
        try:
            from java import jclass
            _check(isinstance(self._native, jclass('io.github.firebird55.gameimmersiontoolkit.FrameOcr')))
            _check(jclass('android.os.Process').is64Bit())
        except (ImportError, AttributeError, TypeError) as error:
            raise ValueError('The signed Android decoder provider is unavailable.') from error
    @property
    def detail(self): return True
    @detail.setter
    def detail(self, value): _check(value is True)
    def reg_name(self, identifier):
        return self._names[identifier] if type(identifier) is int and 0 <= identifier < len(self._names) else None
    def proof(self):
        return {key: value for key, value in self._proof.items() if key != 'register_names'}

    def verify_contract(self):
        from .android_x64_fixtures import CASES, REGISTER_NAMES
        _check(self._names == REGISTER_NAMES)
        complete = []
        for case in CASES:
            decoded = list(self.disasm(bytes.fromhex(case['hex']), case['address']))
            actual = [instruction_contract(value) for value in decoded]
            _check(actual == case['instructions'])
            complete.append(actual)
        digest = hashlib.sha256(json.dumps(complete, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self._proof.update(authored_contract_cases=len(CASES), authored_contract_sha256=digest,
            large_integer_exact=True, register_contract_exact=True, groups_access_exact=True)
        return digest

    def _registers(self, values):
        _check(isinstance(values, list) and len(values) <= 64)
        return tuple(_integer(value, 0, len(self._names) - 1) for value in values)

    def disasm(self, data, address, count=0):
        _check(isinstance(data, bytes) and len(data) <= MAX_INPUT)
        _integer(address, 0, U64); _integer(count, 0, MAX_INPUT)
        _check(address + len(data) <= 2**64)
        if not data: return iter(())
        # JNI long preserves the exact 64-bit pattern; JSON goes directly from
        # native C to Python, never through a JavaScript Number or float.
        signed = address if address < 2**63 else address - 2**64
        values = _json(self._native.disassembleX64(data, signed, count))
        _check(isinstance(values, list) and len(values) <= min(MAX_INPUT, len(data))
            and (not count or len(values) <= count))
        result, offset = [], 0
        for value in values:
            _check(isinstance(value, dict))
            size = _integer(value.get('size'), 1, 24)
            _check(_integer(value.get('address'), 0, U64) == address + offset and offset + size <= len(data)
                and value.get('bytes') == data[offset:offset + size].hex())
            for name in ('mnemonic', 'op_str'):
                _check(isinstance(value.get(name), str) and len(value[name]) <= 1024
                    and all(32 <= ord(char) < 127 for char in value[name]))
            operands = value.get('operands'); _check(isinstance(operands, list) and len(operands) <= 8)
            parsed = []
            for op in operands:
                _check(isinstance(op, dict))
                kind = _integer(op.get('type'), 1, 3)
                args = dict(type=kind, size=_integer(op.get('size'), 0, 64), access=_integer(op.get('access'), 0, 3))
                if kind == 1: args['reg'] = _integer(op.get('reg'), 0, len(self._names) - 1)
                elif kind == 2: args['imm'] = _integer(op.get('imm'), -2**63, 2**63 - 1)
                else:
                    memory = op.get('mem'); _check(isinstance(memory, dict))
                    args['mem'] = Memory(**{key: _integer(memory.get(key), 0, len(self._names) - 1)
                        for key in ('segment', 'base', 'index')},
                        scale=_integer(memory.get('scale'), 0, 8), disp=_integer(memory.get('disp'), -2**63, 2**63 - 1))
                parsed.append(Operand(**args))
            groups = value.get('groups'); _check(isinstance(groups, list) and len(groups) <= 8)
            result.append(Instruction(address + offset, size, _integer(value.get('id'), 1, 65535),
                value['mnemonic'], value['op_str'], data[offset:offset + size], tuple(parsed),
                tuple(_integer(group, 0, 255) for group in groups), self._registers(value.get('regs_read')),
                self._registers(value.get('regs_write')), self))
            offset += size
        return iter(result)


def authored_probe(native):
    from .genshin_native_x64 import decoder
    owned = decoder()
    _check(type(owned) is PackagedX64Decoder and owned.verified)
    owned.verify_contract()
    code = bytes.fromhex('488d05200000004869c007000000c3')
    instructions = list(owned.disasm(code, 0x1000))
    _check(len(instructions) == 3 and instructions[0].mnemonic == 'lea'
        and instructions[0].operands[1].mem.disp == 32 and instructions[1].operands[2].imm == 7
        and instructions[2].mnemonic == 'ret')
    return json.dumps({**owned.proof(), 'authored_operand_probe': True,
        'instructions': len(instructions), 'rip_displacement': 32, 'imul_immediate': 7,
        'python_owned_provider': True, 'original_client_execution': False}, sort_keys=True)


def instruction_contract(value):
    operands = []
    for op in value.operands:
        data = {'type': op.type, 'size': op.size, 'access': op.access}
        if op.type == 1: data['reg'] = op.reg
        elif op.type == 2: data['imm'] = op.imm
        else: data['mem'] = {name: getattr(op.mem, name) for name in ('segment', 'base', 'index', 'scale', 'disp')}
        operands.append(data)
    reads, writes = value.regs_access()
    return {'address': value.address, 'size': value.size, 'id': value.id, 'mnemonic': value.mnemonic,
        'op_str': value.op_str, 'bytes': value.bytes.hex(), 'groups': list(value.groups),
        'regs_read': reads, 'regs_write': writes, 'operands': operands}
