"""Data-only original ARM64 default-key producer and registration validation.

The caller must authenticate the complete original APK and selected ELF member
first. No original instruction is executed. Addresses are discovered from ELF
symbols, relocations and initializer metadata, never from a release/RVA list.
"""
from bisect import bisect_right
from dataclasses import dataclass, field
import hashlib
import mmap
import re
import struct


MAX_MODULE = 1024**3
CALLBACK = b'_ZN26FEncryptionKeyRegistration8CallbackEPh'
REGISTER = b'_Z29RegisterEncryptionKeyCallbackPFvPhE'
GETTER = b'_ZN14FCoreDelegates27GetPakEncryptionKeyDelegateEv'


def _check(value):
    if not value:
        raise ValueError('The original Wuthering bootstrap producer or registration is unsupported.')


def _signed(value, bits):
    return (value ^ (1 << (bits - 1))) - (1 << (bits - 1))


def _adrp(word, pc):
    if word & 0x9f000000 != 0x90000000:
        return None
    immediate = ((word >> 5 & 0x7ffff) << 2) | (word >> 29 & 3)
    return word & 31, (pc & ~4095) + (_signed(immediate, 21) << 12)


def _add(word):
    if word & 0xff800000 != 0x91000000:
        return None
    return word & 31, word >> 5 & 31, (word >> 10 & 4095) << (12 if word >> 22 & 1 else 0)


def _ldr(word):
    if word & 0xffc00000 != 0xf9400000:
        return None
    return word & 31, word >> 5 & 31, (word >> 10 & 4095) * 8


def _call(word, pc):
    return pc + _signed(word & 0x3ffffff, 26) * 4 if word & 0xfc000000 == 0x94000000 else None


@dataclass(frozen=True)
class DefaultOutput:
    parameter: bytes = field(repr=False)
    module_sha256: str
    callback: int
    initializer: int
    source_address: int


