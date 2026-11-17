"""Original training HUD roles, shared by desktop and portable capture hosts."""
from collections import defaultdict
import math
import json
import re
from hashlib import sha256

from .endfield_presentation import _box
from .endfield_sns_presentation import sns_record_signature
from .languages import normalize_text


SOURCE_ROLES = frozenset(('step_ctrl', 'step_layout', 'task_ctrl', 'task_layout', 'goal_ctrl',
    'tutorial_table', 'step_table', 'game_table', 'subgame_table', 'task_info_table', 'label_table'))


def validate_training_dialogue_ui(value):
    """Bound original UI provenance and references without changing dialogue rows."""
    def check(condition):
        if not condition:
            raise ValueError('Invalid original Endfield training UI metadata')

    def identity(text):
        check(isinstance(text, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,384}', text))
        return text

    def text(value, maximum=2048):
        check(isinstance(value, str) and value == value.strip() and 1 <= len(value) <= maximum
              and not any(char in value for char in '\0\r\n{}'))
        return value

    check(isinstance(value, dict) and set(value) == {'schema', 'revision', 'sources', 'locales', 'stages', 'goals'})
    check(type(value['schema']) is int and value['schema'] == 1)
    check(isinstance(value['revision'], str) and re.fullmatch(r'endfield-[0-9a-f]{64}', value['revision']))
    check(isinstance(value['sources'], dict) and set(value['sources']) == SOURCE_ROLES
          and all(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{32}', digest)
                  for digest in value['sources'].values()))
    check(isinstance(value['locales'], dict) and 1 <= len(value['locales']) <= 64)
    locales = {}
    for locale, config in value['locales'].items():
        check(isinstance(locale, str) and re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}', locale))
        check(isinstance(config, dict) and set(config) == {'titles', 'labels', 'profile'})
        check(isinstance(config['titles'], dict) and 1 <= len(config['titles']) <= 4096)
        titles = {}
        for owner, labels in config['titles'].items():
            check(isinstance(labels, list) and 1 <= len(labels) <= 64)
            titles[identity(owner)] = sorted(set(text(label, 256) for label in labels))
        check(isinstance(config['labels'], dict) and 1 <= len(config['labels']) <= 65536)
        labels = {identity(key): text(label, 256) for key, label in config['labels'].items()}
        check(all(key.startswith('endfield:DungeonCharTutorialStepTable:') for key in labels))
        check(isinstance(config['profile'], list) and len(config['profile']) <= 64)
        locales[locale] = {'titles': titles, 'labels': labels,
                           'profile': sorted(set(text(label, 256) for label in config['profile']))}
    check(isinstance(value['stages'], list) and 1 <= len(value['stages']) <= 16384)
    stages, seen = [], set()
    owners = {owner for config in locales.values() for owner in config['titles']}
    for stage in value['stages']:
        check(isinstance(stage, dict) and set(stage) == {'owner', 'stage', 'text_ids'})
        owner = identity(stage['owner'])
        check(owner in owners and type(stage['stage']) is int and 0 <= stage['stage'] < 65536)
        check(isinstance(stage['text_ids'], list) and 1 <= len(stage['text_ids']) <= 256)
        ids = [identity(key) for key in stage['text_ids']]
        check(len(set(ids)) == len(ids) and all(key.startswith('endfield:DungeonCharTutorialStepTable:') for key in ids))
        key = (owner, stage['stage'])
        check(key not in seen)
        seen.add(key)
        stages.append({'owner': owner, 'stage': stage['stage'], 'text_ids': ids})
    check(isinstance(value['goals'], list) and len(value['goals']) <= 65536)
    goals = []
    for goal in value['goals']:
        check(isinstance(goal, dict) and set(goal) == {'owner', 'texts'} and goal['owner'] in owners)
        check(isinstance(goal['texts'], dict) and set(goal['texts']) <= locales.keys())
        goals.append({'owner': goal['owner'], 'texts': {locale: text(body) for locale, body in goal['texts'].items()}})
    result = {'schema': 1, 'revision': value['revision'], 'sources': dict(value['sources']),
              'locales': locales, 'stages': sorted(stages, key=lambda row: (row['owner'], row['stage'])), 'goals': goals}
    check(len(json.dumps(result, ensure_ascii=True)) <= 8 * 1024**2)
    return result


def training_ui_signature(value):
    return sha256(json.dumps(validate_training_dialogue_ui(value), sort_keys=True,
                             separators=(',', ':')).encode()).hexdigest()


def compile_training_dialogue(value, records, display_locale):
    descriptor = validate_training_dialogue_ui(value)
    rows = {row['text_id']: row for row in records}
    if len(rows) != len(records):
        raise ValueError('Duplicate original Endfield training row')
    config = descriptor['locales'].get(display_locale)
    if config is None:
        raise ValueError('Unprepared Endfield training display locale')
    stages = []
    for stage in descriptor['stages']:
        if any(identity not in rows for identity in stage['text_ids']):
            raise ValueError('Original training stage references an absent prepared row')
        if stage['owner'] not in config['titles'] or any(identity not in config['labels'] for identity in stage['text_ids']):
            continue
        stages.append({'owner': stage['owner'], 'ids': stage['text_ids'],
                       'labels': [config['labels'][identity] for identity in stage['text_ids']]})
    return _compile_roles(records, display_locale, config['titles'], stages, descriptor['goals'], config['profile'])


def contains(longer, shorter):
    return any(tuple(longer[at:at + len(shorter)]) == tuple(shorter)
               for at in range(len(longer) - len(shorter) + 1))


def _compile_roles(records, locale, titles, stages, goals, profiles=()):
    normal = lambda text: normalize_text(text, locale)
    title_owners, labels, body_rows, goal_texts = defaultdict(set), set(), defaultdict(list), defaultdict(set)
    for owner, values in titles.items():
        for title in values:
            title_owners[normal(title)].add(owner)
    rows = {row['text_id']: row for row in records}
    for stage in stages:
        labels.update(normal(text) for text in stage['labels'])
        for identity in stage['ids']:
            body_rows[normal(rows[identity]['texts'].get(locale, ''))].append(identity)
    for goal in goals:
        text = goal['texts'].get(locale)
        if text and not any(token in text for token in ('{', '}')):
            goal_texts[goal['owner']].add(normal(text))
    other_kinds = defaultdict(list)
    for row in records:
        if row['dialogue_kind'] != 'tutorial_step':
            other_kinds[normal(row['texts'].get(locale, ''))].append(row['text_id'])
    return {'rows': rows, 'locale': locale, 'title_owners': title_owners,
            'labels': labels, 'body_rows': body_rows, 'stages': stages,
            'goals': goal_texts, 'other_kinds': other_kinds,
            'profiles': {normal(text) for text in profiles}}


def observe_training_dialogue(compiled, spans, size, *, dialogue_menu=False):
    empty = {'steps': [], 'goal_only_caption_keys': set(), 'header_owners': set(), 'body_groups': [], 'role_ids': set()}
    if dialogue_menu or not isinstance(spans, list) or len(spans) > 512:
        return empty
    try:
        width, height = size
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in size):
            return empty
        positioned = []
        for span in spans:
            if not isinstance(span, dict) or not isinstance(span.get('text'), str) or len(span['text']) > 2048:
                return empty
            text = span['text'].strip()
            if not text:
                continue
            box = _box(span, width, height)
            if box is None:
                return empty
            score = span.get('confidence')
            reliable = type(score) in (int, float) and math.isfinite(score) and .8 <= score <= 1
            positioned.append((normalize_text(text, compiled['locale']), box, reliable, text))
    except (TypeError, ValueError, OverflowError):
        return empty
    if len({key for key, box, _, _ in positioned if box[1] < .55 and key in compiled['profiles']}) >= 2:
        return empty
    headers = [(key, box) for key, box, reliable, _ in positioned
               if reliable and key in compiled['title_owners'] and box[0] < .20 and box[2] < .48
               and .10 <= box[1] < .42 and box[3] < .46]
    if len(headers) != 1:
        return empty
    key, header = headers[0]
    owners = compiled['title_owners'][key]
    result = {**empty, 'header_owners': owners}

    def paragraphs(lines):
        lines = sorted(lines, key=lambda row: (row[1][1], row[1][0]))
        groups = []
        for row in lines:
            if (groups and row[1][1] - groups[-1][-1][1][3] <= .030
                    and row[1][1] >= groups[-1][-1][1][1] - .002):
                groups[-1].append(row)
            else:
                groups.append([row])
        return groups

    # Independent left goal role: title/complete authored goal, never a source
    # for the bottom StepDesc or for predecessor state. Numeric progress has a
    # separate original node and cannot supply missing caption words.
    goal_lines = [row for row in positioned if row[1][0] < .45 and row[1][2] <= .50
                  and header[3] < row[1][1] < .72 and not row[0].isdigit()]
    goal_keys = set()
    expected_goals = set().union(*(compiled['goals'].get(owner, set()) for owner in owners))
    goal_lines.sort(key=lambda row: (row[1][1], row[1][0]))
    for start in range(len(goal_lines)):
        text = ''
        for end in range(start, min(start + 16, len(goal_lines))):
            row = goal_lines[end]
            if not row[2] or end > start and row[1][1] - goal_lines[end - 1][1][3] > .030:
                break
            text += row[0]
            if text in expected_goals:
                # A complete reference is role evidence, not a learning hit.
                goal_keys.add(text)
            if not any(wanted.startswith(text) for wanted in expected_goals):
                break
    body_lines = [row for row in positioned if .12 <= row[1][0] and row[1][2] <= .90
                  and .62 <= row[1][1] and row[1][3] < .92]
    bodies = []
    for group in paragraphs(body_lines):
        text = ''.join(row[0] for row in group)
        if all(row[2] for row in group) and len(text) >= 4 and text in compiled['body_rows']:
            bodies.append((text, ' '.join(row[3] for row in group)))
    result['goal_only_caption_keys'] = goal_keys - {key for key, _ in bodies}
    if len(bodies) != 1:
        return result
    body, raw = bodies[0]
    owner_bodies = {identity for stage in compiled['stages'] if stage['owner'] in owners for identity in stage['ids']}
    if (compiled['other_kinds'].get(body)
            or not any(identity in owner_bodies for identity in compiled['body_rows'][body])):
        return result
    result['body_groups'] = [raw]
    result['role_ids'] = owner_bodies.intersection(compiled['body_rows'][body])
    minimum = 5 if re.search(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]', body) else 12
    if len(body) < minimum:
        return result  # Preserve the ordinary source-language short guard.
    # Columns can wrap an authored label. A merged/partial/unknown label fails;
    # the classifier never fills in OCR's missing words.
    label_lines = sorted([row for row in positioned if .25 <= row[1][0] and row[1][2] <= .88
                          and .025 <= row[1][1] and row[1][3] < .23],
                         key=lambda row: ((row[1][0] + row[1][2]) / 2, row[1][1]))
    columns = []
    for row in label_lines:
        center = (row[1][0] + row[1][2]) / 2
        if columns and abs(center - columns[-1][0]) < .018:
            columns[-1][1].append(row)
        else:
            columns.append((center, [row]))
    if not 2 <= len(columns) <= 5:
        return result
    observed = []
    for center, column in columns:
        column.sort(key=lambda row: row[1][1])
        label = ''.join(row[0] for row in column)
        if (not all(row[2] for row in column) or label not in compiled['labels']
                or len(column) > 3 or any(row[1][2] - row[1][0] > .16 for row in column)):
            return result
        observed.append(label)
    if any(not .025 <= second[0] - first[0] <= .13 for first, second in zip(columns, columns[1:])):
        return result
    ids = {identity for stage in compiled['stages'] if stage['owner'] in owners
           and contains(tuple(normalize_text(text, compiled['locale']) for text in stage['labels']), observed)
           for identity in stage['ids']
           if normalize_text(compiled['rows'][identity]['texts'].get(compiled['locale'], ''), compiled['locale']) == body}
    choices = [compiled['rows'][identity] for identity in ids]
    if (not choices or len({sns_record_signature(row) for row in choices}) != 1
            or any(row['voice_status'] != 'unvoiced' or row.get('audio') is not None
                   or row.get('text_capture_verified') is not True or row.get('requires_previous')
                   or row.get('text_binding_unresolved') or row.get('player_voice')
                   or row.get('dialogue_kind') != 'tutorial_step'
                   or 'tip' not in row.get('channels', ()) for row in choices)):
        return result
    result['steps'] = [{'text_id': min(ids), 'source_ocr': raw, 'observed_labels': observed}]
    return result
