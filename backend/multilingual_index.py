"""Locale-tagged official text matching with one verified source performance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading

from rapidfuzz import fuzz, process

from .languages import audio_locale, normalize_text, resolve_locale, study_language
from .models import TextMatch
from .local_game import (dialogue_voice_status, dialogue_audio_scope, dialogue_capture_channels,
    DEFAULT_CAPTURE_CHANNELS, original_recording_context, validate_original_recording_metadata)
from .textmaps import display_text


def candidates(lines):
    cleaned = [display_text(line) for line in lines if display_text(line)]
    rows = [display_text(part) for line in cleaned for part in re.split(r'\s*[~～]\s*|(?<=[.!?。！？])\s+(?=[^\W\d_])|(?<=[。！？])\s*(?=[A-Za-z])|(?<=[.!?])\s*(?=[\u3400-\u9fff])', line) if display_text(part)]
    values = [' '.join(cleaned)] if cleaned else []
    for first in range(len(rows)):
        for last in range(first + 1, min(len(rows), first + 8) + 1):
            value = ' '.join(rows[first:last])
            values.append(value)
            if re.search(r'[:：]', value):
                values.append(re.split(r'[:：]', value, maxsplit=1)[1].strip())
    return list(dict.fromkeys(values))


class MultilingualTextIndex:
    def __init__(self, game: str, directory: Path, *, autoload=True):
        self.game, self.path = game, directory / 'textmap.json'
        self.ready = False
        self.player_voice = 'unconfigured'
        self.capture_unvoiced = False
        self.capture_missing_audio = False
        self.capture_text_only = False
        self.audio_omitted_count = 0
        self.publisher_generation = None
        self.publisher_request_sha256 = None
        self.target_locale = 'en'
        self.source_locale = ''
        self.entry_count = self.audio_count = 0
        self.message, self.state = 'Prepare this game language in Setup', 'not_ready'
        self.lock = threading.RLock()
        self._load_lock = threading.RLock()
        self._records, self._lookup, self._context_pairs, self._context_firsts = [], {}, {}, {}
        self._capture_channels = {}
        self._unvoiced_lookup = {}
        self._missing_audio_lookup = {}
        self._missing_audio_blockers = {}
        self._predecessor_aliases = {}
        self._mission_predecessors = {}
        self._full_frame_veto = {}
        self._player_frame_veto = {}
        self._wuwa_name_templates = None
        self.voice_counts = {status: 0 for status in ('voiced', 'unvoiced', 'unavailable', 'unknown')}
        self.dialogue_coverage = {}
        self._signature = None
        self.snapshot_metadata = {}
        self._sns_compiled = None
        self._training_compiled = ()
        if autoload:
            self.load()

    def _publisher_context(self, row):
        # The host binds a validated source before exposing this index. Hash
        # the complete authored occurrence, including player/audio provenance;
        # do not add toolkit fields to immutable publisher rows or approvals.
        return {'publisher_generation': self.publisher_generation,
                'publisher_request_sha256': self.publisher_request_sha256,
                'publisher_occurrence_sha256': hashlib.sha256(json.dumps(row, sort_keys=True,
                    separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                    if self.publisher_generation is not None else None}

    def publish(self, candidate):
        """Activate the already validated generation without parsing it again."""
        with self._load_lock, self.lock:
            candidate.path.replace(self.path)
            settings = {'game', 'path', 'lock', '_load_lock', 'player_voice',
                        'target_locale', 'capture_unvoiced', 'capture_missing_audio'}
            self.__dict__.update({key: value for key, value in candidate.__dict__.items()
                                  if key not in settings})

    def voice_snapshot(self, signature):
        with self.lock:
            if self.ready and self._signature == signature:
                return {**self.snapshot_metadata, 'records': self._records}
        return None

    def load(self):
        # Several status/capture/preparation threads can observe one replacement.
        # Only one owns JSON decoding and lookup construction for that generation.
        with self._load_lock:
            return self._load_snapshot()

    def _load_snapshot(self):
        try:
            info = self.path.stat()
            signature = (info.st_size, info.st_mtime_ns)
            if signature == self._signature:
                return True
            payload = json.loads(self.path.read_text(encoding='utf-8'))
            if payload.get('format') != 2 or payload.get('game') != self.game:
                raise ValueError('Unsupported game language snapshot')
            if not payload.get('records'):
                raise ValueError('Prepared language table is empty; rebuilding is required')
            locale = payload['source_locale']
            content_mode = payload.get('content_mode')
            if content_mode not in {None, 'text', 'text-audio'}:
                raise ValueError('Unsupported game data content mode')
            requested_text_only = content_mode == 'text'
            study_language(locale)
            if self.game == 'endfield' and 'publisher_world_dialogue_ui' in payload:
                from .endfield_presentation import validate_world_dialogue_ui
                payload['publisher_world_dialogue_ui'] = validate_world_dialogue_ui(payload['publisher_world_dialogue_ui'])
            if self.game == 'endfield' and 'publisher_sns_dialogue_ui' in payload:
                from .endfield_sns_presentation import validate_sns_dialogue_ui
                payload['publisher_sns_dialogue_ui'] = validate_sns_dialogue_ui(payload['publisher_sns_dialogue_ui'])
                if payload['publisher_sns_dialogue_ui']['revision'] != payload.get('fingerprint'):
                    raise ValueError('Original Baker UI and prepared records have different revisions')
            if self.game == 'endfield' and 'publisher_training_dialogue_ui' in payload:
                from .endfield_training_presentation import validate_training_dialogue_ui
                payload['publisher_training_dialogue_ui'] = validate_training_dialogue_ui(payload['publisher_training_dialogue_ui'])
                if payload['publisher_training_dialogue_ui']['revision'] != payload.get('fingerprint'):
                    raise ValueError('Original training UI and prepared records have different revisions')
            lookup, unvoiced_lookup, context_pairs, capture_channels, full_frame_veto = {}, {}, {}, {}, {}
            player_frame_veto = {}
            missing_audio_lookup = {}
            missing_audio_count = 0
            missing_audio_blockers = {}
            eligible_missing_keys = {}
            for row in payload['records']:
                if (row.get('text_capture_verified') is True and not row.get('text_binding_unresolved')
                        and (row.get('voice_status', 'unknown') in {'unknown', 'unavailable'}
                             or requested_text_only and row.get('audio_omitted_by_request') is True) and not row.get('audio')):
                    texts, anchors = row.get('texts'), row.get('ocr_texts', {})
                    if not isinstance(texts, dict) or not isinstance(anchors, dict):
                        raise ValueError('Invalid authored dialogue text metadata')
                    for language, text in texts.items():
                        for value in [text, *anchors.get(language, [])]:
                            eligible_missing_keys.setdefault(language, set()).add(normalize_text(display_text(value), language))
            voice_counts = dict.fromkeys(self.voice_counts, 0)
            coverage = {}
            predecessor_aliases = {}
            mission_parents = {row.get('previous_text_id') for row in payload['records']
                               if self.game == 'endfield' and row.get('dialogue_kind') == 'conversation'
                               and row.get('previous_text_id')}
            mission_predecessors = {}
            for row in payload['records']:
                if row.get('source_locale') != locale or not isinstance(row.get('source_text'), str) or not row['source_text']:
                    raise ValueError('Incomplete game study text')
                if not isinstance(row.get('texts'), dict) or row['texts'].get(locale) != row['source_text']:
                    raise ValueError('Official text locales do not agree')
                if row.get('audio_locale') != audio_locale(locale, self.game):
                    raise ValueError('Original voice locale does not match study text')
                row.setdefault('audio_omitted_by_request', False)
                row.setdefault('source_voice_binding', None)
                row['voice_status'] = dialogue_voice_status(row.get('audio'), row.get('voice_status'),
                    audio_omitted_by_request=row.get('audio_omitted_by_request', False), source_voice_binding=row.get('source_voice_binding'))
                if row.get('audio_omitted_by_request') and not requested_text_only:
                    raise ValueError('Omitted original audio requires an explicit text-only snapshot')
                if requested_text_only and row.get('audio'):
                    raise ValueError('Text-only snapshots must not contain playable audio references')
                if type(row.get('text_capture_verified', False)) is not bool:
                    raise ValueError('Invalid authored text capture evidence')
                row.setdefault('audio_scope', 'paragraph' if self.game == 'beyond'
                               and row['text_id'].endswith(':complete') and row.get('audio') else 'line')
                row['audio_scope'] = dialogue_audio_scope(row.get('audio'), row['audio_scope'])
                validate_original_recording_metadata(row.get('original_recording_sha256'), row.get('original_speaker_id'),
                                                    row['voice_status'], row['audio_scope'])
                voice_counts[row['voice_status']] += 1
                category = row.get('dialogue_kind') or 'uncategorized'
                if not isinstance(category, str):
                    raise ValueError('Invalid dialogue category')
                counts = coverage.setdefault(category, dict.fromkeys(voice_counts, 0))
                counts[row['voice_status']] += 1
                # Historical membership includes every official record, even
                # rows excluded from OCR matching because they have no audio.
                channels = dialogue_capture_channels(row.get('channels'))
                row['channels'] = sorted(channels)
                for identity in [row['text_id'], *(row.get('member_text_ids') or [])]:
                    previous = capture_channels.get(identity)
                    capture_channels[identity] = channels if previous is None else previous | channels
                if self.game == 'endfield' and row.get('member_text_ids'):
                    predecessor_aliases[row['text_id']] = tuple(row['member_text_ids'])
                if mission_parents and category == 'conversation' and row['voice_status'] == 'voiced' and (
                        row['text_id'] in mission_parents or mission_parents.intersection(row.get('member_text_ids') or [])):
                    key = normalize_text(row['source_text'], locale)
                    mission_predecessors.setdefault(key, []).append(row)
                if self.game == 'genshin' and row['voice_status'] == 'voiced' and category == 'conversation':
                    variant = re.fullmatch(r'(genshin:[0-9]+):(male|female)', row['text_id'])
                    if variant and variant[2] == row.get('player_voice'):
                        predecessor_aliases[row['text_id']] = (variant[1],)
                if row['voice_status'] != 'voiced':
                    veto = (player_frame_veto.setdefault(row['player_voice'], {})
                            if row.get('player_voice') else full_frame_veto)
                    for language, text in row['texts'].items():
                        for value in [text, *row.get('ocr_texts', {}).get(language, [])]:
                            veto.setdefault(language, set()).add(normalize_text(display_text(value), language))
                # Authored silence does not resolve an unsupported text branch.
                # Keep its inventory/veto, but neither its diagnostic source nor
                # an otherwise valid translation can identify a capturable row.
                missing_audio = row['voice_status'] in {'unknown', 'unavailable'} or bool(row.get('audio_omitted_by_request'))
                if not missing_audio:
                    # A short voiced caption still conflicts with text-only
                    # capture even if it is too short to identify its recording.
                    for language, text in row['texts'].items():
                        if language not in eligible_missing_keys:
                            continue
                        for value in [text, *row.get('ocr_texts', {}).get(language, [])]:
                            key = normalize_text(display_text(value), language)
                            if key in eligible_missing_keys[language]:
                                missing_audio_blockers.setdefault(row.get('player_voice'), {}).setdefault(language, {}).setdefault(key, set()).add(row.get('previous_text_id'))
                if missing_audio:
                    # Keep unverified and unresolved duplicates in this lookup
                    # as vetoes. Their spelling cannot certify another row.
                    destination = missing_audio_lookup
                    if row.get('text_capture_verified') and not row.get('text_binding_unresolved') and not row.get('audio_omitted_by_request'):
                        missing_audio_count += 1
                elif row.get('text_binding_unresolved'):
                    continue
                else:
                    destination = unvoiced_lookup if row['voice_status'] == 'unvoiced' else lookup
                for language, text in row['texts'].items():
                    for value in [text, *row.get('ocr_texts', {}).get(language, [])]:
                        key = normalize_text(display_text(value), language)
                        if missing_audio and key not in eligible_missing_keys.get(language, ()):
                            continue
                        # NTE's isolated narrow-panel context reads full records;
                        # predecessor metadata must not widen its ordinary lane.
                        if len(key) >= 2 or key and row.get('previous_text_id') and self.game != 'nte':
                            destination.setdefault(language, {}).setdefault(key, []).append(row)
                    if not missing_audio and row.get('member_text_ids') and (anchors := row.get('ocr_texts', {}).get(language)):
                        last = anchors[0]
                        if last and text.endswith(' ' + last):
                            first = text[:-len(last)-1]
                            pair = (language, normalize_text(first, language), normalize_text(last, language))
                            context_pairs.setdefault(pair, []).append(row)
            names = None
            if self.game == 'wuwa':
                from .wuthering_text_templates import PlayerNameTemplates
                names = PlayerNameTemplates(payload['records'])
            if self.game == 'endfield' and 'publisher_sns_dialogue_ui' in payload:
                from .endfield_sns_presentation import compile_sns_chains
                for display_locale in payload['publisher_sns_dialogue_ui']['locales']:
                    compile_sns_chains(payload['publisher_sns_dialogue_ui'], payload['records'], locale,
                                       self.player_voice, display_locale=display_locale)
            training_compiled = ()
            if self.game == 'endfield' and 'publisher_training_dialogue_ui' in payload:
                from .endfield_training_presentation import compile_training_dialogue
                training_compiled = tuple(compile_training_dialogue(payload['publisher_training_dialogue_ui'],
                    payload['records'], display_locale) for display_locale in payload['publisher_training_dialogue_ui']['locales'])
            with self.lock:
                self._wuwa_name_templates = names
                self.source_locale, self._records, self._lookup = locale, payload['records'], lookup
                self._capture_channels = capture_channels
                self._unvoiced_lookup = unvoiced_lookup
                self._missing_audio_lookup = missing_audio_lookup
                self._missing_audio_blockers = missing_audio_blockers
                self.missing_audio_count = missing_audio_count
                self._full_frame_veto = full_frame_veto
                self._player_frame_veto = player_frame_veto
                self._predecessor_aliases = predecessor_aliases
                self._mission_predecessors = mission_predecessors
                self.voice_counts, self.dialogue_coverage = voice_counts, coverage
                self._context_pairs = context_pairs
                self._context_firsts = {}
                for language, first, _ in context_pairs:
                    self._context_firsts.setdefault(language, set()).add(first)
                self.entry_count = len(payload['records'])
                self.audio_count = sum(bool(r.get('audio')) for r in self._records)
                self.capture_text_only = requested_text_only
                self.audio_omitted_count = sum(r.get('audio_omitted_by_request') is True for r in self._records)
                self.ready = True
                capabilities = payload.get('capture_capabilities') or {}
                text_only = capabilities.get('voiced') is False and capabilities.get('unvoiced') is True
                self.state = 'ready' if self.audio_count else 'text_only' if self.capture_text_only else 'unvoiced_only' if text_only else 'missing_voice'
                self.message = (f'{self.entry_count:,} official text lines; audio not requested' if self.capture_text_only
                    else payload.get('message', f'{self.entry_count:,} official lines; {self.audio_count:,} original voices'))
                self.snapshot_metadata = {key: value for key, value in payload.items() if key != 'records'}
                self._training_compiled = training_compiled
                self._signature = signature
            return True
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.message = 'Previous complete language snapshot retained' if self.ready else str(error)
            return False

    def status(self):
        return {'ready': self.ready, 'state': self.state, 'message': self.message,
                'entry_count': self.entry_count, 'audio_count': self.audio_count, 'source_locale': self.source_locale,
                'unvoiced_count': self.voice_counts['unvoiced'], 'voice_counts': dict(self.voice_counts),
                'missing_audio_count': getattr(self, 'missing_audio_count', 0),
                'dialogue_coverage': self.dialogue_coverage,
                'capture_capabilities': self.snapshot_metadata.get('capture_capabilities')}

    @staticmethod
    def authored_scene(text_id):
        return text_id.rsplit(':', 1)[0] if re.fullmatch(r'heavyrain:\d+:[a-f0-9]{8}', text_id) else None

    def _frame_vetoes(self):
        selected = ([self._player_frame_veto.get(self.player_voice, {})]
                    if self.player_voice in {'female', 'male'} else self._player_frame_veto.values())
        return [self._full_frame_veto, *selected]

    def _authored_keys(self, key, locale):
        aliases = self._wuwa_name_templates.keys(key, locale) if self._wuwa_name_templates else ()
        return {key, *aliases}

    def _vetoed(self, key, locale):
        keys = self._authored_keys(key, locale)
        return any(keys.intersection(table.get(locale, ())) for table in self._frame_vetoes())

    def _veto_locales(self):
        return {locale for table in self._frame_vetoes() for locale in table}

    def equivalent_caption_occurrence(self, first, second):
        """Compare complete current source rows, never only displayed fields.

        Authored ordering may distinguish two otherwise identical occurrences.
        Unknown/missing audio has no shared None performance identity.
        """
        if (first.kind != 'exact' or second.kind != 'exact'
                or first.voice_status not in {'voiced', 'unvoiced'}
                or first.voice_status != second.voice_status
                or first.source_text != second.source_text
                or first.source_locale != self.source_locale or second.source_locale != self.source_locale):
            return False
        with self.lock:
            key = normalize_text(first.source_text or '', self.source_locale)
            candidates = [*self._lookup.get(self.source_locale, {}).get(key, ()),
                          *self._unvoiced_lookup.get(self.source_locale, {}).get(key, ())]
            identities = {first.text_id, second.text_id}
            found = {identity: [] for identity in identities}
            for row in candidates:
                identity = row['text_id']
                if identity in found and (not row.get('player_voice') or row['player_voice'] == self.player_voice):
                    if row not in found[identity]:
                        found[identity].append(row)
            if any(len(rows) != 1 for rows in found.values()):
                return False
            def content(identity):
                return {name: value for name, value in found[identity][0].items()
                        if name not in {'text_id', 'previous_text_id', 'requires_previous'}}
            return content(first.text_id) == content(second.text_id)

    def mission_anchor_ids(self, text):
        """A short observed caption can narrow the next line without exporting this take."""
        with self.lock:
            displayed = ' '.join(display_text(text).casefold().split())
            key = normalize_text(displayed, self.source_locale)
            if not key or self._vetoed(key, self.source_locale):
                return frozenset()
            # Preserve meaningful punctuation in the full caption. A label or
            # fragment never establishes the first member of a short pair.
            matches = {row['text_id'] for row in self._lookup.get(self.source_locale, {}).get(key, ())
                       if ' '.join(row['source_text'].casefold().split()) == displayed
                       and (not row.get('player_voice') or row['player_voice'] == self.player_voice)}
            parents = {row['text_id'] for row in self._mission_predecessors.get(key, ())}
            return frozenset(matches) if matches <= parents else frozenset()

    def match_endfield_world_caption(self, spans, image_size):
        """A stateless source-owned world view can distinguish its profile copy."""
        if self.game != 'endfield':
            return None
        from .endfield_presentation import observe_world_caption, world_ui_signature
        with self.lock:
            metadata = self.snapshot_metadata.get('publisher_world_dialogue_ui')
            signature = self._signature
        proof = observe_world_caption(metadata, spans, image_size)
        if proof is None:
            return None
        with self.lock:
            if (signature != self._signature or
                    proof.ui_signature != world_ui_signature(self.snapshot_metadata.get('publisher_world_dialogue_ui'))):
                return None
            return self.match_lines([proof.caption], exact_only=True, channel='dialogue',
                                    _endfield_world_speaker=proof.original_speaker_id)

    def match_endfield_sns_dialogue(self, spans, image_size, *, direct=(), dialogue_menu=False):
        """Resolve each complete written body at its own observed source position."""
        if self.game != 'endfield' or not self.ready or not self.capture_unvoiced or dialogue_menu:
            return []
        from .endfield_sns_presentation import (
            compile_sns_chains, observe_sns_dialogue, sns_record_signature, sns_ui_signature)
        try:
            direct = tuple(direct)
            with self.lock:
                metadata = self.snapshot_metadata.get('publisher_sns_dialogue_ui')
                ui_signature = sns_ui_signature(metadata)
                signature = self._signature
                key = (signature, ui_signature, self.source_locale, self.player_voice)
                if self._sns_compiled is None or self._sns_compiled[0] != key:
                    self._sns_compiled = (key, tuple(compile_sns_chains(
                        metadata, self._records, self.source_locale, self.player_voice, display_locale=locale)
                        for locale in metadata['locales']))
                compiled = self._sns_compiled[1]
            observations = [observation for display in compiled for observation in observe_sns_dialogue(
                display, spans, image_size, dialogue_menu=dialogue_menu)]
            if not observations:
                return []
            with self.lock:
                if (signature != self._signature or ui_signature != sns_ui_signature(
                        self.snapshot_metadata.get('publisher_sns_dialogue_ui'))):
                    return []
                rows = {row['text_id']: row for row in self._records}
                positions = {}
                for observation in observations:
                    positions.setdefault(observation.line_range, []).append(observation)
                # Different cell partitions or translations at the same physical
                # position remain ambiguous, including overlapping long bodies.
                conflicts = {first for first in positions for second in positions
                             if first != second and first[0] < second[1] and second[0] < first[1]}
                result, used = [], set()
                for position, choices in sorted(positions.items()):
                    if position in conflicts:
                        continue
                    signatures = {sns_record_signature(rows[choice.text_id]) for choice in choices}
                    if len(signatures) != 1:
                        continue
                    observation = min(choices, key=lambda choice: choice.text_id)
                    row = rows[observation.text_id]
                    existing = next((hit for hit in direct
                        if hit.kind == 'exact' and hit.voice_status == 'unvoiced'
                        and hit.source_locale == self.source_locale and hit.text_id in rows
                        and sns_record_signature(rows[hit.text_id]) in signatures
                        and normalize_text(hit.source_ocr, self.source_locale)
                            == normalize_text(observation.source_ocr, self.source_locale)), None)
                    if existing is not None:
                        hit = existing
                    else:
                        if row.get('dialogue_kind') != 'message_system':
                            continue  # Context reorders existing ordinary hits; it never admits new ones.
                        target = resolve_locale(self.target_locale, row['texts'])
                        hit = TextMatch(game=self.game, text_id=row['text_id'], english=row.get('english') or row['source_text'],
                            chinese=row.get('chinese', ''), source_ocr=observation.source_ocr, score=100, kind='exact',
                            source_language=study_language(self.source_locale), source_locale=self.source_locale,
                            source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
                            translation_locale=target or self.target_locale,
                            translation_text=row['texts'].get(target, '') if target else '',
                            speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese'),
                            voice_status=row['voice_status'], dialogue_kind=row['dialogue_kind'],
                            text_capture_verified=row['text_capture_verified'], audio_scope=row['audio_scope'],
                            audio_omitted_by_request=row.get('audio_omitted_by_request', False), source_voice_binding=row.get('source_voice_binding'),
                            **self._publisher_context(row))
                    if hit.text_id not in used:
                        result.append(hit)
                        used.add(hit.text_id)
                return result
        except (ValueError, KeyError, TypeError, OverflowError):
            return []

    def match_endfield_training_dialogue(self, spans, image_size, *, direct=(), dialogue_menu=False):
        """Return only complete positioned StepDesc hits and predecessor input.

        Task objectives never become training hits or temporal anchors. Missing
        presentation metadata, changed controls and menus fail closed.
        """
        empty = {'hits': [], 'body_groups': [], 'owners': ()}
        if self.game != 'endfield' or not self.ready or not self.capture_unvoiced or dialogue_menu:
            return empty
        from .endfield_training_presentation import observe_training_dialogue
        from .endfield_sns_presentation import sns_record_signature
        with self.lock:
            observations = [observe_training_dialogue(compiled, spans, image_size, dialogue_menu=dialogue_menu)
                            for compiled in self._training_compiled]
            groups = list(dict.fromkeys(group for observation in observations for group in observation['body_groups']))
            owners = tuple(sorted({owner for observation in observations for owner in observation['header_owners']}))
            if len(groups) != 1:
                return empty
            rows = {row['text_id']: row for row in self._records}
            role_signatures = {sns_record_signature(rows[identity]) for observation in observations
                               for identity in observation['role_ids']}
            hits = {hit.text_id: hit for hit in direct if hit.dialogue_kind == 'tutorial_step'
                    and hit.kind == 'exact' and hit.voice_status == 'unvoiced' and hit.text_id in rows
                    and sns_record_signature(rows[hit.text_id]) in role_signatures
                    and any(normalize_text(hit.source_ocr, self.source_locale) == normalize_text(group, self.source_locale)
                            for group in groups)}
            choices = [step for observation in observations for step in observation['steps']]
            if choices and len({sns_record_signature(rows[choice['text_id']]) for choice in choices}) == 1:
                choice = min(choices, key=lambda choice: choice['text_id'])
                row = rows[choice['text_id']]
                existing = next((hit for hit in hits.values()
                                 if sns_record_signature(rows[hit.text_id]) == sns_record_signature(row)), None)
                if existing is None:
                    target = resolve_locale(self.target_locale, row['texts'])
                    hit = TextMatch(game=self.game, text_id=row['text_id'], english=row.get('english') or row['source_text'],
                        chinese=row.get('chinese', ''), source_ocr=choice['source_ocr'], score=100, kind='exact',
                        source_language=study_language(self.source_locale), source_locale=self.source_locale,
                        source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
                        translation_locale=target or self.target_locale,
                        translation_text=row['texts'].get(target, '') if target else '',
                        speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese'),
                        voice_status=row['voice_status'], dialogue_kind=row['dialogue_kind'],
                        text_capture_verified=row['text_capture_verified'], audio_scope=row['audio_scope'],
                        audio_omitted_by_request=row.get('audio_omitted_by_request', False), source_voice_binding=row.get('source_voice_binding'),
                        **self._publisher_context(row))
                    hits[hit.text_id] = hit
                    # The complete UI selected this authored occurrence. Do not
                    # emit a second globally coalesced alias for the same body.
                    for identity, other in list(hits.items()):
                        if identity != hit.text_id and self.equivalent_caption_occurrence(other, hit):
                            del hits[identity]
            return {'hits': list(hits.values()), 'body_groups': groups, 'owners': owners}

    def match_lines(self, lines, threshold=88, exact_only=False, channel='dialogue', context_groups=(), multiple=False,
                    previous_text_id=None, _endfield_world_speaker=None):
        hits, ambiguous = [], []
        if (_endfield_world_speaker is not None and
                (self.game != 'endfield' or previous_text_id is not None or not exact_only or channel != 'dialogue')):
            return [] if multiple else None
        with self.lock:
            sources = ([display_text(' '.join(lines))]
                       if previous_text_id or _endfield_world_speaker is not None else candidates(lines))
            predecessors = {previous_text_id, *self._predecessor_aliases.get(previous_text_id, ())}
            if self.game == 'genshin' and previous_text_id:
                variant = re.fullmatch(r'(genshin:[0-9]+):(male|female)', previous_text_id)
                if variant and variant[2] != self.player_voice:
                    return [] if multiple else None
            # A known silent/unknown page may contain a shorter spoken sentence.
            # Preserve the complete observation before candidate splitting so a
            # crop or a fuzzy match cannot turn its fragment into that voice.
            nonvoiced_observations = [(locale, normalize_text(source, locale))
                for source in sources for locale in self._veto_locales()
                if self._vetoed(normalize_text(source, locale), locale)]
            for source in sources:
                lookups = [(locale, values, False) for locale, values in self._lookup.items()]
                if self.capture_unvoiced:
                    lookups += [(locale, values, True) for locale, values in self._unvoiced_lookup.items()]
                if self.capture_missing_audio or self.capture_text_only:
                    lookups += [(locale, values, True) for locale, values in self._missing_audio_lookup.items()]
                for locale, lookup, silent in lookups:
                    missing_lookup = lookup is self._missing_audio_lookup.get(locale)
                    if previous_text_id and locale != self.source_locale:
                        continue
                    key, score = normalize_text(source, locale), 100.
                    if self.game in {'starrail', 'genshin', 'endfield'}:
                        # Short interjections recur across unrelated scenes,
                        # including movies without per-caption voice bindings.
                        # Their spelling alone cannot identify a performance.
                        minimum = 5 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', key) else 12
                        if len(key) < minimum and not previous_text_id and not missing_lookup:
                            continue
                    matched_keys = self._authored_keys(key, locale)
                    rows = [row for matched in matched_keys for row in lookup.get(matched, [])]
                    # HEAVY RAIN paginates some authored paragraphs at runtime.
                    # A sufficiently long, exact contiguous page can identify
                    # the whole bound performance; never infer page audio cuts.
                    minimum = 12 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', key) else 24
                    if not silent and self.game == 'heavyrain' and channel == 'dialogue' and len(key) >= minimum:
                        rows = [row for text, matches in lookup.items() if key in text for row in matches]
                        matched_keys = {text for text in lookup if key in text}
                    if not silent and not rows and not exact_only and not previous_text_id and len(key) >= 8:
                        matches = process.extract(key, lookup.keys(), scorer=fuzz.ratio, score_cutoff=max(88, threshold), limit=2)
                        if matches and (len(matches) == 1 or matches[1][1] < matches[0][1] - 2):
                            rows, score = lookup[matches[0][0]], matches[0][1]
                            matched_keys = {matches[0][0]}
                        elif matches:
                            ambiguous.append(source)
                    if previous_text_id:
                        rows = [r for r in rows if r.get('previous_text_id') in predecessors]
                    if not silent and rows and (
                            any(self._vetoed(key, locale) for key in matched_keys)
                            or any(normalize_text(source, observed_locale) in observed
                                   for observed_locale, observed in nonvoiced_observations)):
                        # This text cannot identify spoken versus silent/UI
                        # presentation, even with silent capture switched off.
                        # Keep it ambiguous rather than selecting the silent
                        # duplicate after suppressing its voice candidate.
                        ambiguous.append(source)
                        continue
                    rows = [r for r in rows if channel is None or channel in r.get('channels', ['dialogue', 'tip', 'cinematic', 'gameplay'])]
                    # ZZZ's authored M/F subtitles can themselves identify a
                    # performance. Use the configured Proxy only when the
                    # observed caption leaves more than one variant possible.
                    if self.game != 'zzz' or len(rows) > 1:
                        selected = [r for r in rows if not r.get('player_voice') or r['player_voice'] == self.player_voice]
                        if (self.game == 'wuwa' and any(r.get('player_voice') for r in rows)
                                and (self.player_voice not in {'female', 'male'} or not selected)):
                            # A complete authored caption with an unresolved
                            # Rover branch still owns its observed words. Do
                            # not let filtering it borrow another recording
                            # through one of its shorter sentence fragments.
                            ambiguous.append(source)
                            continue
                        rows = selected
                    if not previous_text_id and any(row.get('requires_previous') for row in rows):
                        ambiguous.append(source)
                        continue
                    if missing_lookup and not self.capture_missing_audio and not any(r.get('audio_omitted_by_request') for r in rows):
                        continue
                    if any(row['voice_status'] in {'unknown', 'unavailable'} or row.get('audio_omitted_by_request') for row in rows):
                        complete = normalize_text(display_text(' '.join(lines)), locale)
                        blockers = [self._missing_audio_blockers.get(None, {})]
                        blockers += ([self._missing_audio_blockers.get(self.player_voice, {})]
                                     if self.player_voice in {'male', 'female'} else
                                     [values for player, values in self._missing_audio_blockers.items() if player])
                        name_conflict = self._wuwa_name_templates and len(matched_keys) > 1 and any(
                            (not voiced.get('player_voice') or voiced['player_voice'] == self.player_voice)
                            and (not previous_text_id or voiced.get('previous_text_id') in predecessors)
                            for matched in matched_keys for voiced in self._lookup.get(locale, {}).get(matched, []))
                        if (key != complete or name_conflict or any(not row.get('text_capture_verified')
                                or row.get('text_binding_unresolved') for row in rows)
                                or any((bool(conflicts) if not previous_text_id else
                                        bool(predecessors.intersection(conflicts)))
                                       for values in blockers
                                       for conflicts in [values.get(locale, {}).get(key, set())])):
                            ambiguous.append(source)
                            continue
                    if _endfield_world_speaker is not None:
                        # All existing caption, channel, player, predecessor and
                        # missing/unknown vetoes above still govern this frame.
                        # Only a verified world speaker's voiced profile peer is
                        # excluded; no takes, translations or member IDs merge.
                        if not any(row.get('dialogue_kind') == 'conversation' and row['voice_status'] == 'voiced'
                                   and row.get('original_speaker_id') == _endfield_world_speaker for row in rows):
                            continue
                        rows = [row for row in rows if not (row.get('dialogue_kind') == 'operator_voice'
                                and row['voice_status'] == 'voiced'
                                and row.get('original_speaker_id') == _endfield_world_speaker)]
                    # Silent prompts can repeat in different scenes with different
                    # official translations. Audio=None is not one shared identity.
                    def identity(row):
                        if row.get('audio_omitted_by_request'):
                            return ('omitted-by-request', row['text_id'], json.dumps(row, sort_keys=True))
                        if self.game == 'endfield' and (context := original_recording_context(row)) is not None:
                            return ('verified-original-export', context)
                        return (json.dumps(row.get('audio'), sort_keys=True), row['source_text'],
                                json.dumps(row['texts'], sort_keys=True)
                                if row['voice_status'] != 'voiced' or row['audio_scope'] in {'paragraph', 'context'} else '',
                                row['voice_status'])
                    identities = {identity(r) for r in rows}
                    if self.game == 'heavyrain' and len(identities) > 1 and score == 100 and context_groups:
                        rows = [row for row in rows if self.authored_scene(row['text_id']) in context_groups]
                        identities = {identity(row) for row in rows}
                    if len(identities) != 1:
                        if len(identities) > 1:
                            ambiguous.append(source)
                        continue
                    row = rows[0]
                    if _endfield_world_speaker is not None:
                        choices = [r for r in rows if r.get('dialogue_kind') == 'conversation'
                                   and r.get('original_speaker_id') == _endfield_world_speaker]
                        if not choices:
                            continue
                        row = choices[0]
                    target = resolve_locale(self.target_locale, row['texts'])
                    hits.append(TextMatch(game=self.game, text_id=row['text_id'], english=row.get('english') or row['source_text'],
                        chinese=row.get('chinese', ''), source_ocr=source, score=score, kind='exact' if score == 100 else 'fuzzy',
                        source_language=study_language(self.source_locale), source_locale=self.source_locale,
                        source_text=row['source_text'], audio_locale=row['audio_locale'], texts=row['texts'],
                        translation_locale=target or self.target_locale, translation_text=row['texts'].get(target, '') if target else '',
                        speaker_english=row.get('speaker_english'), speaker_chinese=row.get('speaker_chinese'),
                        voice_status=row['voice_status'], dialogue_kind=row.get('dialogue_kind'),
                        text_capture_verified=row.get('text_capture_verified', False),
                        audio_scope=row['audio_scope'], audio_omitted_by_request=row.get('audio_omitted_by_request', False),
                        source_voice_binding=row.get('source_voice_binding'), **self._publisher_context(row)))
        if multiple:
            # Retain independent visible speakers, but never turn a wrapped
            # caption's fragment into another performance. The same ambiguity
            # guard used by single-caption matching applies to every result.
            result = {}
            for hit in hits:
                key = normalize_text(hit.source_ocr)
                if any(other.score >= max(92, threshold) and key != (larger := normalize_text(other.source_ocr))
                       and key in larger for other in hits):
                    continue
                if any(key in normalize_text(text) for text in ambiguous):
                    continue
                peers = {other.text_id for other in hits if normalize_text(other.source_ocr) == key
                         and other.score == hit.score}
                if len(peers) == 1:
                    result.setdefault(hit.text_id, hit)
            return list(result.values())
        if not hits:
            return None
        best = max(hits, key=lambda hit: (hit.score, len(normalize_text(hit.source_ocr))))
        key = normalize_text(best.source_ocr, 'zh-Hans')
        longer = [hit for hit in hits if hit.score >= max(92, threshold)
                  and len(normalize_text(hit.source_ocr, 'zh-Hans')) >= max(len(key) * 1.5, len(key) + 8)
                  and key in normalize_text(hit.source_ocr, 'zh-Hans')]
        if longer:
            best = max(longer, key=lambda hit: (len(normalize_text(hit.source_ocr)), hit.score))
        key = normalize_text(best.source_ocr, 'zh-Hans')
        if any(len(normalize_text(text, 'zh-Hans')) >= len(key)
               and key in normalize_text(text, 'zh-Hans') for text in ambiguous):
            return None
        peers = [hit for hit in hits if hit.score == best.score and len(normalize_text(hit.source_ocr)) == len(normalize_text(best.source_ocr))]
        if len({hit.text_id for hit in peers}) != 1:
            return None
        return best

    def match_unvoiced_lines(self, lines):
        """Match text-only presentations outside the normal subtitle lanes.

        The ordinary matcher still resolves collisions with voiced records;
        this must not turn a voiced choice or a partial page into silent text.
        """
        if not self.capture_unvoiced:
            return []
        return [hit for hit in self.match_lines(lines, exact_only=True, channel=None, multiple=True)
                if hit.voice_status == 'unvoiced' and hit.kind == 'exact']

    def match_missing_audio_lines(self, lines):
        """Preserve verified complete captions without asserting spoken silence."""
        if not self.capture_missing_audio and not self.capture_text_only:
            return []
        return [hit for hit in self.match_lines(lines, exact_only=True, channel=None, multiple=True)
                if (self.capture_missing_audio and hit.voice_status in {'unknown', 'unavailable'}
                    or self.capture_text_only and hit.audio_omitted_by_request) and hit.text_capture_verified
                and hit.kind == 'exact']

    def match_full_frame_voice_lines(self, lines):
        """Floating dialogue must not match short labels, choices or unknown UI.

        A choice can repeat a later voiced response. Its text remains a veto
        even when unvoiced capture is disabled; text alone cannot identify
        which presentation is visible. The ordinary crop shares that veto.
        """
        from .steam_games import STEAM_GAMES
        spec = STEAM_GAMES.get(self.game)
        songs = self.game == 'wuwa' and self.snapshot_metadata.get(
            'publisher_song_voices', self.snapshot_metadata.get('publisher_song_cues', 0))
        if self.game != 'endfield' and not songs and (not spec or not spec.floating_dialogue):
            return []
        with self.lock:
            hits = self.match_lines(lines, exact_only=True, channel=None, multiple=True)
            result = []
            for hit in hits:
                if self.game == 'endfield':
                    top = hit.dialogue_kind == 'conversation' and 'cinematic' in self._capture_channels.get(hit.text_id, ())
                    if not hit.text_id.startswith('endfield:film:') and not top:
                        continue
                if self.game == 'wuwa' and (not hit.text_id.startswith('wuwa:music:') or hit.dialogue_kind != 'music_subtitle'):
                    continue
                text = hit.source_ocr
                minimum = 6 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', text) else 12
                if (hit.voice_status == 'voiced' and len(normalize_text(text)) >= minimum
                        and not any(self._vetoed(normalize_text(text, locale), locale)
                                    for locale in self._veto_locales())):
                    result.append(hit)
            return result

    def context_fragments(self, lines):
        """Recognize an observed first cue without choosing its performance."""
        result = set()
        with self.lock:
            for text in candidates(lines):
                for locale, firsts in self._context_firsts.items():
                    key = normalize_text(text, locale)
                    if key in firsts:
                        result.add((locale, key))
        return tuple(sorted(result))

    def match_context(self, previous, lines):
        """Resolve two exact observed cues only through an authored context pair."""
        hits = {}
        with self.lock:
            for text in candidates(lines):
                for locale, first in previous:
                    for row in self._context_pairs.get((locale, first, normalize_text(text, locale)), []):
                        hit = self.match_lines([row['texts'][locale]], exact_only=True)
                        if hit and hit.text_id == row['text_id']:
                            hits[hit.text_id] = hit.model_copy(update={'source_ocr': first + ' ' + text})
        return next(iter(hits.values())) if len(hits) == 1 else None

    def match_line_groups(self, groups, threshold=88, channel='cinematic', context_groups=()):
        result = {}
        for group in groups:
            hit = self.match_lines([group], threshold, channel=channel, context_groups=context_groups)
            if hit:
                result.setdefault(hit.text_id, hit)
        return list(result.values())

    def match_simultaneous_lines(self, lines, threshold=88):
        return self.match_lines(lines, threshold=threshold, multiple=True)

    def match_text(self, text, threshold=88, channel='dialogue'):
        return self.match_lines([text], threshold, channel=channel)

    def is_capture_text(self, text_id, _english, channel):
        with self.lock:
            return channel in self._capture_channels.get(text_id, ())

    def resolve_display_name(self, _candidates):
        return None
