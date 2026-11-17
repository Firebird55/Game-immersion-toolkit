"""Bounded data-only bootstrap readers for the official Infinity Nikki launcher.

No client code, archive tool, disassembler or PE-loading API is used. Source
provenance belongs to the caller: these structural checks are not Authenticode
verification and do not verify an incomplete installer's whole-file checksum.
NSIS structures follow its upstream fileform.h; Qt resource data retain a
big-endian byte length before each stored payload.
"""
from dataclasses import dataclass
import hashlib
import re
import struct
import urllib.request
import zlib

from . import infinity_nikki_release as release


MAX_MEMBER = 64 * 1024**2
MAX_HEADER = 4 * 1024**2
MAX_PACKED = 16 * 1024**2


def _require(condition):
    if not condition:
        raise ValueError('Infinity Nikki official launcher bootstrap is incomplete or has changed format.')


def nsis_overlay_offset(prefix: bytes, total: int) -> int:
    """Plan the next metadata range from a PE header, without fetching its image."""
    _require(isinstance(prefix, bytes) and 64 <= len(prefix) <= 64 * 1024 and
             type(total) is int and len(prefix) <= total <= 1024**3 and prefix[:2] == b'MZ')
    pe = struct.unpack_from('<I', prefix, 60)[0]
    _require(64 <= pe <= len(prefix) - 24 and prefix[pe:pe + 4] == b'PE\0\0')
    count, optional = struct.unpack_from('<H', prefix, pe + 6)[0], struct.unpack_from('<H', prefix, pe + 20)[0]
    start = pe + 24 + optional
    _require(1 <= count <= 96 and optional >= 2 and start + count * 40 <= len(prefix))
    _require(struct.unpack_from('<H', prefix, pe + 24)[0] in (0x10b, 0x20b))
    end = 0
    for index in range(count):
        size, offset = struct.unpack_from('<II', prefix, start + index * 40 + 16)
        _require(size <= total and offset <= total - size)
        if size:
            _require(offset >= start + count * 40)
            end = max(end, offset + size)
    _require(start + count * 40 <= end <= total - 32)
    return end


def _inflate(raw, limit, expected=None):
    decoder = zlib.decompressobj(-15)
    try:
        value = decoder.decompress(raw, limit + 1)
    except zlib.error as error:
        raise ValueError('Infinity Nikki launcher compression has changed format.') from error
    _require(len(value) <= limit and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
    _require(expected is None or len(value) == expected)
    return value


@dataclass(frozen=True)
class HeaderPlan:
    packed_bytes: int
    unpacked_bytes: int
    data_offset: int
    compressed: bool


def nsis_header_plan(frame: bytes) -> HeaderPlan:
    """Read exactly the first header and following header-block length prefix."""
    _require(isinstance(frame, bytes) and len(frame) == 32)
    flags, unpacked, following, packed = (struct.unpack_from('<I', frame, offset)[0] for offset in (0, 20, 24, 28))
    _require(flags & ~15 == 0 and frame[4:20] == b'\xef\xbe\xad\xdeNullsoftInst')
    size = packed & 0x7fffffff
    _require(0 < size <= MAX_HEADER and 0 < unpacked <= MAX_HEADER and following >= 32 + size)
    return HeaderPlan(size, unpacked, 32 + size, bool(packed & 0x80000000))


def decode_nsis_header(frame: bytes, packed: bytes) -> bytes:
    plan = nsis_header_plan(frame)
    _require(isinstance(packed, bytes) and len(packed) == plan.packed_bytes)
    value = _inflate(packed, MAX_HEADER, plan.unpacked_bytes) if plan.compressed else packed
    _require(len(value) == plan.unpacked_bytes)
    return value


def nsis_member_offsets(header: bytes, names=('xstarter.exe',)) -> dict:
    """Select named data members from NSIS Unicode extract instructions.

    Script instructions are inspected as records, never interpreted. Duplicate
    requested basenames are ambiguous and fail instead of selecting a branch.
    """
    _require(isinstance(header, bytes) and 68 <= len(header) <= MAX_HEADER and
             isinstance(names, tuple) and 0 < len(names) <= 8 and len(set(names)) == len(names))
    _require(all(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name) for name in names))
    entries, count = struct.unpack_from('<II', header, 20)
    strings, _ = struct.unpack_from('<II', header, 28)
    string_end, _ = struct.unpack_from('<II', header, 36)
    _require(68 <= entries <= strings <= string_end <= len(header) and 0 < count <= 100_000 and
             entries + count * 28 <= strings and (string_end - strings) % 2 == 0)
    found = {}
    for index in range(count):
        opcode, _, name_offset, data_offset, _, _, _ = struct.unpack_from('<7i', header, entries + index * 28)
        if opcode != 20:  # NSIS EW_EXTRACTFILE, standard visible Unicode build.
            continue
        _require(name_offset >= 0 and 0 <= data_offset <= 1024**3)
        start = strings + name_offset * 2
        _require(strings <= start < string_end)
        end = start
        while end + 2 <= string_end and end - start <= 4096 and header[end:end + 2] != b'\0\0':
            end += 2
        _require(end + 2 <= string_end and end - start <= 4096)
        name = header[start:end].decode('utf-16-le')
        if name in names:
            _require(name not in found)
            found[name] = data_offset
    _require(set(found) == set(names))
    return found


