"""Identical originals can resolve duplicate presentation refs, never context."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from backend import endfield_recording_identity as identity, endfield_release as release
from backend.local_game import LocalDialogue, original_recording_context
from backend.models import TextMatch
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_endfield_mission_dialogue import graph, trunk
from backend.voice_assets import voice_hash


def pair():
    common = {'member_text_ids': None, 'source_locale': 'en',
        'source_text': 'A complete caption occurs in both authored presentations.',
        'english': 'A complete caption occurs in both authored presentations.', 'chinese': '同一条完整的官方台词。',
        'texts': {'en': 'A complete caption occurs in both authored presentations.', 'zh-Hans': '同一条完整的官方台词。'},
        'audio_locale': 'en', 'player_voice': None, 'voice_status': 'voiced', 'channels': ['dialogue'],
        'text_capture_verified': True, 'original_speaker_id': 'chr_0001_example'}
    result = []
    for key, kind, filename in [('spoken', 'conversation', 'scene'), ('profile', 'operator_voice', 'archive')]:
        source = f'voice/english/character/{filename}.wem'
        result.append({**deepcopy(common), 'text_id': 'endfield:' + key, 'dialogue_kind': kind,
            'audio': {'publisher': 'endfield-' + '1' * 64, 'file_id': f'{voice_hash(source):016x}',
                      'source': source, 'locale': 'en'}})
    return result


def catalog_and_sources(tmp_path, monkeypatch, rows, *, same=True, same_length=True):
    file = SimpleNamespace(name='Data/Audio/PCK/Windows/English/new_named_package.pck', content_hashes=('', '1' * 32))
    values = {r['audio']['file_id']: b'RIFF' + b'original' for r in rows}
    if not same:
        values[rows[1]['audio']['file_id']] = b'RIFF' + b'different'[:8]
    if not same_length:
        values[rows[1]['audio']['file_id']] += b'longer'
    inventory = {int(key, 16): ('https://publisher.invalid/', file,
        SimpleNamespace(offset=i * 1000, size=len(raw), bank_seed=None, bank_offset=0))
        for i, (key, raw) in enumerate(values.items())}
    calls = []
    monkeypatch.setattr(release, 'inventory', lambda *_: inventory)
    def media(_tools, stamp, dub, key):
        calls.append((stamp, dub, key))
        return values[f'{key:016x}']
    monkeypatch.setattr(release, 'media', media)
    catalog = SimpleNamespace(tools=tmp_path, stamp=rows[0]['audio']['publisher'],
        file=lambda _: {'spoken': {'audioEffect': 0}})
    return catalog, values, file, calls


def index_for(tmp_path, rows):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'endfield',
        'source_locale': 'en', 'records': rows}), encoding='utf8')
    index = MultilingualTextIndex('endfield', tmp_path)
    assert index.ready, index.status()
    return index


def test_identical_current_original_bytes_keep_both_refs_and_resolve_the_subtitle(tmp_path, monkeypatch):
    rows = pair()
    assert not index_for(tmp_path / 'before', rows).match_lines([rows[0]['source_text']], exact_only=True)
    old = deepcopy(rows)
    catalog, values, _, calls = catalog_and_sources(tmp_path, monkeypatch, rows)
    identity.annotate(catalog, rows, 'english')
    assert len(calls) == 2
    for a, b in zip(old, rows):
        assert {k: v for k, v in b.items() if k != 'original_recording_sha256'} == a
        assert b['original_recording_sha256'] == sha256(values[b['audio']['file_id']]).hexdigest()
        LocalDialogue(**b)
    index = index_for(tmp_path / 'after', rows)
    assert index.match_lines([rows[0]['source_text']], exact_only=True).text_id == rows[0]['text_id']
    # Matching one identical export does not erase authored occurrences.
    hit = index.match_lines([rows[0]['source_text']], exact_only=True)
    assert not index.equivalent_caption_occurrence(hit,
        hit.model_copy(update={'text_id': rows[1]['text_id'], 'dialogue_kind': 'operator_voice'}))


@pytest.mark.parametrize('same_length', [False, True])
def test_real_different_recordings_remain_ambiguous(tmp_path, monkeypatch, same_length):
    rows = pair()
    catalog, _, _, calls = catalog_and_sources(tmp_path, monkeypatch, rows, same=False, same_length=same_length)
    identity.annotate(catalog, rows, 'english')
    assert len(calls) == (2 if same_length else 0)
    assert not any('original_recording_sha256' in r for r in rows)
    assert not index_for(tmp_path / 'index', rows).match_lines([rows[0]['source_text']], exact_only=True)


def test_current_package_identity_reuses_only_unchanged_bytes_and_recovers_bad_receipts(tmp_path, monkeypatch):
    rows = pair()
    catalog, values, file, calls = catalog_and_sources(tmp_path, monkeypatch, rows)
    identity.annotate(catalog, rows, 'english')
    first_digest = rows[0]['original_recording_sha256']
    later = pair()
    catalog.stamp = 'endfield-' + '2' * 64
    for row in later:
        row['audio']['publisher'] = catalog.stamp
    calls.clear()
    identity.annotate(catalog, later, 'english')
    assert not calls and later[0]['original_recording_sha256'] == first_digest
    file.content_hashes = '', '2' * 32
    for key in values:
        values[key] = b'RIFFchanged!'
    identity.annotate(catalog, later, 'english')
    assert len(calls) == 2 and later[0]['original_recording_sha256'] != first_digest
    receipts = list((tmp_path / 'endfield-releases/original-recording-identities-v1').iterdir())
    for path in receipts:
        path.write_bytes(b'0' * 64 + b'\n' + b'0' * 64)
    calls.clear()
    identity.annotate(catalog, later, 'english')
    assert len(calls) == 2


@pytest.mark.parametrize('field,value', [
    ('original_speaker_id', 'chr_0002_other'), ('previous_text_id', 'endfield:prior'),
    ('ocr_texts', {'en': ['A different complete identifying speaker caption.']}),
    ('member_text_ids', ['endfield:another_member']), ('channels', ['dialogue', 'cinematic']),
    ('player_voice', 'male'), ('text_capture_verified', False),
])
def test_hashes_do_not_merge_different_recognition_or_actor_context(tmp_path, field, value):
    rows = pair()
    for row in rows:
        row['original_recording_sha256'] = 'a' * 64
    rows[1][field] = value
    index = index_for(tmp_path, rows)
    # An unconfigured player excludes a player-only row; test an actually
    # selected male branch so the mismatch still cannot become one identity.
    index.player_voice = 'male'
    assert not index.match_lines([rows[0]['source_text']], exact_only=True)


def test_an_archive_cannot_bypass_a_guarded_short_conversation(tmp_path, monkeypatch):
    rows = pair()
    for row in rows:
        row.update(source_text='Wait!', english='Wait!', texts={'en': 'Wait!', 'zh-Hans': '等一下！'})
    rows[0].update(previous_text_id='endfield:prior', requires_previous=True)
    catalog, _, _, calls = catalog_and_sources(tmp_path, monkeypatch, rows)
    identity.annotate(catalog, rows, 'english')
    assert not calls and not any('original_recording_sha256' in r for r in rows)
    index = index_for(tmp_path / 'index', rows)
    assert not index.match_lines(['Wait!'], exact_only=True)
    hit = index.match_lines(['Wait!'], exact_only=True, previous_text_id='endfield:prior')
    assert hit and hit.text_id == rows[0]['text_id']


def test_portable_exports_keep_full_text_and_encoding_identity(tmp_path):
    rows = pair()
    for row in rows:
        row['original_recording_sha256'] = 'a' * 64
        row['audio'] = {'prepared_clip': 'audio/' + 'b' * 64 + '.mp3', 'locale': 'en'}
    assert index_for(tmp_path / 'same', rows).match_lines([rows[0]['source_text']], exact_only=True)
    rows[1]['texts']['zh-Hans'] = '另一种官方译文。'
    assert not index_for(tmp_path / 'translated', rows).match_lines([rows[0]['source_text']], exact_only=True)
    rows[1]['texts'] = deepcopy(rows[0]['texts'])
    rows[1]['audio']['prepared_clip'] = 'audio/' + 'c' * 64 + '.wav'
    assert not index_for(tmp_path / 'encoding', rows).match_lines([rows[0]['source_text']], exact_only=True)


def test_missing_portable_clip_keeps_source_provenance_without_recording_equivalence(tmp_path):
    rows = pair()
    for row in rows:
        row.update(audio=None, voice_status='unavailable', original_recording_sha256='a' * 64)
        preserved = LocalDialogue(**row)
        assert preserved.original_recording_sha256 == 'a' * 64
        assert preserved.original_speaker_id == row['original_speaker_id']
        assert original_recording_context(row) is None
    rows[1]['texts']['zh-Hans'] = '另一种官方译文。'
    index = index_for(tmp_path / 'missing', rows)
    assert index.audio_count == 0
    assert not index.match_lines([rows[0]['source_text']], exact_only=True)
    # Opting into missing-audio capture does not turn a source hash into a
    # shared None/playback identity or erase different official translations.
    assert not index.match_missing_audio_lines([rows[0]['source_text']])
    hits = [TextMatch(game='endfield', text_id=row['text_id'], english=row['english'], chinese=row['chinese'],
                     source_ocr=row['source_text'], score=100, kind='exact', voice_status='unavailable',
                     dialogue_kind=row['dialogue_kind']) for row in rows]
    assert not index.equivalent_caption_occurrence(*hits)


@pytest.mark.parametrize('audio', [None, {}, [], 'missing'])
def test_source_hash_without_a_usable_voiced_audio_binding_has_no_export_context(audio):
    row = {**pair()[0], 'audio': audio, 'original_recording_sha256': 'a' * 64}
    assert original_recording_context(row) is None


@pytest.mark.parametrize('digest,speaker,status,scope', [
    ('A' * 64, 'chr_0001_example', 'voiced', 'line'), ('bad', 'chr_0001_example', 'voiced', 'line'),
    ('a' * 64, None, 'voiced', 'line'), ('a' * 64, 'chr_0001_example', 'unvoiced', 'line'),
    ('a' * 64, 'chr_0001_example', 'unknown', 'line'),
    ('bad', 'chr_0001_example', 'unavailable', 'line'),
    ('a' * 64, 'chr_0001_example', 'unavailable', 'context'),
    ('a' * 64, 'chr_0001_example', 'voiced', 'context'),
])
def test_invalid_original_recording_metadata_is_rejected(digest, speaker, status, scope):
    with pytest.raises(ValueError):
        LocalDialogue('row', 'English', '中文', audio={'file': 'original'} if status == 'voiced' else None,
            voice_status=status, audio_scope=scope, original_recording_sha256=digest, original_speaker_id=speaker)


def test_original_ship_actor_owns_incoming_replacement_extension_and_future_ids(tmp_path, monkeypatch):
    path = identity.assets.DIALOG_GRAPHS + 'npc/future_ship_conversation.json'
    blank = trunk('blank', '')
    blank['_actorNodeData']['_actorIndex'] = 0
    replacement = {'$id': 'replacement', '$type': 'Beyond.Gameplay.DialogTreeExTrunkReplaceNode',
        '_trunkReplaceData': {'replaceItems': [{'trunkId': 'future_spoken_line', 'activeCondition': {
            '$type': 'Beyond.Gameplay.CharFriendshipLevel', '_charId': {'constValue': 'chr_0001_example'}}}]}}
    data = graph([blank, replacement], [('blank', 'replacement')])
    data['derivedData'] = {'isSpaceshipDialog': True, 'spaceshipCharId': 'chr_0001_example',
        'actors': [{'actorType': 256, 'actorId': 'npc_entity', 'npcProxyId': 'npc_proxy', 'useNpcProxy': True}]}
    source = SimpleNamespace(content_hashes=('', '1' * 32))
    files = {path: (None, source)}
    monkeypatch.setattr(identity.assets, '_files', lambda *_: files)
    monkeypatch.setattr(identity.assets, '_asset', lambda *_args, **_kwargs:
        ('', 1, {1: {'m_Script': json.dumps(data)}}, []))
    assert identity.character_speakers(tmp_path, 'first') == {'future_spoken_line': 'chr_0001_example'}
    source.content_hashes = '', '2' * 32
    replacement['_trunkReplaceData']['replaceItems'][0]['activeCondition']['_charId']['constValue'] = 'chr_0002_other'
    assert identity.character_speakers(tmp_path, 'changed') == {}
