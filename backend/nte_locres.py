"""Read original NTE 10100 localization members acquired from publisher archives."""
import base64
import re

from Crypto.Cipher import AES

from .nte_archive_metadata import check as metadata_check
from .nte_publisher_pak import Reader, check, MEMBER_LIMIT
from .preparation_errors import PreparationFailure

MAGIC = bytes.fromhex('0e147475674a03fc4a15909dc3377f1b')
STRING_LIMIT = 2 * 1024**2
COUNT_LIMIT = 2_000_000


class LocalizationParameterMismatch(PreparationFailure):
    """A complete known-layout member rejected the candidate split marker."""

    def __init__(self):
        super().__init__('game_metadata_unavailable',
            'Compatible NTE text information could not be verified. Retry preparation; '
            'the previous completed library is retained.')


def parse(data, parameter=None):
    """Retain namespaces, authored keys and source hashes, never just display text."""
    check(isinstance(data, bytes) and 41 <= len(data) <= MEMBER_LIMIT)
    reader = Reader(data)
    check(reader.read(16) == MAGIC and reader.number('B') == 3 and reader.number() == 10100)
    encrypted = reader.number()
    check(encrypted in (0, 1))
    strings_offset = reader.number('q')
    entries, namespaces = reader.count(COUNT_LIMIT), reader.count(COUNT_LIMIT)
    check(reader.position <= strings_offset <= len(data) - 4)
    key_position = reader.position
    reader.position = strings_offset
    count = reader.count(COUNT_LIMIT)
    if encrypted:
        metadata_check(isinstance(parameter, str) and re.fullmatch(r'0x[0-9a-fA-F]{64}', parameter))
        cipher = AES.new(bytes.fromhex(parameter[2:]), AES.MODE_ECB)
    strings, parameter_mismatch = [], False
    for _ in range(count):
        value = reader.string(STRING_LIMIT)
        if encrypted:
            try:
                raw = base64.b64decode(value.replace('-', '+').replace('_', '/'), validate=True)
            except (ValueError, UnicodeError):
                metadata_check(False)
            metadata_check(bool(raw) and len(raw) % 16 == 0)
            plain = cipher.decrypt(raw)
            end = plain.find(b'HottaLocresSplit')
            if end < 0:
                parameter_mismatch = True
                value = ''
            else:
                try:
                    value = plain[:end].decode('utf-8')
                except UnicodeError:
                    metadata_check(False)
        strings.append(value)
        reader.number()  # Serialized reference count; selection uses authored keys.
    reader.finish()
    reader.position = key_position
    seen_namespaces, result = set(), []
    for _ in range(namespaces):
        reader.number('I')  # FTextKey hash.
        namespace = reader.string(STRING_LIMIT)
        check(namespace not in seen_namespaces)
        seen_namespaces.add(namespace)
        seen_keys = set()
        for _ in range(reader.count(entries - len(result))):
            reader.number('I')
            key = reader.string(STRING_LIMIT)
            source_hash, index = reader.number('I'), reader.number()
            check(key not in seen_keys and 0 <= index < len(strings))
            seen_keys.add(key)
            result.append({'ns': namespace, 'key': key, 'value': strings[index], 'source_hash': source_hash})
    check(len(result) == entries and reader.position == strings_offset)
    if parameter_mismatch:
        raise LocalizationParameterMismatch()
    return result