def decode_nsis_member(block: bytes) -> bytes:
    """Decode one complete independent member; solid streams are unsupported."""
    _require(isinstance(block, bytes) and 4 <= len(block) <= MAX_PACKED + 4)
    word = struct.unpack_from('<I', block)[0]
    _require(word & 0x7fffffff == len(block) - 4 and len(block) > 4)
    return _inflate(block[4:], MAX_MEMBER) if word & 0x80000000 else block[4:]


def launcher_data_resources(member: bytes) -> tuple[bytes, bytes]:
    """Find unique Qt identity/config data by stored lengths and actual schema.

    Identity and encoded config bytes are returned. Config semantics and the
    identity-derived cipher must both agree; addresses, versions, keys and Qt
    link addresses are not pinned to one release. Full member bytes must already
    come from the caller's verified official source.
    """
    _require(isinstance(member, bytes) and 64 <= len(member) <= MAX_MEMBER and member[:2] == b'MZ')
    identities = []
    matches = list(re.finditer(rb'"launcherAppId"', member))
    _require(0 < len(matches) <= 64)
    for match in matches:
        brace = member.rfind(b'{', max(0, match.start() - 4096), match.start())
        if brace < 0:
            continue
        start = brace - 3 if member[max(0, brace - 3):brace] == b'\xef\xbb\xbf' else brace
        if start < 4:
            continue
        size = struct.unpack_from('>I', member, start - 4)[0]
        if not 0 < size <= 4096 or start + size > len(member):
            continue
        identity = member[start:start + size]
        try:
            release._identity(identity)
        except (ValueError, TypeError, KeyError, UnicodeError):
            continue
        identities.append(identity)
    _require(len(identities) == 1)
    identity = identities[0]
    found = []
    candidates = 0
    for match in re.finditer(rb'[A-Za-z0-9+/]{64,}={0,2}', member):
        begin, end = match.span()
        # The final bytes of the big-endian size can themselves be base64
        # characters. Account for that prefix instead of pinning one data size.
        for start in range(begin, min(begin + 4, end)):
            if start < 4 or end - start > release.MAX_CONFIG or struct.unpack_from('>I', member, start - 4)[0] != end - start:
                continue
            candidates += 1
            _require(candidates <= 64)
            encoded = member[start:end]
            try:
                release.decode_launcher_config(encoded, identity)
            except (ValueError, TypeError, KeyError, UnicodeError):
                continue
            found.append(encoded)
    _require(len(found) == 1)
    return identity, found[0]


@dataclass(frozen=True)
class BootstrapPlan:
    pointer: release.LauncherPointer
    total_installer_bytes: int
    etag: str
    member_offset: int
    member_download_bytes: int
    header_sha256: str
    maximum_decoded_member_bytes: int = MAX_MEMBER


