"""Validate and persist prepared dialogue without desktop tool imports."""
import json

from .atomic_files import replace, stage_file
from .local_game import LocalDialogue
from .languages import audio_locale

_SNAPSHOT_CHARS = 16 * 1024


def _snapshot_chunks(payload):
    """Keep the UTF-8 output chunks within 64 KiB, even for a large token."""
    parts, length = [], 0
    for fragment in json.JSONEncoder(ensure_ascii=False).iterencode(payload):
        size = len(fragment)
        if length + size > _SNAPSHOT_CHARS and parts:
            yield ''.join(parts).encode('utf-8')
            parts, length = [], 0
        if size > _SNAPSHOT_CHARS:
            for offset in range(0, size, _SNAPSHOT_CHARS):
                yield fragment[offset:offset + _SNAPSHOT_CHARS].encode('utf-8')
            continue
        parts.append(fragment)
        length += size
    if parts:
        yield ''.join(parts).encode('utf-8')


def write_payload(game, payload, locale, targets, output, *, reader_revision, check=None):
    """Validate and atomically publish the ordinary worker's exact UTF-8 payload."""
    if payload.get('format') != 2 or payload.get('game') != game or payload.get('source_locale') != locale or not payload.get('records'):
        raise ValueError('Incomplete official language snapshot')
    if game == 'genshin' and 'source_receipt' in payload:
        from .genshin_source_receipt import validate
        validate(payload['source_receipt'], publisher=payload.get('fingerprint'), region=payload.get('publisher_region'),
                 metadata_revision=payload.get('metadata_revision'))
    counts = dict.fromkeys(('voiced', 'unvoiced', 'unavailable', 'unknown'), 0)
    categories = {}
    for number, record in enumerate(payload['records']):
        if check is not None and number % 1024 == 0:
            check()
        source = record.get('source_text')
        if (record.get('source_locale') != locale or not isinstance(source, str) or not source.strip()
                or not isinstance(record.get('texts'), dict) or record['texts'].get(locale) != source
                or record.get('audio_locale') != audio_locale(locale, game)):
            raise ValueError('Incomplete game study text or mismatched language in prepared snapshot')
        validated = LocalDialogue(**record)
        record['voice_status'] = validated.voice_status
        counts[validated.voice_status] += 1
        category = categories.setdefault(validated.dialogue_kind or 'uncategorized', dict.fromkeys(counts, 0))
        category[validated.voice_status] += 1
    payload['dialogue_inventory'] = {'voice_counts': counts, 'categories': categories}
    payload['reader_revision'] = reader_revision
    payload['targets_requested'] = sorted(targets)
    with stage_file(output) as staged:
        with staged.open('wb', buffering=0) as stream:
            for chunk in _snapshot_chunks(payload):
                if check is not None:
                    check()
                if stream.write(chunk) != len(chunk):
                    raise OSError('Incomplete prepared language snapshot write')
        replace(staged, output, check=check)
