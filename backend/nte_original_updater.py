"""Derive updater-envelope parameters from original publisher software as data.

This does not derive PAK, IoStore, localization or type-schema parameters.
Original source authentication and a complete declared resource-list validation
are required separately; successful native inspection alone is not admission.
"""
from dataclasses import dataclass, field
import hashlib
import struct

from .nte_updater_native import Image, check


@dataclass(frozen=True)
class Parameters:
    key: bytes = field(repr=False)
    iv: bytes = field(repr=False)
    sdk_sha256: str
    evidence: dict = field(repr=False)


def _slot(row):
    return (row.base_register, row.displacement) if row.base_register in (4, 5) else None


def _move(row, destination, source):
    return (row.opcode == (0x8b,) and row.modrm is not None and row.modrm >> 6 == 3
            and row.destination == destination and row.rm_register == source)


def _data(image, row, length):
    check(row.rip is not None)
    return image.data_bytes(row.rip, length)


def _iv(image, rows, index):
    call_window = rows[max(0, index - 6):index]
    arguments = [row for row in call_window if row.opcode == (0x8d,) and row.destination == 9 and _slot(row)]
    check(len(arguments) == 1)
    base, offset = _slot(arguments[0])
    slots, xmm, general, sources = {}, {}, {}, []
    for row in rows[max(0, index - 64):index]:
        if row.opcode == (0x0f, 0x10) and 0xf2 in row.prefix and row.rip is not None:
            xmm[row.destination] = (_data(image, row, 8), row.rip)
        elif row.opcode == (0x0f, 0xb7) and row.rip is not None:
            general[row.destination] = (_data(image, row, 2), row.rip)
        elif row.immediate_register is not None:
            length = 8 if row.rex & 8 else 4
            general[row.immediate_register] = (row.immediate.to_bytes(length, 'little'), None)
        elif row.opcode in ((0x8b,), (0x0f, 0xb6), (0x0f, 0xb7)) and row.modrm is not None:
            general.pop(row.destination, None)
        if row.base_register != base or not offset <= row.displacement < offset + 32:
            continue
        target = row.displacement - offset
        value, source = None, None
        if row.opcode in ((0xc6,), (0xc7,)) and row.modrm >> 3 & 7 == 0:
            length = 1 if row.opcode == (0xc6,) else 8 if row.rex & 8 else 4
            value = row.immediate.to_bytes(length, 'little')
        elif row.opcode == (0x0f, 0x11) and 0xf2 in row.prefix:
            check(row.destination in xmm)
            value, source = xmm[row.destination]
        elif row.opcode == (0x89,) and 0x66 in row.prefix:
            check(row.destination in general)
            value, source = general[row.destination]
            value = value[:2]
        if value is not None:
            check(target + len(value) <= 32)
            slots.update((target + part, byte) for part, byte in enumerate(value))
            if source is not None:
                sources.append((row.address, source, len(value)))
    check(all(at in slots for at in range(16, 32)))
    length = int.from_bytes(bytes(slots[at] for at in range(16, 24)), 'little')
    capacity = int.from_bytes(bytes(slots[at] for at in range(24, 32)), 'little')
    check(capacity == 15 and 0 < length <= capacity and all(at in slots for at in range(length + 1))
          and slots[length] == 0 and sources)
    return bytes(slots[at] for at in range(length)), tuple(sources)


