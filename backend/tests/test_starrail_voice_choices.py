"""Original-data choice identity without selecting an implicit voice locale."""
import copy
from types import SimpleNamespace

import pytest

from backend import starrail_voice_choices as choices, starrail_game_data as game
from backend.game_data_protocol import GameDataError, GameDataRequest, VoiceChoiceSelection


class Catalog:
    def __init__(self):
        self.build = {'channel': 'starrail-global', 'version': '1.2.3', 'original_generation': 'synthetic-one'}
        self.tables = SimpleNamespace(descriptions={name: {'synthetic_format': 1} for name in choices.TABLES})
        self.rows = {'AvatarCobrand': [self.cobrand(7001)],
            'AllowedAudioLanguage': [{'AudioLanguageKey': 'original-key', 'WwiseLanguageKey': 'Japanese'}],
            'VoiceAtlas': [{'AvatarID': 7001, 'VoiceID': 1, 'AudioID': 9001}]}

    @staticmethod
    def cobrand(owner):
        return {'ID': owner, 'AudioLanguage': 'original-key', 'StateGroupName': f'StateGroup_New_{owner}',
                'OffStateName': f'new_{owner}_default', 'OnStateName': f'new_{owner}_copyright'}

    def file(self, name):
        return self.rows[name.removeprefix('ExcelOutput/').removesuffix('.json')]


def selection(available, owner=7001, alternative='copyright-dub'):
    return VoiceChoiceSelection(available.choice_set_sha256, ((f'starrail:copyright-avatar:{owner}', alternative),))


def test_new_original_owner_is_discovered_dynamically_without_defaults_or_a_fixed_id_list():
    catalog = Catalog()
    catalog.rows['AvatarCobrand'].extend([Catalog.cobrand(9009), Catalog.cobrand(8008)])
    catalog.rows['VoiceAtlas'].append({'AvatarID': 9009, 'VoiceID': 4, 'AudioEvent': 'Ev_new_authored'})
    available = choices.discover(catalog, 'a'*64, 'en')
    assert {row[1] for row in available.groups} == {7001, 9009}
    receipt = choices.selection_receipt(available, selection(available))
    assert receipt['user_choices'] == [{'group_key': 'starrail:copyright-avatar:7001', 'alternative': 'copyright-dub'}]
    assert receipt['unselected_groups'] == ['starrail:copyright-avatar:9009']
    assert receipt['publisher_default_status'] == 'unknown' and receipt['authored_locale_receipt_status'] == 'unproven'
    assert choices.selection_receipt(available, None)['user_choices'] == []


@pytest.mark.parametrize('drift', ['generation', 'schema', 'row', 'new-group'])
def test_generation_schema_row_or_new_group_drift_rejects_an_old_selection(drift):
    catalog = Catalog(); available = choices.discover(catalog, 'a'*64, 'en'); chosen = selection(available)
    generation = 'a'*64
    if drift == 'generation': generation = 'b'*64
    elif drift == 'schema': catalog.tables.descriptions['AvatarCobrand']['synthetic_format'] = 2
    elif drift == 'row': catalog.rows['AvatarCobrand'][0]['OffStateName'] = 'new_off_state'
    else:
        catalog.rows['AvatarCobrand'].append(Catalog.cobrand(555001))
        catalog.rows['VoiceAtlas'].append({'AvatarID': 555001, 'VoiceID': 1, 'AudioID': 45})
    changed = choices.discover(catalog, generation, 'en')
    assert changed.choice_set_sha256 != available.choice_set_sha256
    with pytest.raises(GameDataError, match='choices changed'):
        choices.selection_receipt(changed, chosen)


def test_unknown_group_or_conflicting_original_owners_cannot_select_or_imply_a_fallback():
    catalog = Catalog(); available = choices.discover(catalog, 'a'*64, 'en')
    with pytest.raises(GameDataError):
        choices.selection_receipt(available, selection(available, owner=999991))
    catalog.rows['AvatarCobrand'].append(copy.deepcopy(catalog.rows['AvatarCobrand'][0]))
    with pytest.raises(GameDataError): choices.discover(catalog, 'a'*64, 'en')
    catalog = Catalog(); catalog.rows['VoiceAtlas'].append(copy.deepcopy(catalog.rows['VoiceAtlas'][0]))
    with pytest.raises(GameDataError): choices.discover(catalog, 'a'*64, 'en')
    catalog = Catalog(); catalog.rows['AllowedAudioLanguage'][0]['WwiseLanguageKey'] = 'UnprovedNewDub'
    with pytest.raises(GameDataError): choices.discover(catalog, 'a'*64, 'en')
    catalog = Catalog(); other = Catalog.cobrand(9991)
    other['StateGroupName'] = catalog.rows['AvatarCobrand'][0]['StateGroupName'].upper()
    catalog.rows['AvatarCobrand'].append(other)
    with pytest.raises(GameDataError): choices.discover(catalog, 'a'*64, 'en')


