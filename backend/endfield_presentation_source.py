"""Validate released UI data as data; never execute original Lua/client code."""
import base64
from collections import defaultdict
from functools import lru_cache
import re
import struct

from . import endfield_film_update as assets, endfield_release as release
from . import endfield_film_registry as registry
from .endfield_presentation import validate_world_dialogue_ui
from .game_tools import _atomic_file
from .languages import normalize_text
from .publisher_http import download
from .textmaps import display_text

UI_ROOT = 'assets/beyond/dynamicassets/gameplay/ui/prefabs/'
UI_PATHS = {'dialog': UI_ROOT + 'dialog/dialogpanel.prefab', 'top': UI_ROOT + 'dialog/topright.prefab',
            'profile': UI_ROOT + 'charinfo/charinfoprofilepanel.prefab'}
LUA_PATHS = {'dialog_ctrl': 'Data/LuaScripts/UI/Panels/Dialog/DialogCtrl.lua',
             'dialog_base': 'Data/LuaScripts/UI/Panels/Dialog/DialogCtrlBase.lua',
             'profile_ctrl': 'Data/LuaScripts/UI/Panels/CharInfoProfile/CharInfoProfileCtrl.lua'}
PROFILE_LABELS = ('ui_char_info_controller_profile', 'ui_char_profile_show_voice', 'ui_char_profile_voice_title')


def _check(value):
    if not value:
        raise ValueError('Unverified original Endfield world-dialogue presentation')


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _bindings(objects, required):
    candidates = []
    for value in _walk(objects):
        keys, values = value.get('_keys'), value.get('_values')
        if isinstance(keys, list) and set(required) <= set(k for k in keys if isinstance(k, str)):
            _check(isinstance(values, list) and all(isinstance(key, str) for key in keys)
                   and len(keys) == len(values) and len(set(keys)) == len(keys))
            candidates.append(dict(zip(keys, values)))
    _check(len(candidates) == 1)
    return candidates[0]


def _object(objects, pointer):
    _check(isinstance(pointer, dict) and pointer.get('m_FileID') == 0)
    identity = pointer.get('m_PathID')
    if identity not in objects:
        # CanvasGroup and other view components need no interpretation: their
        # original GameObject component list establishes the owning UI node.
        owners = [value for value in objects.values() if any(
            item.get('component') == pointer for item in value.get('m_Component', []))]
        _check(len(owners) == 1)
        return owners[0]
    value = objects[identity]
    return value if 'm_Component' in value else _object(objects, value['m_GameObject'])


def _descendants(objects, root):
    found, pending = set(), [root]
    children = defaultdict(list)
    for value in objects.values():
        if 'm_Father' in value and 'm_GameObject' in value:
            parent = objects.get(value['m_Father'].get('m_PathID'))
            if parent and 'm_GameObject' in parent:
                children[parent['m_GameObject']['m_PathID']].append(value['m_GameObject']['m_PathID'])
    while pending:
        identity = pending.pop()
        _check(identity not in found)
        found.add(identity)
        pending.extend(children[identity])
    return found


def _named(objects, name):
    matches = [key for key, value in objects.items() if value.get('m_Name') == name and 'm_Component' in value]
    _check(len(matches) == 1)
    return matches[0]


def _labels(objects, name):
    descendants = _descendants(objects, _named(objects, name))
    return {value['_textId'] for value in objects.values()
            if value.get('m_GameObject', {}).get('m_PathID') in descendants and value.get('_textId')}


