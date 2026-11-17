"""Read original ZZZ gateway key data; never load or execute client code.

This owns the evidenced x64 array-literal carrier and adjacent-XOR XML format.
PE section locations, array locations, lengths, mask and RSA parameters come
from each official input. No client address, revision or key is a source literal.
The resulting candidates still need the original gateway-response join.
"""
from bisect import bisect_left
from dataclasses import dataclass, field
import base64
import hashlib
import re
import struct
import xml.etree.ElementTree as ET


PROFILE = 'zzz-x64-rsa-xml-array-v1'
MAX_SECTION = 256 * 1024**2
READ_WINDOW = 4 * 1024**2
MAX_INITIALIZER = 64 * 1024
MAX_ARRAY = 8192
MAX_CANDIDATES = 32
_LEA = re.compile(rb'[\x48-\x4f]\x8d')
_XOR = re.compile(rb'(?:[\x40-\x4f])?\x80')


def _check(value):
    if not value:
        raise ValueError('Unsupported original ZZZ gateway key data.')


def source_plan(size, read):
    """Read only bounded PE metadata; the returned data range is not fetched.

    Callers must account for complete authenticated transport chunks even when
    these small header reads share a chunk with other original client bytes.
    """
    _check(type(size) is int and 256 <= size <= 16 * 1024**3)

    def exact(start, length):
        _check(0 <= start <= size - length and 0 < length <= 16 * 1024)
        result = read(start, length)
        _check(isinstance(result, bytes) and len(result) == length)
        return result

    dos = exact(0, 64)
    _check(dos[:2] == b'MZ')
    pe = struct.unpack_from('<I', dos, 60)[0]
    _check(64 <= pe <= 1024**2)
    header = exact(pe, 24)
    _check(header[:4] == b'PE\0\0')
    machine, count = struct.unpack_from('<HH', header, 4)
    optional = struct.unpack_from('<H', header, 20)[0]
    _check(machine == 0x8664 and 1 <= count <= 96 and 112 <= optional <= 4096)
    body = exact(pe + 24, optional + count * 40)
    _check(struct.unpack_from('<H', body)[0] == 0x20b)
    sections = []
    for index in range(count):
        at = optional + index * 40
        name = body[at:at + 8].rstrip(b'\0')
        virtual, rva, length, offset = struct.unpack_from('<4I', body, at + 8)
        flags = struct.unpack_from('<I', body, at + 36)[0]
        if name != b'.upx0':
            continue
        _check(0 < length <= MAX_SECTION and 0 < virtual <= MAX_SECTION
               and 0 <= offset <= size - length and flags & 0x20000000)
        sections.append({'name': '.upx0', 'offset': offset, 'bytes': length,
                         'rva': rva, 'profile': PROFILE})
    _check(len(sections) == 1)
    return sections[0]


def _memory(data, at, opcode, *, qword):
    """Recognize one data-carrier operand, not a general instruction decoder."""
    start = at
    if at >= len(data):
        return None
    rex = data[at] if 0x40 <= data[at] <= 0x4f else 0
    at += bool(rex)
    if (qword and not rex & 8) or at + 2 > len(data) or data[at] != opcode:
        return None
    modrm = data[at + 1]
    mode, register, base = modrm >> 6, (modrm >> 3 & 7) + ((rex & 4) << 1), modrm & 7
    at += 2
    if mode == 3:
        return None
    if base == 4:
        if at >= len(data):
            return None
        sib = data[at]
        at += 1
        if sib >> 3 & 7 != 4 or rex & 2:
            return None
        base = sib & 7
    if mode == 0 and base == 5:
        return None  # RIP-relative/absolute data is a different carrier.
    base += (rex & 1) << 3
    width = {0: 0, 1: 1, 2: 4}[mode]
    if at + width > len(data):
        return None
    displacement = int.from_bytes(data[at:at + width], 'little', signed=True) if width else 0
    return register, base, displacement, at + width - start


def _lengths(data, at):
    # Original new-array ABI: literal length in EDX before the allocation call,
    # followed by the managed-array data-address LEA. The call is never invoked.
    calls = [i for i in range(max(0, at - 32), at - 4) if data[i] == 0xe8]
    if not calls:
        return ()
    call = calls[-1]
    if at - (call + 5) > 16:
        return ()
    result = set()
    for index in range(max(0, call - 48), call - 4):
        if data[index] == 0xba:
            length = struct.unpack_from('<I', data, index + 1)[0]
            if 128 <= length <= MAX_ARRAY and length % 8 == 0:
                result.add(length)
    return tuple(sorted(result)) if len(result) <= 4 else ()


def _constant_array(data, start, end, base, length):
    """Extract complete literal declarations, without interpreting instructions.

    Unrecognized carriers produce no candidate. A structurally valid private
    XML key is still unaccepted until a unique official response decrypts.
    """
    constants, stores = {}, {}
    at = start
    while at < end:
        if at + 10 <= end and 0x48 <= data[at] <= 0x4f and 0xb8 <= data[at + 1] <= 0xbf:
            register = data[at + 1] - 0xb8 + ((data[at] & 1) << 3)
            constants[register] = (data[at + 2:at + 10], at + 10)
            at += 10
            continue
        memory = _memory(data, at, 0x89, qword=True)
        if memory:
            register, receiver, displacement, width = memory
            if receiver == base and register in constants:
                value, declared = constants[register]
                offset = displacement - 32
                if 0 <= offset <= length - 8 and offset % 8 == 0 and at - declared <= 128:
                    if offset in stores:
                        return None
                    stores[offset] = value
                del constants[register]
            at += width
        else:
            at += 1
    if set(stores) != set(range(0, length, 8)):
        return None
    return b''.join(stores[index] for index in range(0, length, 8))


