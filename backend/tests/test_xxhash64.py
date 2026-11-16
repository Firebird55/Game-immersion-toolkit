"""Independent standard XXH64 vectors for publisher data integrity."""
from backend.xxhash64 import xxhash64, xxhash64_stream


def test_seed_zero_reference_vectors_cover_lanes_stripes_and_tails():
    # Independent seed-zero XXH64 reference results for owned byte sequences.
    expected = {0: 'ef46db3751d8e999', 1: 'e934a84adb052768', 3: 'e5c7bb4533bc65dd',
                4: 'ffced8604453cc1e', 7: '14cc643f630c72d2', 8: '884a173614b81b8d',
                31: 'c346d2b59b4d8ee1', 32: 'cbf59c5116ff32b4', 33: '0c535d1acafb8ead',
                63: 'e26aa9e2a95f8e4f', 64: 'f7c67301db6713f0', 65: 'c31eb63b2ae4465b',
                129: '0ba25dfd6e891fcf'}
    for length, digest in expected.items():
        raw = bytes(range(length))
        assert f'{xxhash64(raw):016x}' == digest
        for boundary in range(length + 1):
            assert f'{xxhash64_stream((raw[:boundary], b"", raw[boundary:])):016x}' == digest
        for width in (1, 7, 8, 31, 32, 33, 64):
            parts = (raw[pos:pos + width] for pos in range(0, length, width))
            assert f'{xxhash64_stream(parts):016x}' == digest


def test_streamed_reference_crosses_many_stripes_and_packet_boundaries():
    raw = bytes(index % 251 for index in range(65537))
    # Independently checked with the locked xxhash-wasm reference reader.
    expected = 0x8c8e0218a8ee0fee
    assert xxhash64(raw) == expected
    for width in (1, 17, 31, 32, 33, 4093, 65536):
        assert xxhash64_stream(memoryview(raw)[pos:pos + width] for pos in range(0, len(raw), width)) == expected
