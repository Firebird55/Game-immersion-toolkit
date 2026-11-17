"""Complete original-registry authoring evidence from one managed invocation.

The rows retain their package, export and native type. Duplicate performance
claims must not disappear merely because they name the same voice event.
"""
import json
from pathlib import Path
import re

from .preparation_errors import PreparationFailure

SCHEMA = 'nte-original-authoring-v1'
ROLES = {
    '/Script/HTGame.MessageDialogSoundData': 'voice',
    '/Script/HTGame.BubbleVoiceMsgDetail': 'voice',
    '/Script/HTGame.StorySequenceAndVedioData': 'sequence',
    '/Script/HTGame.VoiceCaptionData': 'caption',
    '/Script/HTGame.MediaFFmpegInfo': 'movie',
    '/Script/HTGame.TextTableData': 'text_registry',
}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate original authoring field or row')
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError('Non-finite original authoring value')


def read_original_authoring(path, *, schema_sha256, nonce, registry_sha256):
    """Reject stale, partial, ambiguous and incorrectly owned reader packets."""
    try:
        path = Path(path)
        if not path.is_file() or not 0 < path.stat().st_size <= 64*1024**2:
            raise ValueError()
        value = json.loads(path.read_bytes(), object_pairs_hook=_unique, parse_constant=_invalid_constant)
        if (not isinstance(value, dict) or set(value) != {
                'schema', 'complete', 'nonce', 'registry_sha256', 'schema_sha256', 'table_count', 'tables'}
                or value['schema'] != SCHEMA or value['complete'] is not True
                or value['nonce'] != nonce or value['schema_sha256'] != schema_sha256
                or value['registry_sha256'] != registry_sha256
                or not isinstance(nonce, str) or not re.fullmatch('[0-9a-f]{32}', nonce)
                or any(not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                       for digest in (schema_sha256, registry_sha256))
                or not isinstance(value['tables'], list) or not 0 < len(value['tables']) <= 256
                or type(value['table_count']) is not int or value['table_count'] != len(value['tables'])):
            raise ValueError()
        owners, total = set(), 0
        for table in value['tables']:
            if not isinstance(table, dict) or set(table) != {
                    'path', 'package', 'object_name', 'row_structure', 'role', 'rows'}:
                raise ValueError()
            package, name = table['package'], table['object_name']
            if (not isinstance(package, str) or len(package) > 1024
                    or not re.fullmatch(r'/Game/[A-Za-z0-9_/-]+', package)
                    or any(part in ('', '.', '..') for part in package[6:].split('/'))
                    or table['path'] != 'HT/Content/'+package[6:]+'.uasset'
                    or not isinstance(name, str) or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,255}', name)
                    or not isinstance(table['row_structure'], str)
                    or ROLES.get(table['row_structure']) != table['role']):
                raise ValueError()
            identity = (table['path'].casefold(), name.casefold())
            if identity in owners:
                raise ValueError()
            owners.add(identity)
            rows = table['rows']
            if (not isinstance(rows, dict) or len(rows) > 100_000
                    or any(not isinstance(key, str) or not 0 < len(key) <= 512
                           or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in key)
                           or not isinstance(row, dict) for key, row in rows.items())):
                raise ValueError()
            total += len(rows)
            if total > 500_000:
                raise ValueError()
        return value
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise PreparationFailure('game_metadata_unavailable',
            'Original NTE table ownership could not be verified. Retry preparation; '
            'the previous completed index is retained.') from None
