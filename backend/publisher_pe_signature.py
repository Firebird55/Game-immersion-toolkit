"""Source-neutral offline Authenticode verification, with explicit caller policy.

The original DLL is never loaded. Windows verifies a locked data-file handle;
cache-only verification does not claim fresh online revocation information.
Other hosts need an independently reviewed signature-verification capability.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

MAX_PE_BYTES = 64 * 1024**2


class SignatureCapabilityUnavailable(ValueError):
    """The host has no reviewed PE-chain verifier; APK RSA is insufficient."""


def check(condition, reason='Original publisher signature could not be verified.'):
    if not condition:
        raise ValueError(reason)


def _policy(publishers, maximum_bytes):
    check(isinstance(publishers, (set, frozenset)) and 0 < len(publishers) <= 16 and
          all(isinstance(value, str) and value.strip() == value and 0 < len(value) <= 256 and
              not any(ord(char) < 32 or ord(char) == 127 for char in value) for value in publishers),
          'Explicit publisher identities are required for signature verification.')
    check(type(maximum_bytes) is int and 512 <= maximum_bytes <= MAX_PE_BYTES,
          'An explicit bounded original PE size is required for signature verification.')
    return frozenset(publishers)


def source_runtime():
    if sys.platform != 'win32':
        raise SignatureCapabilityUnavailable(
            'This host needs a reviewed offline PE publisher-signature verifier.')


def verify(path, *, publishers, maximum_bytes):
    publishers = _policy(publishers, maximum_bytes)
    source_runtime()
    return _windows(Path(path), publishers=publishers, maximum_bytes=maximum_bytes)


def _windows(path, *, publishers, maximum_bytes):
    import ctypes as c
    import ctypes.wintypes as w
    import msvcrt
    import os
    import uuid

    class Guid(c.Structure):
        _fields_ = [('a', w.DWORD), ('b', w.WORD), ('d', w.WORD), ('bytes', c.c_ubyte * 8)]
    class File(c.Structure):
        _fields_ = [('size', w.DWORD), ('path', w.LPCWSTR), ('handle', w.HANDLE), ('subject', c.c_void_p)]
    class Trust(c.Structure):
        _fields_ = [('size', w.DWORD), ('callback', c.c_void_p), ('client', c.c_void_p),
                    ('ui', w.DWORD), ('revocation', w.DWORD), ('choice', w.DWORD),
                    ('file', c.POINTER(File)), ('action', w.DWORD), ('state', w.HANDLE),
                    ('url', w.LPWSTR), ('flags', w.DWORD), ('context', w.DWORD), ('settings', c.c_void_p)]
    class Certificate(c.Structure):
        _fields_ = [('size', w.DWORD), ('certificate', c.c_void_p)]
    class Signer(c.Structure):
        _fields_ = [('size', w.DWORD), ('time', w.FILETIME), ('count', w.DWORD),
                    ('chain', c.POINTER(Certificate))]
    class AttributeTag(c.Structure):
        _fields_ = [('attributes', w.DWORD), ('tag', w.DWORD)]

    check(c.sizeof(Guid) == 16 and c.sizeof(File) == 32 and c.sizeof(Trust) == 88)
    kernel = c.WinDLL('kernel32.dll', winmode=0x800, use_last_error=True)
    win = c.WinDLL('wintrust.dll', winmode=0x800, use_last_error=True)
    crypt = c.WinDLL('crypt32.dll', winmode=0x800, use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    create.restype = w.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = [w.HANDLE], w.BOOL
    information = kernel.GetFileInformationByHandleEx
    information.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    information.restype = w.BOOL
    verify_trust = win.WinVerifyTrust
    verify_trust.argtypes = [w.HWND, c.POINTER(Guid), c.POINTER(Trust)]
    verify_trust.restype = c.c_long
    provider = win.WTHelperProvDataFromStateData
    provider.argtypes, provider.restype = [w.HANDLE], c.c_void_p
    signer = win.WTHelperGetProvSignerFromChain
    signer.argtypes, signer.restype = [c.c_void_p, w.DWORD, w.BOOL, w.DWORD], c.POINTER(Signer)
    get_name = crypt.CertGetNameStringW
    get_name.argtypes = [c.c_void_p, w.DWORD, w.DWORD, c.c_void_p, w.LPWSTR, w.DWORD]
    get_name.restype = w.DWORD

    # Share-read only denies mutation/deletion while verification uses this same
    # handle. OPEN_REPARSE_POINT + the actual handle attributes reject links.
    handle = create(str(path.absolute()), 0x80000000, 1, None, 3, 0x200000, None)
    check(handle not in (None, c.c_void_p(-1).value), 'Original native data file cannot be locked for verification.')
    stream = None
    try:
        attributes = AttributeTag()
        check(information(handle, 9, c.byref(attributes), c.sizeof(attributes)) and
              not attributes.attributes & (0x400 | 0x10), 'Original native data file is a reparse point or directory.')
        # open_osfhandle transfers handle ownership; the file stays locked until
        # the stream closes after state cleanup. No original library is loaded.
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        handle = None
        stream = os.fdopen(fd, 'rb')
        raw = stream.read(maximum_bytes + 1)
        check(512 <= len(raw) <= maximum_bytes and raw[:2] == b'MZ')
        digest = hashlib.sha256(raw).hexdigest()
        file = File(c.sizeof(File), str(path.absolute()), msvcrt.get_osfhandle(stream.fileno()), None)
        trust = Trust()
        trust.size, trust.ui, trust.choice = c.sizeof(Trust), 2, 1
        trust.file, trust.action, trust.flags = c.pointer(file), 1, 0x1010
        action = Guid.from_buffer_copy(uuid.UUID('00aac56b-cd44-11d0-8cc2-00c04fc295ee').bytes_le)
        try:
            result = verify_trust(c.c_void_p(-1), c.byref(action), c.byref(trust))
            check(result == 0 and trust.state, 'Original native publisher signature is not trusted offline.')
            state = provider(trust.state)
            chain = signer(state, 0, False, 0) if state else None
            check(chain and chain.contents.size >= c.sizeof(Signer) and
                  0 < chain.contents.count <= 32 and chain.contents.chain)
            cert = chain.contents.chain[0].certificate
            check(cert)
            length = get_name(cert, 4, 0, None, None, 0)
            check(1 < length <= 4096)
            buffer = c.create_unicode_buffer(length)
            check(get_name(cert, 4, 0, None, buffer, length) == length and buffer.value in publishers,
                  'Original native signature belongs to a different publisher.')
            stream.seek(0)
            check(hashlib.sha256(stream.read(maximum_bytes + 1)).hexdigest() == digest)
            return {'sha256': digest, 'bytes': len(raw), 'publisher': buffer.value,
                    'verification': 'Windows offline Authenticode', 'online_revocation_freshness': False}
        finally:
            if trust.state:
                trust.action = 2
                verify_trust(c.c_void_p(-1), c.byref(action), c.byref(trust))
    finally:
        if stream is not None:
            stream.close()
        if handle is not None:
            close(handle)