def _cipher(image, target):
    target = image.target(target)
    owner = image.owner(target)
    check(owner is not None and owner[0] == target)
    rows = image.instructions(owner)
    providers = []
    for index, row in enumerate(rows):
        if row.call is None:
            continue
        body = image.target(row.call)
        callee_owner = image.owner(body)
        if callee_owner is not None and callee_owner[1] - callee_owner[0] > 16:
            continue
        try:
            leaf = image.leaf(body, 16)
        except ValueError:
            continue
        if (len(leaf) != 2 or leaf[0].opcode != (0x8d,) or leaf[0].destination != 0
                or leaf[0].rip is None or leaf[1].opcode != (0xc3,)):
            continue
        raw = image.data_bytes(leaf[0].rip, 20)
        nid, block, key_length, iv_length, flags = struct.unpack('<5I', raw)
        # OpenSSL's stable cipher identifier and CBC mode flags describe the
        # frozen envelope algorithm, not a release address or key value.
        if (nid, block, key_length, iv_length, flags & 15) != (419, 16, 16, 16, 2):
            continue
        after = rows[index + 1:index + 10]
        check(after and _move(after[0], 2, 0) and any(item.call is not None for item in after))
        providers.append((body, leaf[0].rip, key_length, iv_length))
    check(len(providers) == 1)
    pads = [row.immediate for row in rows if row.immediate_register == 8 and row.opcode == (0xb0,)]
    check(len(pads) == 2 and pads[0] == pads[1])
    provider = providers[0]
    check(any(row.immediate_register is not None and row.immediate == provider[2] for row in rows)
          and any(row.opcode == (0x83,) and row.immediate == provider[3] and row.modrm >> 3 & 7 == 7 for row in rows))
    return provider[2], provider[3], pads[0], {'consumer': target, 'cipher': provider[:2]}


def _setter(image, parameter):
    results = []
    for hit in image.lea_hits(parameter):
        if hit.destination != 0:
            continue
        try:
            rows = image.leaf(hit.address, 96)
        except ValueError:
            continue
        if len(rows) != 10:
            continue
        equality = rows[1]
        if not (equality.opcode in ((0x39,), (0x3b,)) and equality.modrm >> 6 == 3
                and {equality.destination, equality.rm_register} == {0, 1}
                and rows[2].opcode == (0x74,) and rows[3].opcode == (0x83,)
                and rows[3].base_register == 1 and rows[3].displacement == 24 and rows[3].immediate == 16
                and _move(rows[4], 2, 1) and rows[5].opcode == (0x72,)
                and rows[6].opcode == (0x8b,) and rows[6].destination == 2 and rows[6].base_register == 1
                and rows[6].displacement == 0
                and rows[7].opcode == (0x8b,) and rows[7].destination == 8 and rows[7].base_register == 1
                and rows[7].displacement == 16 and _move(rows[8], 1, 0) and rows[9].opcode == (0xe9,)):
            continue
        check(image.leaf(rows[2].next + rows[2].immediate, 1)[0].opcode == (0xc3,)
              and rows[5].next + rows[5].immediate == rows[7].address)
        results.append(hit.address)
    check(len(results) == 1)
    return results[0]


def _getter(image, target):
    target = image.target(target)
    owner = image.owner(target)
    check(owner is not None and owner[0] == target)
    rows = image.instructions(owner)
    fields = [row for row in rows if row.opcode == (0x8d,) and row.destination == 8
              and row.base_register == 0 and 0 < row.displacement < 65536 and row.displacement % 8 == 0]
    check(len(fields) == 1)
    field_row = fields[0]
    field_index = rows.index(field_row)
    check(field_index > 0 and rows[field_index - 1].call is not None)
    context = image.target(rows[field_index - 1].call)
    context_body = image.leaf(context, 16)
    check(len(context_body) == 2 and context_body[0].opcode == (0x8b,)
          and context_body[0].destination == 0 and context_body[0].rip is not None
          and context_body[1].opcode == (0xc3,))
    check(any(row.opcode == (0x8b,) and row.destination == 1 and row.base_register == 8
              and row.displacement == 16 for row in rows[field_index:]))
    suffixes = []
    for index, row in enumerate(rows):
        if row.opcode != (0x8d,) or row.destination != 0 or row.rip is None:
            continue
        after = rows[index + 1:index + 5]
        if len(after) != 4:
            continue
        length, pointer, preceding, destination = after
        if not (length.opcode == (0xc7,) and length.base_register == 4 and length.displacement == 48
                and length.rex & 8 and length.immediate is not None and 0 < length.immediate <= 64
                and pointer.opcode == (0x89,) and pointer.base_register == 4 and pointer.displacement == 40
                and pointer.destination == 0
                and preceding.opcode == (0x89,) and preceding.base_register == 4 and preceding.displacement == 32
                and preceding.destination == 1 and _move(destination, 1, 3)):
            continue
        check(index + 5 < len(rows) and rows[index + 5].call is not None)
        suffixes.append((image.data_bytes(row.rip, length.immediate), row.rip))
    check(len(suffixes) == 1)
    return field_row.displacement, context, suffixes[0], target


