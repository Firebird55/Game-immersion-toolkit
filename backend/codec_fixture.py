"""Independently authored single-frame FLAC; no encoder, game or recording input."""
import hashlib
import struct

RATE, SAMPLES = 16000, 512


def crc(data, width, polynomial):
    value = 0
    for byte in data:
        value ^= byte << (width - 8)
        for _ in range(8):
            value = ((value << 1) ^ polynomial if value & (1 << (width - 1)) else value << 1) & ((1 << width) - 1)
    return value


def authored_flac():
    # FLAC verbatim subframe with a patterned non-silent mono signal. Expected
    # little-endian PCM is generated independently of the decoder under test.
    samples = [((index * 257 + 113) % 60001) - 30000 for index in range(SAMPLES)]
    pcm = struct.pack('<' + 'h' * SAMPLES, *samples)
    streaminfo = struct.pack('>HH', SAMPLES, SAMPLES) + b'\0' * 6
    streaminfo += ((RATE << 44) | (15 << 36) | SAMPLES).to_bytes(8, 'big')
    streaminfo += hashlib.md5(pcm).digest()  # Required FLAC STREAMINFO checksum, not a trust hash.
    # Fixed block size: code 9 = 256 * 2, rate from STREAMINFO, mono, 16 bits.
    header = bytes.fromhex('fff89008') + b'\0'
    header += bytes([crc(header, 8, 0x07)])
    frame = header + b'\x02' + struct.pack('>' + 'h' * SAMPLES, *samples)
    frame += crc(frame, 16, 0x8005).to_bytes(2, 'big')
    return b'fLaC\x80\x00\x00\x22' + streaminfo + frame, pcm