def _tag(value):
    _require(isinstance(value, str) and 2 <= len(value) <= 256 and value[0] == value[-1] == '"' and
             all(32 <= ord(char) <= 126 for char in value))
    return value


def _range(open_request, url, total, etag, offset, size):
    _require(type(offset) is int and type(size) is int and 0 <= offset <= total - size and
             0 < size <= MAX_PACKED + 4)
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'identity', 'User-Agent': 'GameImmersionToolkit/1',
        'If-Match': etag, 'Range': f'bytes={offset}-{offset + size - 1}'})
    with open_request(request, timeout=45) as response:
        _require(response.status == 206 and response.geturl() == url and
                 response.headers.get('Content-Range') == f'bytes {offset}-{offset + size - 1}/{total}' and
                 response.headers.get('ETag') == etag and response.headers.get('Content-Length') == str(size))
        value = response.read(size + 1)
    _require(len(value) == size)
    return value


def plan_bootstrap(region='global', *, opener=None) -> BootstrapPlan:
    """Read small metadata and report the exact launcher-member download first.

    This plan is bootstrap overhead only. It does not advertise an installer or
    launcher member as the game's dialogue/audio download or disk estimate.
    """
    pointer = release.discover_launcher(region)
    release._launcher_url(pointer.url, region)
    open_request = opener or urllib.request.build_opener(release._NoRedirect()).open
    request = urllib.request.Request(pointer.url, method='HEAD', headers={'Accept-Encoding': 'identity'})
    with open_request(request, timeout=45) as response:
        _require(response.status == 200 and response.geturl() == pointer.url)
        length = response.headers.get('Content-Length', '')
        _require(length.isdecimal() and 64 * 1024 <= int(length) <= 1024**3)
        total, etag = int(length), _tag(response.headers.get('ETag'))
    prefix = _range(open_request, pointer.url, total, etag, 0, 64 * 1024)
    overlay = nsis_overlay_offset(prefix, total)
    frame = _range(open_request, pointer.url, total, etag, overlay, 32)
    header_plan = nsis_header_plan(frame)
    packed = _range(open_request, pointer.url, total, etag, overlay + 32, header_plan.packed_bytes)
    header = decode_nsis_header(frame, packed)
    member_offset = overlay + header_plan.data_offset + nsis_member_offsets(header)['xstarter.exe']
    following = struct.unpack_from('<I', frame, 24)[0]
    _require(overlay + following <= total and member_offset <= overlay + following - 4)
    prefix = _range(open_request, pointer.url, total, etag, member_offset, 4)
    member_bytes = (struct.unpack('<I', prefix)[0] & 0x7fffffff) + 4
    _require(4 < member_bytes <= MAX_PACKED + 4 and member_offset + member_bytes <= overlay + following)
    return BootstrapPlan(pointer, total, etag, member_offset, member_bytes, hashlib.sha256(header).hexdigest())


def load_bootstrap_config(plan: BootstrapPlan, *, opener=None) -> tuple[bytes, dict, str]:
    """Download only the planned member and derive its original data resources.

    HTTPS publisher identity and the strong response validator bind all ranges
    to one selected installer. The component is never loaded or executed. This
    does not claim an independent whole-installer checksum/signature check.
    """
    _require(isinstance(plan, BootstrapPlan) and 64 * 1024 <= plan.total_installer_bytes <= 1024**3)
    release._launcher_url(plan.pointer.url, plan.pointer.region)
    _tag(plan.etag)
    open_request = opener or urllib.request.build_opener(release._NoRedirect()).open
    block = _range(open_request, plan.pointer.url, plan.total_installer_bytes, plan.etag,
                   plan.member_offset, plan.member_download_bytes)
    member = decode_nsis_member(block)
    identity, encoded = launcher_data_resources(member)
    return identity, release.decode_launcher_config(encoded, identity), hashlib.sha256(member).hexdigest()
