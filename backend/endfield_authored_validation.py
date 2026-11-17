"""Original table-field certification, deliberately separate from admission.

The original tables can establish written references and configured primary
voice paths without accepting an AssetBundle master. They cannot establish
graph occurrence/order, UI geometry, cinematic ownership or local playback.
This envelope is intentionally not a format-2 capture snapshot.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re

FORMAT = 'endfield-authored-table-validation-v1'
UNFULFILLED = ('decoded_dialog_graph_ownership', 'decoded_presentation_ui_ownership',
               'cinematic_text_and_voice_ownership', 'original_voice_media_presence',
               'complete_canonical_capture_admission')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class _TableOnly:
    """Do not inherit optional graph/UI/network methods from another catalog."""
    __slots__ = ('base', 'files', 'values', 'controls')

    def __init__(self, catalog):
        self.base, self.files = catalog, getattr(catalog, 'files', {})
        self.values, self.controls = {}, {}

    def file(self, path, *, optional=False):
        found = re.fullmatch(r'TableCfg/([A-Za-z0-9_]+)\.json', path)
        if found is None:
            raise ValueError('Use an authored Endfield table root')
        if path not in self.values:
            value = self.base.file(path, optional=optional)
            if not isinstance(value, dict):
                raise ValueError('Original Endfield table root is not a map')
            name = 'Data/TableCfg/' + found[1] + '.bytes'
            original = self.files.get(name)
            control = None
            if original is not None:
                if (original.name != name or len(original.content_hashes) != 2 or
                        re.fullmatch('[0-9a-f]{32}', original.content_hashes[1]) is None or original.size < 12):
                    raise ValueError('Original table control is invalid')
                control = {'name': name, 'md5': original.content_hashes[1], 'bytes': original.size}
            self.controls[path] = {'root': found[1], 'file_control': control,
                                   'absent_optional_entry': original is None and optional and not value}
            self.values[path] = value
        return self.values[path]


def build(catalog, source_locale, target_locales, *, content_mode='text'):
    """Build canonical ordinary facts; no voice inventory or bundle decoder."""
    # Reuse the current owned reducers, not a second interpretation of authored
    # narrative tables. Their optional graph hooks are absent from this view.
    from . import endfield_assets as authored
    target_locales = tuple(target_locales)
    if source_locale not in authored.SUPPORTED_LOCALES or content_mode not in {'text', 'text-audio'}:
        raise ValueError('Choose an official Endfield study language and mode')
    if any(code not in authored.TEXT_LOCALES for code in target_locales):
        raise ValueError('Choose official Endfield translation languages')
    view = _TableOnly(catalog)
    tables = {}
    for locale in sorted({source_locale, *target_locales}):
        table = view.file('TableCfg/I18nTextTable_' + authored.TEXT_LOCALES[locale] + '.json')
        if not table or any(not isinstance(value, str) for value in table.values()):
            raise ValueError('Original selected Endfield text table is incomplete')
        tables[locale] = table
    audio = view.file('TableCfg/AudioDialog.json')
    if not audio:
        raise ValueError('Original AudioDialog metadata is incomplete')
    paths, audio_ids = authored.audio_paths(audio), authored.audio_id_paths(audio)
    durations = authored.primary_voice_durations(audio, source_locale)
    warnings = []
    dialogs = authored.authored_dialogues(view, radio_evidence=authored.radio_evidence(view, audio))
    dialogs.update(authored.narrative_dialogues(view, warnings))
    rows = authored.dialogue_records(dialogs, paths, tables, source_locale, {},
                                    audio_ids=audio_ids, primary_durations=durations)
    if not rows or len(rows) > 1_000_000:
        raise ValueError('Original ordinary Endfield records are missing or oversized')
    by_id = {row['text_id']: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError('Repeated original ordinary record identity')
    reverse = defaultdict(list)
    for identity, path in audio_ids.items():
        reverse[path].append(identity)
    bindings = {}
    for identity, row in dialogs.items():
        key = str(row.get('dialogText', {}).get('id'))
        texts = {locale: authored.display_text(values.get(key, '')) for locale, values in tables.items()}
        for gender, path, _ in authored._performances(row, paths, audio_ids, texts):
            text_id = 'endfield:' + identity + (':' + gender if gender else '')
            record = by_id.get(text_id)
            if record is None or path is None or record['voice_status'] == 'unvoiced':
                continue
            source = 'voice/' + authored.VOICE_LOCALES[source_locale] + '/' + path.replace('\\', '/').lower()
            bindings[text_id] = {'kind': 'configured-primary-reference',
                'source': source, 'file_id': f'{authored.voice_hash(source):016x}', 'locale': record['audio_locale'],
                'audio_dialog_ids': sorted(reverse[path]), 'player_voice': record.get('player_voice'),
                'declared_positive_primary_duration': durations.get(path),
                'media_presence_verified': False, 'caller_voice_enabled_verified': False}
    result = {'format': FORMAT, 'game': 'endfield', 'source_locale': source_locale,
        'target_locales': list(target_locales), 'content_mode': content_mode, 'records': rows,
        'configured_voice_bindings': bindings, 'original_table_controls': view.controls,
        'records_sha256': hashlib.sha256(_json(rows)).hexdigest(),
        'ordinary_record_count': len(rows), 'dialogue_kinds': dict(Counter(row['dialogue_kind'] for row in rows)),
        'voice_status_without_media_inventory': dict(Counter(row['voice_status'] for row in rows)),
        'coverage_warnings': warnings, 'graph_ui_admission_verified': False,
        'snapshot_ready': False, 'unfulfilled_evidence': list(UNFULFILLED)}
    result['facts_sha256'] = hashlib.sha256(_json(result)).hexdigest()
    return result


def validate_from_source(ctx, identity, common, reference, records):
    """Reopen the explicit original receipt before validating candidate fields.

    Catalog rechecks the original client, resource generation, request, complete
    typed index and each consumed whole table. Neither ambient legacy data nor
    a self-reported candidate digest can replace those checks.
    """
    from .endfield_text_source import Catalog
    catalog = Catalog(ctx, identity, common, reference)
    facts = build(catalog, ctx.request.source_locale, ctx.request.target_locales,
                  content_mode=ctx.request.content_mode)
    report = validate_candidate(facts, records)
    report['original_source_reference'] = reference
    return report


def validate_candidate(facts, records):
    """Certify only fields proven by the original ordinary table projection.

    Additional graph/speaker/recording metadata is preserved and reported as
    unverified; it is never silently accepted, discarded or guessed here.
    """
    if (facts.get('format') != FORMAT or facts.get('snapshot_ready') is not False or
            hashlib.sha256(_json({key: value for key, value in facts.items() if key != 'facts_sha256'})).hexdigest() != facts.get('facts_sha256') or
            hashlib.sha256(_json(facts['records'])).hexdigest() != facts['records_sha256']):
        raise ValueError('Original authored facts are not a valid limited-scope certificate')
    expected = {row['text_id']: row for row in facts['records']}
    actual = {row['text_id']: row for row in records}
    if len(actual) != len(records) or actual.keys() != expected.keys():
        raise ValueError('Candidate ordinary record identities differ from original tables')
    counts = Counter()
    for identity, source in expected.items():
        row = actual[identity]
        if row.get('voice_status') not in {'voiced', 'unvoiced', 'unavailable', 'unknown'}:
            raise ValueError('Candidate has an invalid voice state')
        for field in ('source_locale', 'source_text', 'texts', 'english', 'chinese', 'dialogue_kind', 'audio_locale'):
            if row.get(field) != source.get(field):
                raise ValueError('Candidate original authored field differs: ' + field)
        for field in ('previous_text_id', 'original_speaker_id', 'player_voice'):
            if source.get(field) is not None and row.get(field) != source[field]:
                raise ValueError('Candidate explicit table-owned field differs: ' + field)
            if source.get(field) is None and row.get(field) is not None:
                counts['unverified_' + field] += 1
        if source['dialogue_kind'] != 'conversation' and row.get('channels') != source.get('channels'):
            raise ValueError('Candidate table presentation channels differ')
        if row.get('channels') != source.get('channels'):
            counts['unverified_graph_channels'] += 1
        if source.get('voice_status') == 'unvoiced' and row.get('voice_status') != 'unvoiced':
            raise ValueError('Candidate replaced an authored unvoiced state')
        if source.get('voice_status') != 'unvoiced' and row.get('voice_status') == 'unvoiced':
            counts['unverified_silence_claims'] += 1
        audio = row.get('audio')
        if audio is not None:
            binding = facts['configured_voice_bindings'].get(identity)
            if not isinstance(audio, dict) or binding is None:
                raise ValueError('Candidate audio has no original primary-source reference')
            for field in ('source', 'file_id', 'locale'):
                if audio.get(field) != binding[field]:
                    raise ValueError('Candidate configured original voice reference differs: ' + field)
            counts['configured_audio_references_verified'] += 1
        if row.get('voice_status') == 'voiced':
            counts['playback_presence_not_certified'] += 1
    return {'format': FORMAT, 'game': 'endfield', 'source_locale': facts['source_locale'],
        'ordinary_records_verified': len(records), 'text_fields_verified': True,
        'candidate_sha256': hashlib.sha256(_json(records)).hexdigest(),
        'configured_voice_bindings': len(facts['configured_voice_bindings']),
        'unverified_claim_counts': dict(counts), 'graph_ui_admission_verified': False,
        'snapshot_ready': False, 'unfulfilled_evidence': list(UNFULFILLED)}
