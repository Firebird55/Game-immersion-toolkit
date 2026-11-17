"""Requested text keeps original evidence without acquiring playable banks."""
import json
import pytest

from backend import nte_assets as assets
from backend.multilingual_index import MultilingualTextIndex
from backend.language_worker import write_payload
from backend.tests.test_nte_publisher import online


def staging(path):
    rows = [('ST_MainDialogue', 'One', 'Watch the western entrance.'),
            ('ST_MainDialogue', 'Missing', 'Keep walking towards the bridge.'),
            ('ST_MainDialogue', 'Ambiguous', 'An ambiguous original event.'),
            ('ST_Sequence', 'Caption', 'An authored cinematic caption.'),
            ('ST_DialogueSumUP', 'Summary', 'An authored written summary.'),
            ('ST_Interface', 'Label', 'An interface label.')]
    (path/'localization.json').write_text(json.dumps({'en': [
        {'ns': ns, 'key': key, 'value': value} for ns, key, value in rows]}), encoding='utf-8')
    (path/'dialogue-events.json').write_text(json.dumps({
        'one': ['play_vo_one'], 'missing': ['play_vo_missing'],
        'ambiguous': ['play_vo_first', 'play_vo_second']}))
    (path/'voice-events.json').write_text(json.dumps(['Play_Vo_One', 'Play_Vo_Missing']))
    (path/'voice-bank-paths.json').write_text(json.dumps([
        'HT/Content/WwiseAudio/Event/English/Play_Vo_One.bnk']))
    (path/'sequence-cues.json').write_text(json.dumps({'events': {'scene': ['Play_Vo_CG_WholeScene']},
        'groups': {'scene': [{'ns': 'ST_Sequence', 'key': 'Caption',
                              'start_ms': 'audio-clock-not-inspected', 'end_ms': None}]}}))
    # Deliberately no media.json. An accidental bank read/parser must fail.
    (path/'banks').mkdir()
    (path/'banks/Play_Vo_One.bnk').write_bytes(b'not inspected for a text request')


def test_text_rows_retain_evidence_and_unknown_captions_without_bank_or_media_reads(tmp_path, monkeypatch):
    staging(tmp_path)
    monkeypatch.setattr(assets, 'read_bank_play_layers', lambda *_a, **_k: pytest.fail('Text request parsed a voice bank'))
    rows = assets.build_records(tmp_path, source_locale='en', content_mode='text')
    by_key = {row['text_id'].rsplit(':', 1)[-1]: row for row in rows}
    assert all(row['audio'] is None and row['audio_omitted_by_request'] is True for row in rows)
    assert by_key['One']['voice_status'] == 'voiced'
    binding = by_key['One']['source_voice_binding']
    assert binding['member'].endswith('/English/Play_Vo_One.bnk')
    assert binding['locale'] == 'en' and binding['playback_resolved'] is False and 'depot' not in binding
    assert by_key['Missing']['voice_status'] == 'unknown' and by_key['Missing']['text_capture_verified']
    assert by_key['Ambiguous']['voice_status'] == 'unknown' and not by_key['Ambiguous']['text_capture_verified']
    assert by_key['Caption']['voice_status'] == 'unknown' and by_key['Caption']['text_capture_verified']
    assert by_key['Caption']['source_voice_binding'] is None
    assert by_key['Summary']['voice_status'] == 'unvoiced'
    assert by_key['Label']['voice_status'] == 'unknown' and not by_key['Label']['text_capture_verified']
    payload = {'format': 2, 'game': 'nte', 'source_locale': 'en', 'install': None,
               'fingerprint': 'fixture', 'content_mode': 'text', 'records': rows}
    write_payload('nte', payload, 'en', [], tmp_path/'textmap.json')
    index = MultilingualTextIndex('nte', tmp_path)
    assert index.ready and index.state == 'text_only' and index.audio_count == 0
    spoken = index.match_lines(['Watch the western entrance.'], exact_only=True)
    assert spoken.voice_status == 'voiced' and spoken.audio_omitted_by_request
    caption = index.match_lines(['An authored cinematic caption.'], exact_only=True)
    assert caption.voice_status == 'unknown' and caption.audio_omitted_by_request
    assert index.match_lines(['An interface label.'], exact_only=True) is None


def test_text_publisher_adapter_does_not_prefetch_or_read_dub_banks(online, monkeypatch):
    from backend import nte_publisher as publisher
    observed = []
    class TextOriginals(dict):
        def __getitem__(self, path):
            assert not path.lower().endswith(('.bnk', '.wem')), 'Text preparation acquired original audio'
            observed.append(path)
            return super().__getitem__(path)
    for stamp in online.originals:
        online.originals[stamp] = TextOriginals(online.originals[stamp])
    monkeypatch.setattr(publisher.Catalog, 'prefetch', lambda *_: pytest.fail('Text request prefetched dub banks'))
    payload = assets.index_language(None, online.root, 'en', ['fr'], content_mode='text')
    assert payload['content_mode'] == 'text' and observed
    assert all(path.endswith('.locres') for path in observed)
    row = payload['records'][0]
    assert row['audio'] is None and row['voice_status'] == 'voiced'
    assert row['source_voice_binding']['event'] == 'Play_Vo_Line'
    assert row['texts']['fr'] == 'Authored translation.'
    assert 'audio not requested' in payload['message']