class _Elf:
    def __init__(self, raw):
        self.raw = raw
        _check(64 <= len(raw) <= MAX_MODULE and raw[:7] == b'\x7fELF\x02\x01\x01')
        h = self.unpack('<16sHHIQQQIHHHHHH', 0)
        _check(h[1] == 3 and h[2] == 183 and h[3] == 1 and h[8] == 64 and
               h[9] == 56 and 1 <= h[10] <= 32 and h[11] == 64 and 1 <= h[12] <= 96 and h[13] < h[12])
        self.loads = []
        for i in range(h[10]):
            t, flags, off, va, _, size, memory, _ = self.unpack('<IIQQQQQQ', h[5] + i * 56)
            _check(off + size <= len(raw) and size <= memory)
            if t == 1:
                self.loads.append((flags, va, memory))
        table = [self.unpack('<IIQQQQIIQQ', h[6] + i * 64) for i in range(h[12])]
        names = self.take(table[h[13]][4], table[h[13]][5])
        self.sections = []
        for s in table:
            _check(s[0] < len(names) and b'\0' in names[s[0]:])
            name = names[s[0]:names.index(0, s[0])].decode('ascii')
            if s[1] != 8:
                self.take(s[4], s[5])
            self.sections.append(dict(name=name, type=s[1], flags=s[2], va=s[3], offset=s[4],
                                      size=s[5], link=s[6], entry=s[9]))
        dynamic = [s for s in self.sections if s['type'] == 11]
        _check(len(dynamic) == 1)
        symbols = dynamic[0]
        _check(symbols['entry'] == 24 and symbols['size'] % 24 == 0 and
               symbols['size'] <= MAX_MODULE and symbols['link'] < len(self.sections))
        strings = self.sections[symbols['link']]
        _check(strings['type'] == 3 and strings['size'] <= MAX_MODULE)
        names = self.take(strings['offset'], strings['size'])
        self.symbols = {}
        for at in range(symbols['offset'], symbols['offset'] + symbols['size'], 24):
            no, info, _, sec, va, size = self.unpack('<IBBHQQ', at)
            _check(no < len(names))
            end = names.find(b'\0', no)
            _check(end >= 0)
            name = names[no:end]
            if name not in (CALLBACK, REGISTER, GETTER):
                continue
            _check(name not in self.symbols and info & 15 == 2 and 0 < sec < len(self.sections) and size)
            section = self.sections[sec]
            _check(section['flags'] & 4 and section['va'] <= va and va + size <= section['va'] + section['size'])
            self.symbols[name] = (va, size, section['offset'] + va - section['va'])
        _check(set(self.symbols) == {CALLBACK, REGISTER, GETTER})

    def take(self, at, size):
        _check(type(at) is int and type(size) is int and 0 <= at <= len(self.raw) and 0 <= size <= len(self.raw) - at)
        return self.raw[at:at + size]

    def unpack(self, layout, at):
        return struct.unpack(layout, self.take(at, struct.calcsize(layout)))

    def section(self, name):
        result = [s for s in self.sections if s['name'] == name]
        _check(len(result) == 1)
        return result[0]

    def words(self, symbol, maximum):
        va, size, off = self.symbols[symbol]
        _check(size % 4 == 0 and 0 < size <= maximum)
        return va, [x[0] for x in struct.iter_unpack('<I', self.take(off, size))]

    def readonly(self, va, size):
        choices = [s for s in self.sections if s['flags'] & 2 and not s['flags'] & 5 and
                   s['type'] != 8 and s['va'] <= va and va + size <= s['va'] + s['size']]
        _check(len(choices) == 1)
        s = choices[0]
        return self.take(s['offset'] + va - s['va'], size)

    def writable(self, va, size):
        return any(flags & 2 and start <= va and va + size <= start + memory for flags, start, memory in self.loads)

    def output(self):
        pc, words = self.words(CALLBACK, 256)
        registers, values, output = {0: ('output', 0)}, {}, {}
        returned = False
        for i, word in enumerate(words):
            _check(not returned)
            if word in (0xd503201f, 0xd503245f, 0xd503233f, 0xd50323bf):
                continue
            if word == 0xd65f03c0:
                returned = True
                continue
            address = _adrp(word, pc + i * 4)
            add = _add(word)
            if address:
                registers[address[0]] = address[1]
                continue
            if add:
                dest, source, amount = add
                _check(source in registers and dest != 31)
                old = registers[source]
                registers[dest] = (old[0], old[1] + amount) if isinstance(old, tuple) else old + amount
                continue
            pair = word & 0xffc00000
            single = word & 0xffc00000
            if pair in (0xad400000, 0xad000000, 0xa9400000, 0xa9000000):
                vector = pair in (0xad400000, 0xad000000)
                unit = 16 if vector else 8
                load = pair in (0xad400000, 0xa9400000)
                targets = [word & 31, word >> 10 & 31]
                base, displacement = word >> 5 & 31, _signed(word >> 15 & 127, 7) * unit
            elif single in (0x3dc00000, 0x3d800000, 0xf9400000, 0xf9000000):
                vector = single in (0x3dc00000, 0x3d800000)
                unit = 16 if vector else 8
                load = single in (0x3dc00000, 0xf9400000)
                targets = [word & 31]
                base, displacement = word >> 5 & 31, (word >> 10 & 4095) * unit
            else:
                raise ValueError('The native default callback is not a supported static copy producer.')
            _check(base in registers)
            origin = registers[base]
            for n, register in enumerate(targets):
                key = vector, register
                offset = displacement + n * unit
                if load:
                    _check(type(origin) is int)
                    source = origin + offset
                    values[key] = [(value, source + j) for j, value in enumerate(self.readonly(source, unit))]
                else:
                    _check(isinstance(origin, tuple) and origin[0] == 'output' and key in values)
                    start = origin[1] + offset
                    _check(0 <= start <= 32 - unit and all(j not in output for j in range(start, start + unit)))
                    output.update((start + j, value) for j, value in enumerate(values[key]))
        _check(returned and set(output) == set(range(32)))
        source = output[0][1]
        _check(all(output[i][1] == source + i for i in range(32)))
        return bytes(output[i][0] for i in range(32)), source

    def references(self, symbol, maximum, *, addresses_only=False):
        pc, words = self.words(symbol, maximum)
        addresses = set()
        for i, word in enumerate(words):
            page = _adrp(word, pc + i * 4)
            if not page or i + 1 == len(words):
                continue
            following = words[i + 1]
            add, load = _add(following), _ldr(following)
            if add and add[1] == page[0]:
                addresses.add((add[0], page[1] + add[2]))
            if not addresses_only and load and load[1] == page[0]:
                addresses.add((load[0], page[1] + load[2]))
        return addresses

    def registration(self):
        callback = self.symbols[CALLBACK][0]
        register = self.symbols[REGISTER][0]
        getter = {va for reg, va in self.references(GETTER, 512, addresses_only=True) if reg == 0 and self.writable(va, 16)}
        _check(len(getter) == 1)
        _check(bool(getter & {va for _, va in self.references(REGISTER, 2048)}))
        _, register_words = self.words(REGISTER, 2048)
        arguments, captured = {0}, False
        for word in register_words:
            if word & 0xffc00000 == 0xf9000000:
                captured |= word & 31 in arguments and word >> 5 & 31 != 31
                continue
            if word & 0xffc00000 == 0xa9000000:
                captured |= bool({word & 31, word >> 10 & 31} & arguments) and word >> 5 & 31 != 31
                continue
            if word & 0xffe0ffe0 == 0xaa0003e0:
                target, source = word & 31, word >> 16 & 31
                copied = source in arguments
                arguments.discard(target)
                if copied:
                    arguments.add(target)
            elif word & 0xfc000000 == 0x94000000:
                arguments.difference_update(range(19))
            elif (word & 0x7c000000 == 0x14000000 or word & 0x7e000000 in (0x34000000, 0x36000000)
                  or word & 0xff000010 == 0x54000000):
                continue
            else:
                arguments.discard(word & 31)
            if captured:
                break
        _check(captured)
        init = self.section('.init_array')
        _check(init['type'] == 14 and init['size'] % 8 == 0 and init['size'] <= 128 * 1024)
        got, constructors = set(), set()
        for s in self.sections:
            if s['type'] != 4:
                continue
            _check(s['entry'] == 24 and s['size'] % 24 == 0 and s['size'] <= 64 * 1024**2)
            for off in range(s['offset'], s['offset'] + s['size'], 24):
                address, info, value = self.unpack('<QQq', off)
                if info != 1027:
                    continue
                if value == callback:
                    _check(self.writable(address, 8))
                    got.add(address)
                if init['va'] <= address < init['va'] + init['size']:
                    _check((address - init['va']) % 8 == 0)
                    constructors.add(value)
        _check(1 <= len(got) <= 8 and constructors)
        frame = self.section('.eh_frame_hdr')
        _check(self.take(frame['offset'], 4) == bytes((1, 0x1b, 3, 0x3b)))
        count, = self.unpack('<I', frame['offset'] + 8)
        _check(1 <= count <= 1_000_000 and 12 + 8 * count <= frame['size'])
        starts = [frame['va'] + self.unpack('<i', frame['offset'] + 12 + i * 8)[0] for i in range(count)]
        _check(starts == sorted(set(starts)))
        text = self.section('.text')
        bindings = []
        for start in constructors:
            i = bisect_right(starts, start) - 1
            if i < 0 or starts[i] != start or i + 1 == len(starts):
                continue
            end = starts[i + 1]
            if not text['va'] <= start < end <= text['va'] + text['size'] or end - start > 16384:
                continue
            words = [x[0] for x in struct.iter_unpack('<I', self.take(text['offset'] + start - text['va'], end - start))]
            for j, word in enumerate(words):
                page = _adrp(word, start + j * 4)
                if page is None or j + 2 >= len(words):
                    continue
                base, address = page
                k = j + 1
                add = _add(words[k])
                if add and add[1] == base:
                    base, address, k = add[0], address + add[2], k + 1
                if k + 1 >= len(words):
                    continue
                load = _ldr(words[k])
                if load and load[0] == 0 and load[1] == base and address + load[2] in got and _call(words[k + 1], start + (k + 1) * 4) == register:
                    bindings.append(start)
        _check(len(bindings) == 1)
        return bindings[0]


def default_output(path, expected_sha256):
    """Derive one registered native output, after independently verified member integrity."""
    _check(isinstance(expected_sha256, str) and re.fullmatch('[0-9a-f]{64}', expected_sha256))
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        size = stream.seek(0, 2)
        _check(64 <= size <= MAX_MODULE)
        stream.seek(0)
        for part in iter(lambda: stream.read(1024**2), b''):
            digest.update(part)
        _check(digest.hexdigest() == expected_sha256)
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as raw:
            elf = _Elf(raw)
            parameter, address = elf.output()
            constructor = elf.registration()
            return DefaultOutput(parameter, expected_sha256, elf.symbols[CALLBACK][0], constructor, address)