def _json_owner(image, field_offset, context):
    results = []
    literal = image.string(b'appId')
    for owner, reference in image.references(literal):
        if reference.destination != 2:
            continue
        rows = image.instructions(owner)
        index = rows.index(reference)
        tail = rows[index + 1:index + 40]
        check(len(tail) >= 12 and tail[0].opcode == (0x8d,) and tail[0].destination == 1
              and _slot(tail[0]) and tail[1].call is not None)
        key_slot = _slot(tail[0])
        candidates = []
        for at, row in enumerate(tail[:-3]):
            if row.call is None or image.target(row.call) != context:
                continue
            member, value, assignment = tail[at + 1:at + 4]
            if not (member.opcode == (0x8d,) and member.destination == 1 and member.base_register == 0
                    and member.displacement == field_offset and value.opcode == (0x8d,)
                    and value.destination == 2 and _slot(value) and assignment.call is not None):
                continue
            output = _slot(value)
            before = tail[2:at]
            getters = [part for part in range(len(before) - 3)
                       if before[part].opcode == (0x8d,) and before[part].destination == 8 and _slot(before[part]) == output
                       and before[part + 1].opcode == (0x8d,) and before[part + 1].destination == 2
                       and _slot(before[part + 1]) == key_slot
                       and before[part + 2].opcode == (0x8d,) and before[part + 2].destination == 1
                       and before[part + 3].call is not None]
            if len(getters) == 1:
                candidates.append(row.address)
        if len(candidates) == 1:
            results.append((owner[0], reference.address, candidates[0]))
    check(len(results) == 1)
    return results[0]


def derive(sdk: bytes, configuration: dict) -> Parameters:
    """Derive a candidate from the original owned consumer and JSON field join.

    Callers must authenticate both inputs, and verify the returned candidate
    against the complete current publisher resource-list checksum and inventory.
    """
    check(isinstance(configuration, dict) and isinstance(configuration.get('appId'), str))
    app_id = configuration['appId'].encode('utf-8')
    check(0 < len(app_id) <= 1024 and b'\0' not in app_id)
    image = Image(sdk)
    marker = image.string(b'PatcherXML0')
    candidates = []
    for owner, _ in image.references(marker):
        rows = image.instructions(owner)
        for index, row in enumerate(rows):
            if row.call is None:
                continue
            window = rows[max(0, index - 5):index]
            keys = [part for part in window if part.opcode == (0x8d,) and part.destination == 8 and part.rip is not None]
            if len(keys) != 1:
                continue
            try:
                key_length, iv_length, padding, cipher_proof = _cipher(image, row.call)
                iv, iv_proof = _iv(image, rows, index)
                setter = _setter(image, keys[0].rip)
            except ValueError:
                continue
            getters = []
            for caller, call in image.callers(setter):
                preceding = image.instructions(caller)
                before = preceding[max(0, preceding.index(call) - 6):preceding.index(call)]
                if not before or not _move(before[-1], 1, 0):
                    continue
                calls = [part for part in before if part.call is not None]
                if not calls:
                    continue
                returned = before.index(calls[-1])
                if any(part.opcode not in ((0x90,), (0x0f, 0x1f)) for part in before[returned + 1:-1]):
                    continue
                field_offset, context, suffix, getter = _getter(image, calls[-1].call)
                json_proof = _json_owner(image, field_offset, context)
                getters.append((suffix, getter, json_proof))
            check(len(getters) == 1)
            (suffix, suffix_address), getter, json_proof = getters[0]
            key = (app_id + suffix).ljust(key_length, bytes([padding]))[:key_length]
            iv = iv.ljust(iv_length, bytes([padding]))[:iv_length]
            evidence = {'consumer': owner[0], 'call': row.address, 'cipher': cipher_proof,
                        'iv': iv_proof, 'setter': setter, 'getter': getter,
                        'json': json_proof, 'suffix': (suffix_address, len(suffix))}
            candidates.append(Parameters(key, iv, hashlib.sha256(sdk).hexdigest(), evidence))
    check(candidates and len({(item.key, item.iv) for item in candidates}) == 1)
    return candidates[0]