def layout_labels(layouts):
    """Require the source-owned speaker/body and mutually exclusive profile views."""
    dialog, top, profile = (layouts[key] for key in ('dialog', 'top', 'profile'))
    binding = _bindings(dialog, ('textName', 'textTalk', 'bottomLayout'))
    bottom_object = _object(dialog, binding['bottomLayout'])
    bottom, = [key for key, value in dialog.items() if value is bottom_object]
    body = _descendants(dialog, bottom)
    _check(all(_object(dialog, binding[key]) in [dialog[k] for k in body] for key in ('textName', 'textTalk')))
    binding = _bindings(profile, ('textVoiceInformation', 'voiceInformation', 'roleInformation', 'charNameTextShadow'))
    def owns(parent, child):
        parent_object = _object(profile, binding[parent])
        root, = [key for key, value in profile.items() if value is parent_object]
        return _object(profile, binding[child]) in [profile[k] for k in _descendants(profile, root)]
    _check(owns('voiceInformation', 'textVoiceInformation') and owns('roleInformation', 'charNameTextShadow'))
    _check(_object(profile, binding['voiceInformation']) != _object(profile, binding['roleInformation']))
    all_profile = {value.get('_textId') for value in profile.values()}
    _check(set(PROFILE_LABELS) <= all_profile)
    buttons = [_named(top, key) for key in ('ButtonAuto', 'ButtonSkip')]
    rectangles = {value['m_GameObject']['m_PathID']: value for value in top.values()
                  if 'm_AnchoredPosition' in value and 'm_GameObject' in value}
    first, second = (rectangles[key]['m_AnchoredPosition'] for key in buttons)
    _check(first['x'] < second['x'] < 0 and abs(first['y'] - second['y']) < 50)
    root = rectangles[_named(top, 'TopRight')]
    _check(root['m_AnchorMin'] == root['m_AnchorMax'] == {'x': 1.0, 'y': 1.0})
    auto, skip = _labels(top, 'AutoKeyHint'), _labels(top, 'SkipKeyHint')
    _check(1 <= len(auto) <= 2 and len(skip) == 1 and auto.isdisjoint(skip))
    return auto, skip, set(PROFILE_LABELS)


def _function(text, name):
    # Preserve quoted strings, but never accept a commented-out old binding as
    # evidence that a changed controller still renders that presentation.
    token = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|--\[(=*)\[.*?\]\1\]|--[^\r\n]*'
    text = re.sub(token, lambda match: match[0] if not match[0].startswith('--') else '\n' * match[0].count('\n'),
                  text, flags=re.S)
    matches = re.findall(r'(?m)^' + re.escape(name) + r'\s*=.*?function\([^)]*\)(.*?)^end\b', text, re.S)
    _check(len(matches) == 1)
    return matches[0]


def _contains(body, statement):
    pattern = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*|[^\s]'
    actual, wanted = re.findall(pattern, body), re.findall(pattern, statement)
    return any(actual[index:index + len(wanted)] == wanted for index in range(len(actual)))


def controller_labels(scripts):
    body = _function(scripts['dialog_ctrl'], 'DialogCtrl.SetTrunk')
    _check(all(_contains(body, text) for text in ('name = trunkTbData.actorName', 'dialogText = trunkTbData.dialogText',
        'self.view.textName:SetAndResolveTextStyle(richName)', 'self.view.textTalk:SetText(text)')))
    play = _function(scripts['profile_ctrl'], 'CharInfoProfileCtrl._PlayVoice')
    stop = _function(scripts['profile_ctrl'], 'CharInfoProfileCtrl._StopVoice')
    _check(all(_contains(play, text) for text in ('local voiceId = data.voId', 'VoiceUtils.TryGetVoiceDuration(voiceId)',
        'self.view.voiceInformation.gameObject:SetActive(true)', 'self.view.roleInformation.gameObject:SetActive(false)',
        'self.view.textVoiceInformation.text = data.voiceDesc')))
    _check(_contains(stop, 'self.view.voiceInformation.gameObject:SetActive(false)'))
    body = _function(scripts['dialog_base'], 'DialogCtrlBase._SwitchControllerAutoPlayHint')
    labels = re.findall(r'(?m)^\s*InputManagerInst:SetBindingText\(self\.view\.buttonAuto\.onClick\.bindingId,\s*Language\["([A-Za-z0-9_]+)"\]\)', body)
    _check(len(labels) == 2 and len(set(labels)) == 2)
    return set(labels)