def test_row_order_is_canonical_but_a_different_study_dub_requires_its_own_choice_set():
    catalog = Catalog(); catalog.rows['AvatarCobrand'].append(Catalog.cobrand(9991))
    catalog.rows['VoiceAtlas'].append({'AvatarID': 9991, 'VoiceID': 2, 'AudioID': 9300})
    first = choices.discover(catalog, 'a'*64, 'en')
    for rows in catalog.rows.values(): rows.reverse()
    assert choices.discover(catalog, 'a'*64, 'en') == first
    assert choices.discover(catalog, 'a'*64, 'ja').choice_set_sha256 != first.choice_set_sha256


def test_current_21_table_boundary_cannot_promote_private_rows_or_touch_audio(monkeypatch):
    catalog = Catalog(); catalog.tables.descriptions.pop('AvatarCobrand')
    catalog.file = lambda *a: pytest.fail('Missing original schemas cannot load research rows')
    assert choices.discover(catalog, 'a'*64, 'en') is None
    request = GameDataRequest('global', 'en', (), 'text-audio', VoiceChoiceSelection('a'*64,
        (('starrail:copyright-avatar:7001', 'copyright-dub'),)))
    provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_transport', lambda *a: pytest.fail('Metadata-unavailable choices cannot open publisher assets'))
    ctx = SimpleNamespace(request=request, check=lambda: None)
    plan = provider.plan(request, ctx)
    assert plan.stage == 'voice-choice-metadata' and not plan.runtime_available
    assert plan.available_voice_choices is None and plan.handle['request'] == request.json()


def test_available_selection_provenance_is_retained_but_cannot_deliver_unproved_mixed_locale(monkeypatch):
    catalog = Catalog(); generation = SimpleNamespace(identity='a'*64)
    available = choices.discover(catalog, generation.identity, 'en')
    request = GameDataRequest('global', 'en', (), 'text-audio', selection(available))
    provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_audio_inventory', lambda *a: pytest.fail('An unproved locale override cannot acquire audio'))
    plan = provider._audio_plan(SimpleNamespace(request=request), catalog, generation, None, {}, {})
    assert plan.stage == 'voice-choice-locale-binding' and not plan.runtime_available
    assert plan.available_voice_choices == available
    provenance = plan.handle['voice_choice_provenance']
    assert provenance['user_choices'][0]['alternative'] == 'copyright-dub'
    assert provenance['authored_locale_receipt_status'] == 'unproven'
    assert plan.handle['request'] == request.json()
    wrong = GameDataRequest('global', 'en', (), 'text-audio', VoiceChoiceSelection('b'*64, request.voice_choices.choices))
    with pytest.raises(GameDataError):
        provider._audio_plan(SimpleNamespace(request=wrong), catalog, generation, None, {}, {})
    with pytest.raises(GameDataError) as error:
        provider._snapshot_audio(SimpleNamespace(request=request), None, None, None, None, None, None)
    assert error.value.code == 'starrail_voice_choice_locale_unproven'


def test_unselected_available_choices_still_have_no_implicit_state(monkeypatch):
    from backend import starrail_game_audio as audio
    catalog = Catalog(); provider = game.create_provider(platform='windows')
    monkeypatch.setattr(provider, '_audio_inventory', lambda *a: (audio.Quote('audio-external-members', ()), object(), {'event_unresolved': 1}, ()))
    ctx = SimpleNamespace(request=GameDataRequest('global', 'en', (), 'text-audio'))
    plan = provider._audio_plan(ctx, catalog, SimpleNamespace(identity='a'*64), SimpleNamespace(identity='b'*64), {}, {})
    assert plan.available_voice_choices is not None and not plan.runtime_available
    provenance = plan.handle['audio']['voice_choice_provenance']
    assert provenance['user_choices'] == [] and provenance['unselected_groups'] == ['starrail:copyright-avatar:7001']