@pytest.mark.parametrize('groups', [None, [], {'scene': None}, {'scene': ['not a caption owner']}])
def test_text_caption_owner_format_drift_fails_before_publication(tmp_path, groups):
    from backend.preparation_errors import PreparationFailure
    staging(tmp_path)
    (tmp_path/'sequence-cues.json').write_text(json.dumps({'groups': groups}), encoding='utf-8')
    with pytest.raises(PreparationFailure, match='sequence timing or culture'):
        assets.build_records(tmp_path, source_locale='en', content_mode='text')


def test_unsupported_protagonist_projection_remains_unknown_and_cannot_capture(tmp_path):
    staging(tmp_path)
    path = tmp_path/'localization.json'
    value = json.loads(path.read_bytes())
    value['en'][0]['value'] = '{Gender}|gender(first,second,third)'
    path.write_text(json.dumps(value), encoding='utf-8')
    rows = assets.build_records(tmp_path, source_locale='en', content_mode='text')
    row = next(row for row in rows if row['text_id'].endswith(':One'))
    assert row['text_binding_unresolved'] and row['voice_status'] == 'unknown' and not row['audio']


def test_duplicate_unverified_interface_text_keeps_its_veto_in_text_mode(tmp_path):
    staging(tmp_path)
    path = tmp_path/'localization.json'; value = json.loads(path.read_bytes())
    value['en'][-1]['value'] = value['en'][0]['value']
    path.write_text(json.dumps(value), encoding='utf-8')
    rows = assets.build_records(tmp_path, source_locale='en', content_mode='text')
    (tmp_path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'source_locale': 'en',
        'content_mode': 'text', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('nte', tmp_path)
    assert index.ready and index.match_lines(['Watch the western entrance.'], exact_only=True) is None


def text_context(path):
    from backend.nte_dialogue_graph import annotate
    from backend.nte_dialogue_context import NteDialogueContext
    rows = []
    for identity, text in [('First', 'Watch the western entrance.'), ('Short', 'X'), ('Elsewhere', 'X')]:
        rows.append({'text_id': 'nte:Owned:'+identity, 'source_locale': 'en', 'source_text': text,
            'texts': {'en': text}, 'audio_locale': 'en', 'audio': None, 'voice_status': 'unknown',
            'audio_omitted_by_request': True, 'source_voice_binding': None, 'text_capture_verified': True,
            'dialogue_kind': 'conversation', 'channels': ['dialogue']})
    annotate(rows, [('nte:Owned:First', 'nte:Owned:Short')], text_mode=True)
    assert rows[1]['previous_text_id'] == rows[0]['text_id']
    (path/'textmap.json').write_text(json.dumps({'format': 2, 'game': 'nte', 'source_locale': 'en',
        'content_mode': 'text', 'records': rows}), encoding='utf-8')
    index = MultilingualTextIndex('nte', path)
    assert index.ready
    return index, NteDialogueContext()


def observe(context, index, caption, now, *, enabled=True, scope=1):
    return context.match(index, [caption], index.match_lines([caption], exact_only=True),
                         enabled=enabled, scope=scope, now=now, stable_frames=2)


def test_native_text_predecessor_preserves_unknown_and_does_not_widen_ordinary_one_char_lane(tmp_path):
    index, context = text_context(tmp_path)
    assert index.match_lines(['X'], exact_only=True) is None
    assert observe(context, index, 'X', 0) is None
    for now in (1, 1.1):
        assert observe(context, index, 'Watch the western entrance.', now).voice_status == 'unknown'
    match = observe(context, index, 'X', 1.2)
    assert match.text_id == 'nte:Owned:Short' and match.voice_status == 'unknown'
    assert match.audio_omitted_by_request and match.text_capture_verified and match.source_voice_binding is None
    assert index.match_lines(['X'], exact_only=True) is None


@pytest.mark.parametrize('change', ['menu', 'mode', 'snapshot', 'scope', 'speaker', 'unverified', 'player'])
def test_text_predecessor_keeps_menu_source_quality_and_player_guards(tmp_path, change):
    index, context = text_context(tmp_path)
    if change == 'unverified': index._records[0]['text_capture_verified'] = False
    if change == 'player': index._records[0]['player_voice'] = 'female'; index.player_voice = 'male'
    for now in (1, 1.1):
        caption = 'Wrong speaker: Watch the western entrance.' if change == 'speaker' else 'Watch the western entrance.'
        observe(context, index, caption, now)
    if change == 'mode': index.snapshot_metadata['content_mode'] = 'text-audio'
    if change == 'snapshot': index.snapshot_metadata['publisher_snapshot'] = 'different-completed-source'
    assert observe(context, index, 'X', 1.2, enabled=change != 'menu', scope=2 if change == 'scope' else 1) is None