def decode_lua(raw, key):
    data = base64.b64decode(raw.strip(), validate=True)
    _check(8 <= len(data) <= 256 * 1024 and len(data) % 4 == 0 and len(key) == 16)
    words = list(struct.unpack('<' + 'I' * (len(data) // 4), data))
    keys = struct.unpack('<4I', key)
    count, mask, delta = len(words), 0xffffffff, 0x9e3779b9
    total, y = ((6 + 52 // count) * delta) & mask, words[0]
    while total:
        e = total >> 2 & 3
        for position in range(count - 1, -1, -1):
            z = words[position - 1] if position else words[-1]
            mix = (((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4)) ^
                   ((total ^ y) + (keys[(position & 3) ^ e] ^ z))) & mask
            words[position] = (words[position] - mix) & mask
            y = words[position]
        total = (total - delta) & mask
    plain = struct.pack('<' + 'I' * count, *words)
    _check(len(plain) - 7 <= words[-1] <= len(plain) - 4)
    return plain[:words[-1]].decode('utf-8', 'strict')


@lru_cache(maxsize=3)
def original_ui(tools, stamp):
    # Keep UI ownership independent of cinematic/recording cache identities.
    base, rows = release.group(tools, stamp, 4)
    manifest, = [row for row in rows if row.name == 'Data/Bundles/Windows/manifest.hgmmap']
    data = registry.inflate(release._whole(tools, base, manifest, 160 * 1024**2), 384 * 1024**2)
    names = {path: 'Data/Bundles/Windows/' + bundle for _, path, bundle in
             registry.bindings(data, path_prefixes=tuple(UI_PATHS.values()))}
    _check(names.keys() == set(UI_PATHS.values()))
    del data
    found = {}
    for role, block in [('initial', 2), ('main', 11)]:
        wanted = frozenset(name for name in names.values() if name.startswith('Data/Bundles/Windows/' + role + '/'))
        if wanted:
            base, rows = release.group(tools, stamp, block, wanted)
            found.update((file.name, (base, file)) for file in rows)
    _check(set(names.values()) <= found.keys())
    files = {path: found[name] for path, name in names.items()}
    layouts, sources = {}, {}
    for role, path in UI_PATHS.items():
        _check(path in files)
        source = files[path]
        _, _, layouts[role], _ = assets._asset(tools, source, path, classes=(1, 114, 224))
        sources[role] = source[1].content_hashes[1]
    auto, skip, profile = layout_labels(layouts)
    names = frozenset(LUA_PATHS.values())
    base, original = release.group(tools, stamp, 17, names)
    rows = {file.name: file for file in original}
    _check(rows.keys() == names)
    from .endfield_lua_parameters import scripts as original_scripts
    scripts = original_scripts(tools, stamp, {role: (base, rows[path]) for role, path in LUA_PATHS.items()})
    for role, path in LUA_PATHS.items():
        file = rows[path]
        sources[role] = file.content_hashes[1]
    auto.update(controller_labels(scripts))
    return {'sources': sources, 'auto': auto, 'skip': skip, 'profile': profile}


def cues(catalog, dialogs, tables):
    source, locales = original_ui(catalog.tools, catalog.stamp), {}
    labels = catalog.file('TableCfg/TextTable.json')
    for locale, table in tables.items():
        def texts(keys):
            values = [display_text(table.get(str(labels.get(key, {}).get('id')), '')) for key in keys]
            _check(all(values))
            return sorted(set(values))
        names = defaultdict(set)
        for row in dialogs.values():
            speaker = row.get('original_speaker_id')
            if not speaker or row.get('dialogue_kind') != 'conversation':
                continue
            actor = row.get('actorName')
            name = display_text(table.get(str(actor.get('id')), '')) if isinstance(actor, dict) else ''
            if normalize_text(name, locale) and not re.search(r'[{}\[\]]', name):
                names[speaker].add(name)
        if names:
            locales[locale] = {'auto': texts(source['auto']), 'skip': texts(source['skip']),
                'profile': texts(source['profile']), 'speakers': {key: sorted(value) for key, value in names.items()}}
    return validate_world_dialogue_ui({'schema': 1, 'revision': catalog.stamp,
                                      'sources': source['sources'], 'locales': locales})
