"""Authored positioned-span policy fixtures; not real game/SDK OCR acceptance."""
from .android_probe import _library
from .caption_layout import native_nte_caption
from .prepared_session import PreparedCaptureSession


def span(text, left, top, width, *, size=(1920, 1080), height=.025):
    w, h = size
    return {'text': text, 'confidence': .99, 'bounding_rect': {
        'x1': left*w, 'y1': top*h, 'x2': (left+width)*w, 'y2': top*h,
        'x3': (left+width)*w, 'y3': (top+height)*h, 'x4': left*w, 'y4': (top+height)*h}}


def row(identity, text, *, kind='conversation', previous=None, status='voiced'):
    return dict(text_id=identity, english=text, chinese='', source_locale='en', source_text=text,
        texts={'en': text}, audio_locale='en', audio={'authored-fixture': True} if status == 'voiced' else None,
        voice_status=status, dialogue_kind=kind, channels=['dialogue'], previous_text_id=previous,
        original_speaker_id='chr_authored_guide' if identity.startswith('world:') else None)


def training_proof(root):
    from .endfield_training_presentation import SOURCE_ROLES, validate_training_dialogue_ui
    prefix = 'endfield:DungeonCharTutorialStepTable:'
    body = 'Use the battle skill to protect the ally.'
    records = []
    for owner in ('first', 'second'):
        for suffix, text in (('body', body), ('tail', 'Another complete authored training instruction.')):
            value = row(prefix + owner + '_' + suffix, text, kind='tutorial_step', status='unvoiced')
            value.update(channels=['tip'], text_capture_verified=True, texts={'en': text, 'fr': owner + ' ' + text})
            records.append(value)
    descriptor = {'schema': 1, 'revision': 'endfield-' + '3'*64,
        'sources': {role: '4'*32 for role in SOURCE_ROLES},
        'locales': {'en': {'titles': {'first': ['Operator Guide: First'], 'second': ['Operator Guide: Second']},
            'labels': {item['text_id']: 'Combo Skill' if item['text_id'].endswith('tail') else
                       'Battle Skill' if 'first_' in item['text_id'] else 'Ultimate' for item in records},
            'profile': ['Profile', 'Voice Information']}},
        'stages': [{'owner': owner, 'stage': 0, 'text_ids': [prefix + owner + '_body', prefix + owner + '_tail']}
                   for owner in ('first', 'second')], 'goals': [{'owner': 'first', 'texts': {'en': body}}]}
    library = _library(root / 'input', game='endfield', records=records, clips={},
        metadata={'fingerprint': descriptor['revision'], 'publisher_training_dialogue_ui': descriptor})
    positioned = [span('Operator Guide: First', 80/1920, 250/1080, 600/1920),
        span('Battle Skill', 850/1920, 105/1080, 100/1920),
        span('Combo Skill', 958/1920, 105/1080, 100/1920), span(body, 400/1920, 820/1080, 1120/1920)]
    results = {}
    for condition in ('bottom', 'left', 'unpositioned', 'opt_out'):
        session = PreparedCaptureSession(root / condition);session.import_library(library)
        session.update_settings({'capture_unvoiced': condition != 'opt_out'});scope = session.start()
        lines = positioned if condition != 'left' else [*positioned[:-1], span(body, 70/1920, 400/1080, 750/1920)]
        emitted = []
        for sequence in (1, 2):
            emitted += session.observe(scope, sequence, [item['text'] for item in lines], channel='fullframe',
                now=sequence*.1, presentation_lines=lines if condition != 'unpositioned' else None,
                frame_size=(1920, 1080))
        if condition == 'bottom':
            results['endfield_training_original_identity'] = len(emitted) == 1 and emitted[0]['text_id'] == records[0]['text_id']
            results['endfield_training_original_fields'] = bool(emitted and emitted[0]['texts'] == records[0]['texts']
                and not emitted[0]['has_audio'] and session.index.snapshot_metadata['publisher_training_dialogue_ui']
                == validate_training_dialogue_ui(descriptor))
        else:
            results['endfield_training_' + condition + '_rejected'] = not emitted and session.history.count() == 0 \
                and all(context.anchor is None for context in session.floating_contexts.values())
    return results


