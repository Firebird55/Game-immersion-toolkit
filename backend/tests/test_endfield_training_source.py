"""Ordinary future training IDs follow literal owned title/step references."""
from copy import deepcopy

import pytest

from backend.endfield_training_source import authored_descriptor
from backend.endfield_training_presentation import compile_training_dialogue
from backend.tests.test_endfield_training_presentation import fixture, SOURCE_ROLES, STAMP


def inputs():
    metadata, rows = fixture()
    owner = 'future_unreleased_training'
    ids = [rows[0]['text_id'].split(':')[-1], rows[2]['text_id'].split(':')[-1]]
    tutorials = {owner: {'tutorialStageData': [{'stepIds': ids}]}}
    steps = {identity: {'iconDesc': {'id': -501-number}} for number, identity in enumerate(ids)}
    games = {owner: {'gameCategory': 'dungeon_chartutorial', 'gameName': {'id': -600}}}
    subgames = {owner: {'id': owner, '$type': 'Beyond.Gameplay.Core.DungeonSubGameData, Gameplay.Beyond',
        'modeId': 'dungeon_training', 'bindScriptId': 9876501, 'mainTasks': [{'taskId': 'native_task_UID'}]}}
    infos = {'future_level': {'9876501': {'native_task_UID': {'taskTitle': {'key': 'literal_title'},
        'trackingInfoDict': {'Objective1': {'description': {'key': 'literal_goal'}}}}}}}
    labels = {'literal_title': {'id': -601}, 'literal_goal': {'id': -700}}
    tables = {'en': {'-600': 'Fallback Guide: Future', '-601': 'Operator Guide: Future',
                     '-501': 'Battle Skill', '-502': 'Combo Skill', '-700': rows[0]['source_text']}}
    return [STAMP, {role: 'a'*32 for role in SOURCE_ROLES}, rows, tutorials, steps, games, subgames, infos, labels, tables]


def test_future_ids_titles_labels_and_goal_vetoes_come_from_original_same_scope():
    args = inputs()
    before = deepcopy(args[2])
    descriptor = authored_descriptor(*args)
    config = descriptor['locales']['en']
    assert config['titles']['future_unreleased_training'] == ['Fallback Guide: Future', 'Operator Guide: Future']
    assert descriptor['stages'][0]['text_ids'] == [args[2][0]['text_id'], args[2][2]['text_id']]
    assert descriptor['goals'][0]['texts']['en'] == args[2][0]['source_text']
    assert len(compile_training_dialogue(descriptor, args[2], 'en')['stages']) == 1
    assert args[2] == before


@pytest.mark.parametrize('damage', ['custom_title', 'missing_title', 'wrong_script', 'wrong_task_uid',
    'wrong_subgame_owner', 'wrong_mode', 'disabled_tracking', 'non_tutorial', 'duplicated_script_scope'])
def test_unproved_native_custom_or_different_title_owners_never_borrow_fallback(damage):
    args = inputs()
    sub = args[6]['future_unreleased_training']
    task = args[7]['future_level']['9876501']['native_task_UID']
    if damage == 'custom_title': task['taskTitleUseConfig'] = True
    elif damage == 'missing_title': task['taskTitle'] = {'key': 'missing_current_I18n_ref'}
    elif damage == 'wrong_script': sub['bindScriptId'] = 42
    elif damage == 'wrong_task_uid': sub['mainTasks'][0]['taskId'] = 'another_scope'
    elif damage == 'wrong_subgame_owner': sub['id'] = 'another_owner'
    elif damage == 'wrong_mode': sub['modeId'] = 'another_mode'
    elif damage == 'disabled_tracking': sub['disableTracking'] = True
    elif damage == 'non_tutorial': args[5]['future_unreleased_training']['gameCategory'] = 'ordinary_quest'
    elif damage == 'duplicated_script_scope': args[7]['different_level'] = deepcopy(args[7]['future_level'])
    with pytest.raises(ValueError):
        authored_descriptor(*args)


def test_goal_config_route_is_not_a_new_story_row_or_a_caption_alias():
    args = inputs()
    args[7]['future_level']['9876501']['native_task_UID']['trackingInfoDict']['Objective1']['descriptionUseConfig'] = True
    descriptor = authored_descriptor(*args)
    assert not descriptor['goals']
    assert len(args[2]) == 4 and all('ocr_texts' not in row for row in args[2])
