"""Original next links, view types and source conflicts govern Baker context."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend import endfield_sns_source as source
from backend.endfield_sns_presentation import SOURCE_ROLES, compile_sns_chains


def retention_controller():
    # Synthetic owned functions describe the supported shape without copying
    # an original game controller or executing any Lua.
    return '''SNSDialogContentCore._InitSNSDialogData = HL.Method() << function(self)
    local dialogContentInfo = {}
    self.m_dialogContentInfo = dialogContentInfo
    for csIndex = flagCSIndex, contentLink.Count - 1 do
        local contentLinkNode = contentLink[csIndex]
        if contentLinkNode.additive then
            local additiveOnly = true
        else
            local latestContentInfo = dialogContentInfo[#dialogContentInfo]
            table.insert(dialogContentInfo, self:_GenDialogContentInfo(chatId, dialogId,
                contentLinkNode.contentId, latestContentInfo and latestContentInfo.contentId or 0,
                contentLinkNode.hasRead, accumulateCellCount, csIndex, true))
            accumulateCellCount = accumulateCellCount + 1
            table.insert(dialogProcessAction, { type = DialogProcessActionType.UpdateCount,
                dialogId = dialogId, count = accumulateCellCount,
                targetUpdateCellLuaIndex = accumulateCellCount })
        end
    end
end
SNSDialogContentCore._StartDialogProcessAction = HL.Method() << function(self)
    local nextProgressAction = self.m_dialogProcessAction[nextStep]
    self.view.dialogScrollList:UpdateCount(nextProgressAction.count)
end
SNSDialogContentCore._DoCellLoadingAction = HL.Method() << function(self)
    local contentInfo = self.m_dialogContentInfo[self.m_targetUpdateCellLuaIndex]
    local cell = self.m_getDialogContentCellFunc(self.m_targetUpdateCellLuaIndex)
    if not contentInfo.isLoaded then
        contentInfo.isLoaded = true
        self:_StartDialogProcessAction(1)
    end
end
'''


def test_owned_append_count_loaded_contract_is_structural_not_a_file_hash_pin():
    original = retention_controller()
    source.cell_retention(original)
    source.cell_retention(original.replace('local additiveOnly = true',
        '-- ordinary compatible source extension\n            local additiveOnly = true\n'
        '            local futureCompatibleField = 42'))


@pytest.mark.parametrize('mutation', ['front_insert', 'reverse_order', 'increment_before_append', 'fixed_count',
    'extra_list_reset', 'replace_list', 'remove_old_cell', 'sort_old_cells', 'replace_old_cell', 'finish_removal',
    'loaded_without_advance', 'commented_advance'])
def test_replacement_reordering_removal_or_changed_progress_never_proves_retention(mutation):
    original = retention_controller()
    if mutation == 'front_insert':
        changed = original.replace('table.insert(dialogContentInfo,', 'table.insert(dialogContentInfo, 1,')
    elif mutation == 'reverse_order':
        changed = original.replace('flagCSIndex, contentLink.Count - 1', 'contentLink.Count - 1, flagCSIndex, -1')
    elif mutation == 'increment_before_append':
        changed = original.replace('            accumulateCellCount = accumulateCellCount + 1\n', '')
        changed = changed.replace('            table.insert(dialogContentInfo,',
            '            accumulateCellCount = accumulateCellCount + 1\n            table.insert(dialogContentInfo,')
    elif mutation == 'fixed_count':
        changed = original.replace('count = accumulateCellCount,', 'count = 1,')
    elif mutation == 'extra_list_reset':
        changed = original.replace('self.view.dialogScrollList:UpdateCount(nextProgressAction.count)',
            'self.view.dialogScrollList:UpdateCount(nextProgressAction.count)\n'
            '    self.view.dialogScrollList:UpdateCount(1)')
    elif mutation == 'replace_list':
        changed = original.replace('    for csIndex =', '    dialogContentInfo = {}\n    for csIndex =')
    elif mutation == 'remove_old_cell':
        changed = original.replace('    for csIndex =', '    table.remove(dialogContentInfo, 1)\n    for csIndex =')
    elif mutation == 'sort_old_cells':
        changed = original.replace('    local nextProgressAction =',
            '    table.sort(self.m_dialogContentInfo)\n    local nextProgressAction =')
    elif mutation == 'replace_old_cell':
        changed = original.replace('    local nextProgressAction =',
            '    self.m_dialogContentInfo[1] = self.m_dialogContentInfo[2]\n    local nextProgressAction =')
    elif mutation == 'finish_removal':
        changed = original.replace('    local cell =',
            '    table.remove(self.m_dialogContentInfo, 1)\n    local cell =')
    elif mutation == 'loaded_without_advance':
        changed = original.replace('self:_StartDialogProcessAction(1)', 'self:_StartDialogProcessAction(2)')
    else:
        changed = original.replace('self:_StartDialogProcessAction(1)', '-- self:_StartDialogProcessAction(1)')
    assert changed != original
    with pytest.raises(ValueError):
        source.cell_retention(changed)


def cell(number, previous, following, kind=1, **extra):
    return {'contentId': number, 'preContentId': previous, 'nextContentId': following,
            'contentType': kind, 'optionType': 0, 'dialogOptionIds': [], 'isEnd': False, **extra}


def original_graph():
    # Deliberately nonordinal IDs and map order: sorting or subtracting one
    # cannot reconstruct this newly published topic's actual sequence.
    groups = {'future_event': {'chatId': 'future_contact', 'dialogContentData': {
        99: cell(99, 7, 501, 7), 40: cell(40, 0, 7), 501: cell(501, 99, -1),
        7: cell(7, 40, 99, 7), -1: cell(-1, 501, 0, isEnd=True)}}}
    rows = [{'text_id': f'endfield:SNSDialogTable:future_event:{number}'} for number in (40, 7, 99, 501)]
    return groups, rows


def test_new_topics_follow_native_next_links_and_keep_each_original_id():
    groups, rows = original_graph()
    before = deepcopy(rows)
    chains = source.authored_chains(groups, rows)
    ids = [chain['text_ids'] for chain in chains]
    assert [row['text_id'] for row in rows] in ids
    assert len(chains) == 6 and all(2 <= len(chain['text_ids']) <= 4 for chain in chains)
    assert rows == before
    groups['future_event']['dialogContentData'][40]['compatible_future_field'] = {'another': True}
    assert source.authored_chains(groups, rows) == chains


@pytest.mark.parametrize('condition', ['option', 'end', 'missing_prepared_body', 'wrong_reciprocal_link'])
def test_options_end_placeholders_and_missing_bodies_do_not_make_written_context(condition):
    groups, rows = original_graph()
    target = 'endfield:SNSDialogTable:future_event:7'
    if condition == 'option':
        groups['future_event']['dialogContentData'][7].update(optionType=1, dialogOptionIds=['unselected_option'])
    elif condition == 'end':
        groups['future_event']['dialogContentData'][7]['isEnd'] = True
    elif condition == 'missing_prepared_body':
        rows = [row for row in rows if row['text_id'] != target]
    else:
        groups['future_event']['dialogContentData'][7]['preContentId'] = 12345
    chains = source.authored_chains(groups, rows)
    if condition == 'wrong_reciprocal_link':
        # A directly observed forward pair is independent of its unproved
        # predecessor; it still cannot manufacture the missing backward link.
        assert not any(chain['text_ids'][0].endswith(':40') for chain in chains)
    else:
        assert not any(target in chain['text_ids'] for chain in chains)


def test_converging_predecessors_stay_guarded_but_literal_unbranched_forward_cells_survive():
    groups, rows = original_graph()
    items = groups['future_event']['dialogContentData']
    items[42] = cell(42, 0, 7)
    rows.append({'text_id': 'endfield:SNSDialogTable:future_event:42'})
    chains = source.authored_chains(groups, rows)
    assert not any(chain['text_ids'][0].endswith((':40', ':42')) for chain in chains)
    assert any(chain['text_ids'] == ['endfield:SNSDialogTable:future_event:7',
                                    'endfield:SNSDialogTable:future_event:99'] for chain in chains)


@pytest.mark.parametrize('field,value', [('contentId', '40'), ('nextContentId', []), ('preContentId', None),
                                        ('optionType', False), ('isEnd', 0), ('dialogOptionIds', None)])
def test_changed_required_link_schema_cannot_silently_admit_context(field, value):
    groups, rows = original_graph()
    groups['future_event']['dialogContentData'][40][field] = value
    with pytest.raises(ValueError):
        source.authored_chains(groups, rows)


def test_source_metadata_retains_other_prepared_sns_types_as_complete_context_conflict_peers(monkeypatch):
    groups = {}
    rows = []
    for topic, voice in [('written_future_topic', False), ('voice_future_topic', True)]:
        groups[topic] = {'chatId': 'future_contact', 'dialogContentData': {
            10: cell(10, 0, 80), 80: cell(80, 10, -1, 5 if voice else 7)}}
        for number, text in [(10, 'A complete original contextual message.'), (80, 'New status message')]:
            rows.append({'text_id': f'endfield:SNSDialogTable:{topic}:{number}', 'source_locale': 'en',
                'source_text': text, 'texts': {'en': text}, 'audio': None,
                'voice_status': 'unavailable' if voice and number == 80 else 'unvoiced',
                'dialogue_kind': 'message_voice' if voice and number == 80 else 'message_system' if number == 80 else 'message',
                'text_capture_verified': True, 'channels': ['dialogue']})
    original = deepcopy(rows)
    tables = {'SNSDialogTable': groups, 'SNSChatTable': {'future_contact': {'name': {'id': 10}}},
              'TextTable': {name: {'id': number} for name, number in [('new_messages_key', 101),
                           ('new_tasks_key', 102), ('new_friends_key', 103)]}}
    class Catalog:
        tools, stamp = 'unused synthetic tools', 'endfield-' + '1'*64
        files = {f'Data/TableCfg/{name}.bytes': SimpleNamespace(content_hashes=('', 'a'*32)) for name in tables}
        def file(self, path):
            return tables[path.removeprefix('TableCfg/').removesuffix('.json')]
    monkeypatch.setattr(source, 'original_ui', lambda *_: (
        {role: 'b'*32 for role in SOURCE_ROLES - {'chat_table', 'dialog_table', 'label_table'}},
        ('new_messages_key', 'new_tasks_key', 'new_friends_key')))
    metadata = source.cues(Catalog(), rows, {'en': {'10': 'Future contact', '101': 'New Messages mode',
                                                   '102': 'New Tasks mode', '103': 'New Friends mode'}})
    assert len(metadata['chains']) == 2
    assert not compile_sns_chains(metadata, rows, 'en').chains
    assert rows == original
