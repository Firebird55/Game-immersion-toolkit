"""Complete original package controls required before accepting an AKPK master.

No network, source activation or audio playback happens in this module. A
caller must supply its current original CRC-checked index and complete original
VFS file bytes. The complete publisher file MD5 is checked before any bank is
decoded. Candidate values and original media are never returned in the proof.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import struct

from . import endfield_vfs as vfs
from .endfield_client_source import check

MAX_CONTROL = 16 * 1024**2


def validate(candidate, common, index, block, name, payload):
    check(isinstance(common, vfs.IndexParameters) and type(block) is int and block in (101, 102, 103, 104))
    required = {1, 21, 101, 102, 103, 104}
    check(required <= common.directories.keys())
    parameters = vfs.Parameters(common.key, {n: common.directories[n] for n in required},
                                candidate.multiplier, candidate.xor_constant, common.protocol)
    files = vfs.parse_index(index, common, block)
    selected = [row for row in files if row.name == name]
    check(len(selected) == 1, 'Original audio-master control has no unique VFS owner.')
    file = selected[0]
    check(isinstance(payload, bytes) and 12 <= len(payload) == file.size <= MAX_CONTROL and
          len(file.content_hashes) == 2 and
          hashlib.md5(payload).hexdigest() == file.content_hashes[1],
          'Original complete audio-master control MD5 or size differs.')
    check(payload[:4] == b':)xD', 'Audio-master control must exercise the original custom package header.')
    # payload is the complete VFS file after its outer stream layer, as required
    # by that file's authored content hash. Do not apply its original chunk
    # offset/nonce a second time.
    view = replace(file, offset=0, nonce=None, chunk_size=file.size)
    hashes, banks = hashlib.sha256(), []

    class ControlPackage(vfs.Package):
        def _bank(self, identity, offset, size):
            check(8 <= size <= MAX_CONTROL)
            original = self.source.read(offset, size)
            plain = vfs.xor_data(original, identity, self.parameters)
            check(plain[:4] == b'BKHD')
            at, sections = 0, 0
            while at < len(plain):
                check(at + 8 <= len(plain))
                _kind, length = struct.unpack_from('<4sI', plain, at)
                check(length <= len(plain) - at - 8)
                at += 8 + length
                sections += 1
            check(at == size and sections > 0)
            hashes.update(struct.pack('<QI', identity, size))
            hashes.update(hashlib.sha256(plain).digest())
            banks.append(sections)
            return super()._bank(identity, offset, size)

    package = ControlPackage(vfs.PackageSource(io.BytesIO(payload), view, parameters), parameters)
    check(banks, 'Original audio-master control does not contain a complete bank.')
    return parameters, {'schema': 1, 'original_index_sha256': hashlib.sha256(index).hexdigest(),
                        'original_file_md5': file.content_hashes[1], 'original_file_bytes': len(payload),
                        'block': block, 'complete_banks': len(banks), 'complete_bank_sections': sum(banks),
                        'decoded_banks_sha256': hashes.hexdigest(), 'media_entries': len(package.entries),
                        'media_playback_verified': False}