def run(root):
    root.mkdir(parents=True, exist_ok=True)
    _library(root / 'different-take', duration=.24)
    different = root / 'different-take/authored-tone.wav'
    body = 'A complete authored caption distinguishes these original presentations.'
    records = [row('world:spoken', body), row('world:profile', body, kind='operator_voice')]
    descriptor = {'schema': 1, 'revision': 'endfield-' + '1'*64,
        'sources': {role: '2'*32 for role in ('dialog', 'top', 'profile', 'dialog_ctrl', 'dialog_base', 'profile_ctrl')},
        'locales': {'en': {'auto': ['Auto'], 'skip': ['Skip'], 'profile': ['Profile', 'Audio Log'],
            'speakers': {'chr_authored_guide': ['Guide']}}}}
    clips = {'world:spoken': root / 'world-input/authored-tone.wav', 'world:profile': different}
    library = _library(root / 'world-input', game='endfield', records=records, clips=clips,
        metadata={'publisher_world_dialogue_ui': descriptor})
    world = PreparedCaptureSession(root / 'world');world.import_library(library)
    scope = world.start()
    positioned = [span('Auto', .78, .05, .1), span('Skip', .92, .05, .06),
        span('Guide', .45, .83, .1), span(body, .1, .9, .8, height=.065)]
    observed = [value['text'] for value in positioned]
    world.observe(scope, 1, observed, channel='fullframe', now=1, presentation_lines=positioned, frame_size=(1920, 1080))
    voiced = world.observe(scope, 2, observed, channel='fullframe', now=1.1, presentation_lines=positioned, frame_size=(1920, 1080))
    bad = [{**value, 'confidence': 0} for value in positioned]
    quality_veto = world.index.match_endfield_world_caption(bad, (1920, 1080)) is None
    opening = 'Keep watching the western entrance.'
    records = [row('nte:First', opening), row('nte:Short', 'Ah?', previous='nte:First'),
        row('nte:Elsewhere', 'Ah?'), row('nte:Unknown', 'Ah?', status='unknown', kind='uncategorized')]
    clips = {'nte:First': root / 'nte-input/authored-tone.wav',
        'nte:Short': root / 'nte-input/authored-tone.wav', 'nte:Elsewhere': different}
    library = _library(root / 'nte-input', game='nte', records=records, clips=clips)
    nte = PreparedCaptureSession(root / 'nte');nte.import_library(library)
    scope = nte.start();sequence = 0
    def scans(text, *, menu=False, quality=True):
        nonlocal sequence
        positioned = [span(text, .3, .84, .4, size=(1000, 1000))]
        if menu: positioned.append(span('An authored response option', .7, .72, .25, size=(1000, 1000)))
        layout = native_nte_caption(positioned if quality else [], (1000, 1000), (0, 0, 1000, 1000), (100, 700, 800, 280))
        results = []
        for _ in range(2):
            sequence += 1
            results += nte.observe(scope, sequence, list(layout.groups) if layout else [text],
                now=sequence*.1, nte_layout=layout, dialogue_menu=bool(layout and layout.dialogue_menu))
        return results
    scans(opening);short = scans('Ah?')
    scans(opening);scans('Ah?', menu=True)
    menu_reset = nte.nte_context.anchor is None
    scans(opening);scans('Ah?', quality=False)
    result = {'fixture': 'authored-positioned-spans-not-sdk-gameplay',
        'endfield_world_original_identity': len(voiced) == 1 and voiced[0]['text_id'] == 'world:spoken',
        'endfield_unknown_quality_rejected': quality_veto,
        'nte_direct_original_successor': len(short) == 1 and short[0]['text_id'] == 'nte:Short',
        'nte_actual_menu_geometry_reset': menu_reset, 'nte_absent_evidence_disabled': nte.nte_context.anchor is None}
    result.update(training_proof(root / 'training'))
    if any(value is not True for key, value in result.items() if key != 'fixture'):
        raise ValueError('The authored game caption policy proof failed')
    return result
