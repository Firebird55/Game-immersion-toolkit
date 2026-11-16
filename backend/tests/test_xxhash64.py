"""Independent standard XXH64 vectors for publisher data integrity."""
from backend.xxhash64 import xxhash64


def test_seed_zero_reference_vectors_cover_lanes_stripes_and_tails():
    # Independent seed-zero XXH64 reference results for owned byte sequences.
    expected = {0: 'ef46db3751d8e999', 1: 'e934a84adb052768', 3: 'e5c7bb4533bc65dd',
                4: 'ffced8604453cc1e', 7: '14cc643f630c72d2', 8: '884a173614b81b8d',
                31: 'c346d2b59b4d8ee1', 32: 'cbf59c5116ff32b4', 33: '0c535d1acafb8ead',
                63: 'e26aa9e2a95f8e4f', 64: 'f7c67301db6713f0', 65: 'c31eb63b2ae4465b',
                129: '0ba25dfd6e891fcf'}
    for length, digest in expected.items():
        assert f'{xxhash64(bytes(range(length))):016x}' == digest
