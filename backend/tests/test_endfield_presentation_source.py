"""Synthetic original UI structures and frozen numerical-codec format cases."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from backend import endfield_presentation_source as source
from backend.endfield_presentation import SOURCE_ROLES


def layout():
    objects, counter = {}, 0
    def node(name, parent=None, *, text=None, position=None, corner=False):
        nonlocal counter
        counter += 1
        identity, transform = counter, 1000 + counter
        objects[identity] = {'m_Name': name, 'm_Component': [{'component': {'m_FileID': 0, 'm_PathID': transform}}]}
        objects[transform] = {'m_GameObject': {'m_FileID': 0, 'm_PathID': identity},
            'm_Father': {'m_FileID': 0, 'm_PathID': 0 if parent is None else 1000 + parent},
            'm_AnchorMin': {'x': 1.0 if corner else 0.0, 'y': 1.0 if corner else 0.0},
            'm_AnchorMax': {'x': 1.0 if corner else 0.0, 'y': 1.0 if corner else 0.0},
            'm_AnchoredPosition': position or {'x': 0.0, 'y': 0.0}}
        if text:
            objects[2000 + counter] = {'m_GameObject': {'m_FileID': 0, 'm_PathID': identity}, '_textId': text}
        return identity
    def bind(values):
        objects[9999] = {'_keys': list(values), '_values': [{'m_FileID': 0, 'm_PathID': value} for value in values.values()]}
    return objects, node, bind


def layouts():
    dialog, node, bind = layout()
    bottom = node('BottomLayout')
    name, text = node('TextName', bottom), node('TextTalk', bottom)
    bind({'bottomLayout': bottom, 'textName': name, 'textTalk': text})
    profile, node, bind = layout()
    root = node('Profile')
    voice, role = node('VoiceInformation', root), node('RoleInformation', root)
    body, name = node('VoiceBody', voice), node('CharName', role)
    for key in source.PROFILE_LABELS:
        node('Header-' + key, root, text=key)
    bind({'voiceInformation': voice, 'roleInformation': role, 'textVoiceInformation': body, 'charNameTextShadow': name})
    top, node, _ = layout()
    root = node('TopRight', corner=True)
    node('ButtonAuto', root, position={'x': -200.0, 'y': -80.0})
    node('ButtonSkip', root, position={'x': -100.0, 'y': -80.0})
    auto, skip = node('AutoKeyHint', root), node('SkipKeyHint', root)
    node('Text', auto, text='future_auto_label')
    node('Text', skip, text='future_skip_label')
    return {'dialog': dialog, 'profile': profile, 'top': top}


def scripts():
    # Constructed interface statements, not original game-controller files.
    return {'dialog_ctrl': '''DialogCtrl.SetTrunk = function(self)
    name = trunkTbData.actorName
    dialogText = trunkTbData.dialogText
    self.view.textName:SetAndResolveTextStyle(richName)
    self.view.textTalk:SetText(text)
end
''', 'profile_ctrl': '''CharInfoProfileCtrl._PlayVoice = function(self)
    local voiceId = data.voId
    VoiceUtils.TryGetVoiceDuration(voiceId)
    self.view.voiceInformation.gameObject:SetActive(true)
    self.view.roleInformation.gameObject:SetActive(false)
    self.view.textVoiceInformation.text = data.voiceDesc
end
CharInfoProfileCtrl._StopVoice = function(self)
    self.view.voiceInformation.gameObject:SetActive(false)
end
''', 'dialog_base': '''DialogCtrlBase._SwitchControllerAutoPlayHint = function(self)
    InputManagerInst:SetBindingText(self.view.buttonAuto.onClick.bindingId, Language["new_active_auto"])
    InputManagerInst:SetBindingText(self.view.buttonAuto.onClick.bindingId, Language["new_enable_auto"])
end
'''}


def test_source_roles_discover_new_control_keys_without_a_caption_id_allowlist():
    auto, skip, profile = source.layout_labels(layouts())
    assert auto == {'future_auto_label'} and skip == {'future_skip_label'}
    assert profile == set(source.PROFILE_LABELS)
    assert source.controller_labels(scripts()) == {'new_active_auto', 'new_enable_auto'}


@pytest.mark.parametrize('change', ['wrong_body_owner', 'duplicate_binding', 'moved_controls', 'missing_profile_header'])
def test_changed_UI_ownership_or_role_geometry_is_not_certified(change):
    data = layouts()
    if change == 'wrong_body_owner':
        binding = data['profile'][9999]
        i = binding['_keys'].index('textVoiceInformation')
        binding['_values'][i] = binding['_values'][binding['_keys'].index('charNameTextShadow')]
    elif change == 'duplicate_binding':
        data['dialog'][9998] = deepcopy(data['dialog'][9999])
    elif change == 'moved_controls':
        key = source._named(data['top'], 'ButtonAuto')
        data['top'][1000 + key]['m_AnchoredPosition']['x'] = -50.0
    else:
        for row in data['profile'].values():
            if row.get('_textId') == source.PROFILE_LABELS[0]:
                row['_textId'] = 'unrecognized_new_profile_control'
    with pytest.raises(ValueError):
        source.layout_labels(data)


def test_an_unparsed_canvas_component_is_still_bound_to_its_unique_original_owner():
    data = layouts()
    dialog = data['dialog']
    root = dialog[9999]['_values'][0]['m_PathID']
    dialog[root]['m_Component'].append({'component': {'m_FileID': 0, 'm_PathID': 8888}})
    dialog[9999]['_values'][0] = {'m_FileID': 0, 'm_PathID': 8888}
    assert source.layout_labels(data)[0] == {'future_auto_label'}


@pytest.mark.parametrize('decoy', ['-- ', '--[[\n', 'logger.info("'])
def test_comments_and_string_literals_cannot_certify_a_removed_profile_hide(decoy):
    data = scripts()
    statement = 'self.view.roleInformation.gameObject:SetActive(false)'
    replacement = decoy + statement + ('\n]]' if decoy.startswith('--[[') else '")' if decoy.startswith('logger') else '')
    data['profile_ctrl'] = data['profile_ctrl'].replace(statement, replacement)
    with pytest.raises(ValueError):
        source.controller_labels(data)


def test_normal_source_table_updates_supply_new_labels_and_actors(monkeypatch):
    keys = ('future_auto', 'future_skip', 'future_profile', 'future_audio')
    references = {key: {'id': index} for index, key in enumerate(keys)}
    table = {'0': 'Play automatically', '1': 'Skip dialogue', '2': 'Operator Profile',
             '3': 'Audio Log', '4': 'A new operator'}
    monkeypatch.setattr(source, 'original_ui', lambda *_: {'sources': {role: 'a'*32 for role in SOURCE_ROLES},
        'auto': {'future_auto'}, 'skip': {'future_skip'}, 'profile': {'future_profile', 'future_audio'}})
    catalog = SimpleNamespace(tools=None, stamp='endfield-'+'b'*64, file=lambda _: references)
    rows = {'future_line': {'dialogue_kind': 'conversation', 'original_speaker_id': 'chr_future', 'actorName': {'id': 4}}}
    before = source.cues(catalog, rows, {'en': table})
    table['0'] = 'New published automatic-play label'
    after = source.cues(catalog, rows, {'en': table})
    assert before['locales']['en']['auto'] == ['Play automatically']
    assert after['locales']['en']['auto'] == ['New published automatic-play label']
    assert after['locales']['en']['speakers'] == {'chr_future': ['A new operator']}


def test_frozen_synthetic_Lua_ciphertext_is_decoded_only_as_data():
    encrypted = b'8KZWIToKxsu9/ZEqRZEc3zBfKaRZa05arMZZHHbpwPqma7mqkRidRglooKc='
    assert source.decode_lua(encrypted, b'fixture-key-only') == 'return "synthetic data; never execute"'
    with pytest.raises(ValueError):
        source.decode_lua(b'not valid base64', b'fixture-key-only')