def _private_key(encoded, mask):
    plain = bytes([encoded[0] ^ mask]) + bytes(a ^ b for a, b in zip(encoded[1:], encoded[:-1]))
    xml = plain.rstrip(b'\0')
    if (len(plain) - len(xml) > 7 or b'\0' in xml or b'<!' in xml or b'&' in xml
            or not xml.startswith(b'<RSAKeyValue>')):
        return None
    try:
        root = ET.fromstring(xml)
        expected = {'Modulus', 'Exponent', 'D', 'P', 'Q', 'DP', 'DQ', 'InverseQ'}
        if (root.tag != 'RSAKeyValue' or root.attrib or len(root) != 8
                or {item.tag for item in root} != expected
                or any(item.attrib or len(item) or not item.text for item in root)):
            return None
        values = {item.tag: int.from_bytes(base64.b64decode(
            re.sub(r'[ \t\r\n]', '', item.text), validate=True), 'big') for item in root}
        bits = values['Modulus'].bit_length()
        if (not 1024 <= bits <= 4096 or any(value <= 0 for value in values.values())
                or any(values[name].bit_length() > bits for name in ('D', 'P', 'Q'))):
            return None
        if (values['DP'] != values['D'] % (values['P'] - 1)
                or values['DQ'] != values['D'] % (values['Q'] - 1)
                or values['InverseQ'] != pow(values['Q'], -1, values['P'])):
            return None
        from Crypto.PublicKey import RSA
        key = RSA.construct((values['Modulus'], values['Exponent'], values['D'],
                             *sorted((values['P'], values['Q']))), consistency_check=True)
        if not 1024 <= key.size_in_bits() <= 4096:
            return None
        return key
    except (ValueError, TypeError, ZeroDivisionError, ET.ParseError):
        return None


@dataclass(frozen=True)
class KeyCandidate:
    key: object = field(repr=False, compare=False)
    proof: dict


def candidates(data, plan, *, allow_empty=False):
    """Locate the owned data format inside one planned official PE section.

    This is data recognition, not execution, emulation or disassembly. Candidate
    XML and key bytes never enter provenance or error messages.
    """
    _check(isinstance(data, bytes) and len(data) == plan['bytes'] <= MAX_SECTION
           and plan.get('profile') == PROFILE)
    xors, markers = {}, 0
    for match in _XOR.finditer(data):
        memory = _memory(data, match.start(), 0x80, qword=False)
        if memory:
            register, base, displacement, width = memory
            end = match.start() + width
            if register == 6 and displacement == 0 and end < len(data):
                markers += 1
                _check(markers <= 65536)
                xors.setdefault(base, []).append((match.start(), data[end], end + 1))
    result, attempted = {}, 0
    for match in _LEA.finditer(data):
        memory = _memory(data, match.start(), 0x8d, qword=True)
        if not memory:
            continue
        register, base, displacement, width = memory
        if displacement != 32 or register not in xors:
            continue
        lengths = _lengths(data, match.start())
        if not lengths:
            continue
        starts = [item[0] for item in xors[register]]
        position = bisect_left(starts, match.start() + width)
        for end, mask, xor_end in xors[register][position:]:
            if xor_end - match.start() > MAX_INITIALIZER:
                break
            for length in lengths:
                attempted += 1
                _check(attempted <= 4096)
                encoded = _constant_array(data, match.start() + width, end, base, length)
                if encoded is None:
                    continue
                key = _private_key(encoded, mask)
                if key is None:
                    continue
                identity = hashlib.sha256(key.export_key(format='DER')).hexdigest()
                proof = {'profile': PROFILE, 'section': plan['name'],
                         'initializer_offset': plan['offset'] + match.start(),
                         'initializer_bytes': xor_end - match.start(), 'array_bytes': length,
                         'array_sha256': hashlib.sha256(encoded).hexdigest()}
                result.setdefault(identity, KeyCandidate(key, proof))
                _check(len(result) <= MAX_CANDIDATES)
    _check(result or allow_empty)
    return tuple(result.values())


def read_candidates(plan, read):
    """Read planned section windows with bounded overlap and memory.

    Complete initializer recognition survives transport/window boundaries. The
    full selected section is considered before accepting its candidate set.
    """
    _check(0 < plan['bytes'] <= MAX_SECTION and plan.get('profile') == PROFILE)
    found = {}
    for start in range(0, plan['bytes'], READ_WINDOW):
        begin = max(0, start - MAX_INITIALIZER)
        length = min(start + READ_WINDOW, plan['bytes']) - begin
        data = read(plan['offset'] + begin, length)
        _check(isinstance(data, bytes) and len(data) == length)
        window = plan | {'offset': plan['offset'] + begin, 'bytes': length}
        for candidate in candidates(data, window, allow_empty=True):
            identity = hashlib.sha256(candidate.key.export_key(format='DER')).hexdigest()
            found.setdefault(identity, candidate)
            _check(len(found) <= MAX_CANDIDATES)
    _check(found)
    return tuple(found.values())
