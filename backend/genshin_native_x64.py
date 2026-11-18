"""Bounded static original-native analysis with an exact software decoder closure.

Game code is input data. The decoder is a pinned toolkit dependency, never an
original game library. Windows amd64 uses the pinned original wheel. Android
requires the explicitly installed, APK-verified owned CAPI provider.
"""
from collections import deque
import bisect
from functools import lru_cache
import hashlib
import importlib
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import platform
import struct
import sys

CS_OP_REG, CS_OP_IMM, CS_OP_MEM = 1, 2, 3
DECODER_VERSION = '5.0.7'
DECODER_DLL_SHA256 = '46b7c385efe50db4def8aa99aa351c44ea28b1f3c2ccbc4ca41dbb2a02340e39'
DECODER_NOTICE_SHA256 = '404bd0cb0137ffb797258f844f53e5273f9b6d5781a1a359a2880411f49a4f30'
MAX_IMAGE = 768 * 1024**2
MAX_METHOD = 64 * 1024
_android_decoder = None


def install_android_decoder(provider):
    """Owned host injection only; never an environment path or game plugin."""
    from .android_x64_decoder import PackagedX64Decoder
    _check(type(provider) is PackagedX64Decoder and provider.verified)
    _check(not os.environ.get('LIBCAPSTONE_PATH'), 'An overridden native decoder path is unsupported.')
    provider.require_android()
    # The actual packaged CAPI must work before the dependency is advertised.
    sample = list(provider.disasm(bytes.fromhex('488d05200000004869c007000000c3'), 0x1000))
    _check(len(sample) == 3 and sample[0].operands[1].mem.disp == 32
           and sample[1].operands[2].imm == 7 and sample[2].mnemonic == 'ret')
    global _android_decoder
    _android_decoder = provider
    decoder.cache_clear()


def require_android_decoder(provider):
    """Verify the host's installed provider before using an Android-only route."""
    from .android_x64_decoder import PackagedX64Decoder
    _check(type(provider) is PackagedX64Decoder and provider.verified and _android_decoder is provider,
           'The verified Android decoder is unavailable.')
    _check(not os.environ.get('LIBCAPSTONE_PATH'), 'An overridden native decoder path is unsupported.')
    provider.require_android()
    _check(decoder() is provider, 'The Android decoder changed during original-data preparation.')


def _check(condition, reason='Unsupported, ambiguous or incomplete original-native input'):
    if not condition:
        raise ValueError(str(reason))


@lru_cache(maxsize=1)
def decoder():
    """Validate the exact native dependency before loading its library."""
    _check(not os.environ.get('LIBCAPSTONE_PATH'), 'An overridden native decoder path is unsupported.')
    if _android_decoder is not None:
        return _android_decoder
    _check(sys.platform == 'win32' and platform.machine().lower() in {'amd64', 'x86_64'}
           and struct.calcsize('P') == 8,
           'Original Genshin native preparation currently requires a Windows amd64 host.')
    try:
        distribution = importlib.metadata.distribution('capstone')
        spec = importlib.util.find_spec('capstone')
        _check(distribution.version == DECODER_VERSION and spec and spec.origin,
               'The pinned native decoder is unavailable.')
        package = Path(spec.origin).resolve().parent
        library = package / 'lib' / 'capstone.dll'
        notice = Path(distribution.locate_file('capstone-5.0.7.dist-info/LICENSE.TXT'))
        _check(library.is_file() and library.stat().st_size <= 16 * 1024**2
               and hashlib.sha256(library.read_bytes()).hexdigest() == DECODER_DLL_SHA256
               and notice.is_file() and notice.stat().st_size <= 64 * 1024
               and hashlib.sha256(notice.read_bytes()).hexdigest() == DECODER_NOTICE_SHA256,
               'The pinned native decoder or its complete notice differs.')
        module = importlib.import_module('capstone')
        _check(module.__version__ == DECODER_VERSION
               and (module.CS_OP_REG, module.CS_OP_IMM, module.CS_OP_MEM) == (1, 2, 3)
               and Path(module._cs._name).resolve() == library.resolve(),
               'The loaded native decoder differs from its verified closure.')
        result = module.Cs(module.CS_ARCH_X86, module.CS_MODE_64)
        result.detail = True
        return result
    except (OSError, ImportError, importlib.metadata.PackageNotFoundError) as error:
        raise ValueError('The pinned native decoder is unavailable; repair the toolkit installation.') from error