def test_unavailable_selected_update_keeps_existing_text_audio_and_old_request_restore(tmp_path, monkeypatch):
    import json
    from dataclasses import replace
    from backend.game_data import GameDataService
    from backend.tests.test_game_data import Provider
    from backend.tests.test_starrail_game_data import finish
    producer = game.create_provider(platform='windows')
    monkeypatch.setattr(producer, '_transport', lambda *a: pytest.fail('Selected unavailable metadata cannot open assets'))
    restored_requests = []
    class Prior(Provider):
        def plan(self, request, ctx):
            return producer.plan(request, ctx) if request.voice_choices is not None else super().plan(request, ctx)
        def download(self, plan, ctx):
            source = super().download(plan, ctx)
            payload = json.loads(source.snapshot_path.read_bytes()); payload['game'] = 'starrail'
            source.snapshot_path.write_text(json.dumps(payload))
            (ctx.directory / 'owned-original.wem').write_bytes(b'inert owned original retained through selection')
            return replace(source, restore_handle={'request': ctx.request.json()})
        def restore(self, handle, ctx):
            assert handle['request'] == ctx.request.json()
            restored_requests.append(ctx.request.json())
            return super().restore(handle, ctx)
    prior = Prior(); service = GameDataService(tmp_path, {'starrail': prior})
    old = GameDataRequest('global', 'en', ('zh-Hans',), 'text-audio')
    try:
        plan = service.plan('starrail', old.json())['game']
        service.download('starrail', {'plan_id': plan['plan_id'], 'revision': plan['revision']})
        assert finish(service)['job']['status'] == 'complete'
        source = service.restore('starrail'); body = source.snapshot_path.read_bytes()
        original = source.snapshot_path.parent / 'owned-original.wem'; encoded = original.read_bytes()
        available = choices.discover(Catalog(), 'a'*64, 'en')
        selected = GameDataRequest('global', 'en', ('zh-Hans',), 'text-audio', selection(available))
        blocked = service.plan('starrail', selected.json())['game']
        assert blocked['voice_choices'] == selected.voice_choices.json()
        assert not blocked['can_download'] and 'metadata is not available' in blocked['message']
        with pytest.raises(GameDataError):
            service.download('starrail', {'plan_id': blocked['plan_id'], 'revision': blocked['revision']})
        retained = service.restore('starrail')
        assert restored_requests[-1] == old.json() and retained.restore_handle['request'] == old.json()
        assert retained.snapshot_path.read_bytes() == body and original.read_bytes() == encoded
        assert retained.voice_source.has(json.loads(body)['records'][0]) and prior.downloads == 1
        handle = {'schema': game.AUDIO_SOURCE, 'request': selected.json(), 'receipt_sha256': 'a'*64,
                  'snapshot_sha256': 'b'*64, 'members_sha256': 'c'*64}
        with pytest.raises(GameDataError) as error:
            producer._restore_audio(handle, SimpleNamespace(request=selected))
        assert error.value.code == 'starrail_voice_choice_locale_unproven'
    finally: service.close()


def test_choice_metadata_cannot_bypass_existing_study_or_owner_locale_guards(tmp_path):
    import json
    from backend.multilingual_index import MultilingualTextIndex
    from backend.tests.test_starrail_game_snapshot import payload
    from backend import starrail_game_audio as audio
    data = payload(); path = tmp_path / 'textmap.json'; path.write_text(json.dumps(data))
    index = MultilingualTextIndex('starrail', tmp_path, autoload=False); index.path = path
    assert index.load()
    data['records'][0]['audio_locale'] = 'ja'
    data['records'][0]['source_voice_binding']['locale'] = 'ja'
    data['voice_choices'] = {'claimed_override_receipt': 'a'*64}
    path.write_text(json.dumps(data))
    assert not index.load()
    owner = audio.Owner('English/VoBanks9.pck', 1000, 'a'*32,
                        'https://autopatchos.starrails.com/test/VoBanks9.pck', 'b'*64)
    binding = {'locale': 'ja', 'audio_event': 'Ev_original', 'event_media': 1,
               'bank_package': owner.name, 'bank_digest': owner.md5, 'bank_offset': 100, 'bank_size': 20,
               'claimed_override_receipt': 'a'*64}
    with pytest.raises(GameDataError, match='another dub'):
        audio.OriginalVoices(object(), (audio.OriginalMember('starrail:guard', binding, audio.Span(owner, 100, 20)),),
                             decoder=tmp_path/'never-run', encoder=tmp_path/'never-run')
