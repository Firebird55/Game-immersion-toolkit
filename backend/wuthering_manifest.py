"""Read Kuro release metadata with explicit parameters and host cryptography."""

import base64
import binascii
import json

from .preparation_errors import PreparationFailure


def decode_manifest(raw, parameters, crypto):
    """Request ENTRY parameters only for a valid encrypted response envelope."""
    try:
        text = raw.decode('utf-8-sig')
        if text.lstrip().startswith('{'):
            return json.loads(text)
        cipher = base64.b64decode(text.strip(), validate=True)
        if not cipher or len(cipher) % 16:
            raise ValueError('Invalid encrypted ENTRY framing')
    except (UnicodeError, ValueError, binascii.Error) as error:
        raise PreparationFailure('publisher_metadata_invalid',
            'The Wuthering release-metadata response is invalid. Existing prepared text and audio are unchanged.',
            previous_snapshot_retained=True) from error

    key, iv = parameters()
    try:
        decoded = crypto.block_cipher('AES', 'CBC', key, cipher, iv=iv)
        padding = decoded[-1] if len(decoded) == len(cipher) else 0
        if not 1 <= padding <= 16 or decoded[-padding:] != bytes([padding]) * padding:
            raise ValueError('Invalid ENTRY padding')
        result = json.loads(decoded[:-padding])
        if not isinstance(result, dict):
            raise ValueError('Invalid ENTRY JSON object')
        return result
    except (UnicodeError, ValueError) as error:
        raise PreparationFailure('publisher_format_key_unresolved',
            'The verified ENTRY input cannot read the current Wuthering release metadata. The current manifest key/IV source must be verified before updating; existing text and audio are unchanged.',
            previous_snapshot_retained=True) from error