class Image:
    """Bounded PE32+ sections and original unwind-owned method ranges."""

    def __init__(self, data):
        _check(isinstance(data, bytes) and 512 <= len(data) <= MAX_IMAGE and data[:2] == b'MZ')
        self.data = data
        pe, = self.unpack('<I', 0x3c)
        _check(0x40 <= pe <= len(data) - 264 and data[pe:pe + 4] == b'PE\0\0')
        machine, count = self.unpack('<HH', pe + 4)
        optional_size, = self.unpack('<H', pe + 20)
        optional = pe + 24
        _check(machine == 0x8664 and 1 <= count <= 96 and 240 <= optional_size <= 4096)
        magic, = self.unpack('<H', optional)
        self.base, = self.unpack('<Q', optional + 24)
        directories, = self.unpack('<I', optional + 108)
        _check(magic == 0x20b and self.base > 0 and self.base % 0x1000 == 0 and directories >= 4)
        self.sections, self.executable_sections = {}, []
        raw_ranges, virtual_ranges = [], []
        for index in range(count):
            at = optional + optional_size + 40 * index
            name, virtual, rva, size, raw = self.unpack('<8sIIII', at)
            flags, = self.unpack('<I', at + 36)
            name = name.rstrip(b'\0').decode('ascii', errors='strict')
            _check(name and name not in self.sections and rva > 0 and raw <= len(data)
                   and 0 <= size <= len(data) - raw and max(virtual, size) > 0
                   and rva + max(virtual, size) <= 1 << 32)
            if size:
                _check(all(raw + size <= begin or end <= raw for begin, end in raw_ranges))
                raw_ranges.append((raw, raw + size))
            _check(all(rva + max(virtual, size) <= begin or end <= rva
                       for begin, end in virtual_ranges))
            virtual_ranges.append((rva, rva + max(virtual, size)))
            self.sections[name] = (rva, virtual, raw, size)
            if flags & 0x20000000 and size:
                self.executable_sections.append(name)
        _check(self.executable_sections)
        exception_rva, exception_size = self.unpack('<II', optional + 112 + 8 * 3)
        _check(0 < exception_size <= 2_000_000 * 12 and exception_size % 12 == 0)
        at = self.offset(exception_rva, exception_size)
        functions = []
        for index in range(exception_size // 12):
            start, end, _unwind = self.unpack('<III', at + 12 * index)
            _check(0 < start < end and end - start <= 64 * 1024**2)
            self.offset(start, end - start)
            functions.append((start, end))
        functions = sorted(set(functions))
        _check(functions and len({start for start, _ in functions}) == len(functions))
        self.function_starts = [start for start, _ in functions]
        self.function_ends = [end for _, end in functions]

    def unpack(self, format_, offset):
        size = struct.calcsize(format_)
        _check(type(offset) is int and 0 <= offset <= len(self.data) - size)
        return struct.unpack_from(format_, self.data, offset)

    def offset(self, rva, size=1):
        _check(type(rva) is type(size) is int and rva >= 0 and size >= 0)
        matches = [raw + rva - start for start, _virtual, raw, count in self.sections.values()
                   if start <= rva and rva + size <= start + count]
        _check(len(matches) == 1, 'Native read leaves its unique original PE section.')
        return matches[0]

    def function_start(self, rva):
        index = bisect.bisect_right(self.function_starts, rva) - 1
        return (self.function_starts[index] if index >= 0 and rva < self.function_ends[index] else None)

    def window(self, rva):
        index = bisect.bisect_left(self.function_starts, rva)
        _check(index < len(self.function_starts) and self.function_starts[index] == rva,
               'The native method has no exact original unwind ownership.')
        end = self.function_ends[index]
        _check(0 < end - rva <= MAX_METHOD)
        at = self.offset(rva, end - rva)
        return self.data[at:at + end - rva]

    def instructions(self, rva):
        result = list(decoder().disasm(self.window(rva), self.base + rva))
        _check(result and len(result) <= 65536)
        return result

    def leaf(self, rva, maximum=64):
        """An explicit small straight-line leaf, through its actual return."""
        _check(type(maximum) is int and 1 <= maximum <= 256)
        start = self.offset(rva)
        section = next(s for s in self.sections.values() if s[2] <= start < s[2] + s[3])
        size = min(maximum, section[2] + section[3] - start)
        result = []
        for instruction in decoder().disasm(self.data[start:start + size], self.base + rva):
            _check(not instruction.mnemonic.startswith('j') and instruction.mnemonic != 'call')
            result.append(instruction)
            if instruction.mnemonic == 'ret':
                return result
        raise ValueError('The original native leaf has no bounded owned return.')


FULL = (1 << 64) - 1
VOLATILE = ('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')

def register(name):
    if not name:
        return ('', 0)
    for root, parts in {'rax': ('rax', 'eax', 'ax', 'al', 'ah'), 'rbx': ('rbx', 'ebx', 'bx', 'bl', 'bh'), 'rcx': ('rcx', 'ecx', 'cx', 'cl', 'ch'), 'rdx': ('rdx', 'edx', 'dx', 'dl', 'dh'), 'rsi': ('rsi', 'esi', 'si', 'sil'), 'rdi': ('rdi', 'edi', 'di', 'dil'), 'rbp': ('rbp', 'ebp', 'bp', 'bpl'), 'rsp': ('rsp', 'esp', 'sp', 'spl')}.items():
        if name in parts:
            return (root, 8 if name in ('ah', 'bh', 'ch', 'dh') else 0)
    if name.startswith('r') and name[-1:] in ('d', 'w', 'b'):
        return (name[:-1], 0)
    return (name, 0)

def merge(left, right):
    result = {}
    for key in left.keys() & right.keys():
        av, am = left[key]
        bv, bm = right[key]
        mask = am & bm & ~(av ^ bv) & FULL
        if mask:
            result[key] = (av & mask, mask)
    return result


def jump_edges(instructions, supplied):
    edges = {} if supplied is None else dict(supplied)
    _check(len(edges) <= 64)
    for address, targets in edges.items():
        _check(address in instructions and instructions[address].mnemonic == 'jmp'
               and instructions[address].operands[0].type != CS_OP_IMM
               and isinstance(targets, tuple) and 0 < len(targets) <= 256
               and all(target in instructions for target in targets),
               'The supplied native jump-table edges are not bounded instruction targets.')
    return edges

class Constants:

    def __init__(self, seq, noreturn=(), limit=200000, *, jump_targets=None):
        _check(seq and len(seq) <= 65536)
        self.seq = seq
        self.ins = {i.address: i for i in seq}
        _check(len(self.ins) == len(seq))
        self.next = {a.address: b.address for a, b in zip(seq, seq[1:])}
        self.noreturn = set(noreturn)
        self.jump_targets = jump_edges(self.ins, jump_targets)
        self.frame = next((i.operands[1].mem.disp for i in seq[:40] if i.mnemonic == 'lea' and i.operands[0].type == CS_OP_REG and (i.reg_name(i.operands[0].reg) == 'rbp') and (i.operands[1].type == CS_OP_MEM) and (i.reg_name(i.operands[1].mem.base) == 'rsp') and (not i.operands[1].mem.index)), 0)
        self.states = {seq[0].address: {}}
        todo = deque([seq[0].address])
        iterations = 0
        while todo:
            at = todo.popleft()
            iterations += 1
            _check(iterations <= limit, 'constant CFG bound')
            state = self.transfer(self.ins[at], dict(self.states[at]))
            for child in self.successors(self.ins[at]):
                result = merge(self.states[child], state) if child in self.states else state
                if child not in self.states or result != self.states[child]:
                    self.states[child] = dict(result)
                    todo.append(child)
        self.iterations = iterations

    def successors(self, i):
        target = i.operands[0].imm if i.operands and i.operands[0].type == CS_OP_IMM else None
        if i.mnemonic in ('ret', 'retf', 'iret', 'int3', 'ud2') or (i.mnemonic == 'call' and target in self.noreturn):
            return []
        if i.mnemonic == 'jmp':
            return [target] if target in self.ins else self.jump_targets.get(i.address, ())
        if i.mnemonic.startswith('j'):
            return [p for p in (target, self.next.get(i.address)) if p in self.ins]
        return [self.next[i.address]] if i.address in self.next else []

    def location(self, i, op):
        if op.type == CS_OP_REG:
            return ('reg', register(i.reg_name(op.reg))[0])
        if op.type == CS_OP_MEM and (not op.mem.index):
            root = register(i.reg_name(op.mem.base))[0]
            if root in ('rsp', 'rbp'):
                return ('stack', op.mem.disp + (self.frame if root == 'rbp' else 0))
        return None

    def read(self, i, op, state):
        width = op.size * 8
        mask = (1 << width) - 1
        if op.type == CS_OP_IMM:
            return (op.imm & mask, mask)
        key = self.location(i, op)
        value, known = state.get(key, (0, 0))
        shift = register(i.reg_name(op.reg))[1] if op.type == CS_OP_REG else 0
        return (value >> shift & mask, known >> shift & mask)

    def write(self, i, op, pair, state):
        key = self.location(i, op)
        if key is None:
            if op.type == CS_OP_MEM:
                for stored in list(state):
                    if stored[0] == 'stack':
                        state.pop(stored)
            return
        width = op.size * 8
        if width > 64:
            state.pop(key, None)
            return
        value, known = pair
        low = (1 << width) - 1
        shift = register(i.reg_name(op.reg))[1] if op.type == CS_OP_REG else 0
        old, om = state.get(key, (0, 0))
        written = low << shift
        nv = old & ~written | (value & low) << shift
        nm = om & ~written | (known & low) << shift
        if op.type == CS_OP_REG and width == 32:
            nv &= (1 << 32) - 1
            nm |= FULL ^ (1 << 32) - 1
        if nm:
            state[key] = (nv & nm, nm & FULL)
        else:
            state.pop(key, None)

    def transfer(self, i, state):
        ops = i.operands
        m = i.mnemonic
        _, written_registers = i.regs_access()
        if m != 'call' and any((register(i.reg_name(r))[0] == 'rsp' for r in written_registers)):
            for key in list(state):
                if key[0] == 'stack':
                    state.pop(key)
        if m in ('mov', 'movabs', 'movzx', 'movsx', 'movsxd') and len(ops) == 2:
            value, known = self.read(i, ops[1], state)
            sw = ops[1].size * 8
            dw = ops[0].size * 8
            if m == 'movzx':
                known |= (1 << dw) - 1 ^ (1 << sw) - 1
            elif m in ('movsx', 'movsxd') and known & 1 << sw - 1:
                high = (1 << dw) - 1 ^ (1 << sw) - 1
                known |= high
                if value & 1 << sw - 1:
                    value |= high
            self.write(i, ops[0], (value, known), state)
            return state
        if m == 'lea' and len(ops) == 2 and (ops[1].type == CS_OP_MEM):
            mem = ops[1].mem
            value = mem.disp
            valid = True
            for identifier, scale in ((mem.base, 1), (mem.index, mem.scale)):
                if not identifier:
                    continue
                name = i.reg_name(identifier)
                if name == 'rip':
                    value += i.address + i.size
                    continue
                rv, rm = state.get(('reg', register(name)[0]), (0, 0))
                valid &= rm == FULL
                value += rv * scale
            self.write(i, ops[0], (value, FULL) if valid else (0, 0), state)
            return state
        if m in ('add', 'sub', 'xor', 'and', 'or', 'inc', 'dec', 'shl', 'shr', 'sar') and ops and (ops[0].type == CS_OP_REG):
            width = ops[0].size * 8
            mask = (1 << width) - 1
            av, am = self.read(i, ops[0], state)
            bv, bm = self.read(i, ops[1], state) if len(ops) > 1 else (1, mask)
            if m in ('xor', 'sub') and len(ops) > 1 and (ops[1].type == CS_OP_REG) and (ops[0].reg == ops[1].reg):
                result = (0, mask)
            elif am == mask and bm == mask:
                if m in ('shl', 'shr', 'sar'):
                    bv &= 63 if width == 64 else 31
                value = av + bv if m in ('add', 'inc') else av - bv if m in ('sub', 'dec') else av ^ bv if m == 'xor' else av & bv if m == 'and' else av | bv if m == 'or' else av << bv if m == 'shl' else av >> bv if m == 'shr' else (av - (1 << width) if av & 1 << width - 1 else av) >> bv
                result = (value & mask, mask)
            else:
                result = (0, 0)
            self.write(i, ops[0], result, state)
            return state
        if m == 'call':
            for name in VOLATILE:
                state.pop(('reg', name), None)
            for key in list(state):
                if key[0] == 'stack':
                    state.pop(key)
            return state
        if m in ('cmp', 'test', 'bt', 'nop') or m.startswith('j') or m in ('ret', 'int3', 'ud2'):
            return state
        _, writes = i.regs_access()
        for identifier in writes:
            state.pop(('reg', register(i.reg_name(identifier))[0]), None)
        for operand in ops:
            if operand.type == CS_OP_MEM and operand.access & 2:
                self.write(i, operand, (0, 0), state)
        if any((register(i.reg_name(r))[0] == 'rsp' for r in writes)):
            for key in list(state):
                if key[0] == 'stack':
                    state.pop(key)
        return state

    def value_before(self, address, name, bits):
        _check(1 <= bits <= 64 and address in self.states, 'unreachable or unknown native point')
        root, shift = register(name)
        value, known = self.states[address].get(('reg', root), (0, 0))
        mask = (1 << bits) - 1 << shift
        _check(known & mask == mask, ('ambiguous or clobbered native constant', hex(address), name, bits))
        return value >> shift & (1 << bits) - 1


class Definitions:
    """All reaching register writes, including conflicting and unknown paths."""

    successors = Constants.successors

    def __init__(self, seq, noreturn=(), limit=200000, *, jump_targets=None):
        _check(seq and len(seq) <= 65536)
        self.ins = {i.address: i for i in seq}
        self.next = {a.address: b.address for a, b in zip(seq, seq[1:])}
        self.noreturn = set(noreturn)
        self.jump_targets = jump_edges(self.ins, jump_targets)
        self.states = {seq[0].address: {}}
        todo, iterations = deque([seq[0].address]), 0
        while todo:
            at = todo.popleft()
            iterations += 1
            _check(iterations <= limit, 'Native definition CFG exceeds its bound.')
            ins, state = self.ins[at], dict(self.states[at])
            writes = {register(ins.reg_name(r))[0] for r in ins.regs_access()[1]}
            if ins.mnemonic == 'call':
                writes.update(VOLATILE)
            for name in writes:
                state[name] = frozenset({at})
            for child in self.successors(ins):
                if child in self.states:
                    old = self.states[child]
                    result = {key: old.get(key, frozenset({None}))
                              | state.get(key, frozenset({None})) for key in old.keys() | state.keys()}
                    _check(all(len(values) <= 1024 for values in result.values()))
                else:
                    result = state
                if child not in self.states or result != self.states[child]:
                    self.states[child] = dict(result)
                    todo.append(child)

    def before(self, address, name):
        _check(address in self.states, 'Unreachable native definition query.')
        return self.states[address].get(register(name)[0], frozenset({None}))
