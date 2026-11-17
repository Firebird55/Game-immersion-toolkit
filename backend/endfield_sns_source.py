"""Derive Baker view/cell ownership from the selected original publisher release."""
from collections import defaultdict
from functools import lru_cache
import re

from . import endfield_film_registry as registry, endfield_film_update as assets
from . import endfield_metadata as metadata, endfield_release as release, endfield_vfs as vfs
from .endfield_presentation_source import _bindings, _check, _contains, _function, _object, decode_lua
from .endfield_sns_presentation import validate_sns_dialogue_ui
from .game_tools import _atomic_file
from .languages import normalize_text
from .publisher_http import download
from .textmaps import display_text


UI_ROOT = 'assets/beyond/dynamicassets/gameplay/ui/prefabs/sns/'
UI_PATHS = {'basic_layout': UI_ROOT + 'snsbasicpanel.prefab',
            'barker_layout': UI_ROOT + 'snsbarkerpanel.prefab',
            'mission_layout': UI_ROOT + 'snsmissionpanel.prefab',
            'core_layout': UI_ROOT + 'widgets/snsdialogcontentcore.prefab',
            'cell_layout': UI_ROOT + 'widgets/snsdialogcontentcorecell.prefab',
            'system_layout': UI_ROOT + 'widgets/snscontentsystemmsg.prefab'}
LUA_PATHS = {'basic_ctrl': 'Data/LuaScripts/UI/Panels/SNSBasic/SNSBasicCtrl.lua',
             'barker_ctrl': 'Data/LuaScripts/UI/Panels/SNSBarker/SNSBarkerCtrl.lua',
             'mission_ctrl': 'Data/LuaScripts/UI/Panels/SNSMission/SNSMissionCtrl.lua',
             'core_ctrl': 'Data/LuaScripts/UI/Widgets/SNSDialogContentCore.lua',
             'cell_ctrl': 'Data/LuaScripts/UI/Widgets/SNSDialogContentCoreCell.lua',
             'system_ctrl': 'Data/LuaScripts/UI/Widgets/SNSContentSystemMsg.lua',
             'base_ctrl': 'Data/LuaScripts/UI/Widgets/SNSContentBase.lua'}


def cell_retention(core):
    """Require the owned ascending append/count/finish path, never replacement.

    These are source-shape checks on the selected release, not executed Lua or
    a hash pin of the current controller. All complete observed boxes are still
    required independently; source retention cannot establish off-screen cells.
    """
    init = _function(core, 'SNSDialogContentCore._InitSNSDialogData')
    progress = _function(core, 'SNSDialogContentCore._StartDialogProcessAction')
    loading = _function(core, 'SNSDialogContentCore._DoCellLoadingAction')
    _check(_contains(init, 'local dialogContentInfo = {} self.m_dialogContentInfo = dialogContentInfo'))
    _check(_contains(init, 'for csIndex = flagCSIndex, contentLink.Count - 1 do '
                     'local contentLinkNode = contentLink[csIndex]'))
    _check(_contains(init, '''
        else
            local latestContentInfo = dialogContentInfo[#dialogContentInfo]
            table.insert(dialogContentInfo,
                self:_GenDialogContentInfo(chatId, dialogId, contentLinkNode.contentId,
                    latestContentInfo and latestContentInfo.contentId or 0,
                    contentLinkNode.hasRead, accumulateCellCount, csIndex, true))
            accumulateCellCount = accumulateCellCount + 1
            table.insert(dialogProcessAction, {
                type = DialogProcessActionType.UpdateCount, dialogId = dialogId,
                count = accumulateCellCount, targetUpdateCellLuaIndex = accumulateCellCount
            })
        end'''))
    _check(_contains(progress, 'local nextProgressAction = self.m_dialogProcessAction[nextStep]')
           and _contains(progress, 'self.view.dialogScrollList:UpdateCount(nextProgressAction.count)')
           and len(re.findall(r':UpdateCount\s*\(', progress)) == 1)
    _check(_contains(loading, 'local contentInfo = self.m_dialogContentInfo[self.m_targetUpdateCellLuaIndex]')
           and _contains(loading, 'local cell = self.m_getDialogContentCellFunc(self.m_targetUpdateCellLuaIndex)')
           and _contains(loading, '''
               if not contentInfo.isLoaded then
                   contentInfo.isLoaded = true
                   self:_StartDialogProcessAction(1)
               end''')
           and not re.search(r':UpdateCount\s*\(', loading))
    for body in (init, progress, loading):
        _check(not re.search(r'table\s*\.\s*(?:remove|sort)\s*\(|:\s*(?:RemoveAt|Reverse)\s*\(', body))
        # Additive-result fields may change; replacing/reordering retained cell
        # entries or reassigning the owned list cannot satisfy this contract.
        _check(not re.search(r'(?:self\s*\.\s*m_dialogContentInfo|dialogContentInfo)\s*\[[^\n]*?\]\s*=(?!=)', body))
    compact = lambda body: re.sub(r'\s+', '', body)
    for body in (compact(init).replace('localdialogContentInfo={}', '', 1)
                 .replace('self.m_dialogContentInfo=dialogContentInfo', '', 1),
                 compact(progress), compact(loading)):
        _check(not re.search(r'(?:self\.m_dialogContentInfo|(?<![\w.])dialogContentInfo)=(?!=)', body))


def controller_labels(scripts):
    configs = dict((panel, key) for key, panel in re.findall(
        r'titleLangKey\s*=\s*"([^"\\]+)"\s*,\s*panelId\s*=\s*PanelId\.([A-Za-z_0-9]+)', scripts['basic_ctrl']))
    _check({'SNSBarker', 'SNSMission', 'SNSFriend'} <= configs.keys())
    body = _function(scripts['basic_ctrl'], 'SNSBasicCtrl._InitTabs')
    _check(_contains(body, 'local titleLangKey = self.m_tabInfos[self.m_curTabIndex].titleLangKey')
           and _contains(body, 'self.view.title.text = Language[titleLangKey]'))
    for role, owner in [('barker_ctrl', 'SNSBarkerCtrl'), ('mission_ctrl', 'SNSMissionCtrl')]:
        body = _function(scripts[role], owner + '._RefreshContent')
        _check(_contains(body, 'local chatId = Tables.sNSDialogTable[dialogId].chatId')
               and _contains(body, 'self.view.snsDialogContentCore:InitSNSDialogContentCore(chatId, dialogId)'))
    body = _function(scripts['core_ctrl'], 'SNSDialogContentCore.InitSNSDialogContentCore')
    _check(_contains(body, 'local chatCfg = Tables.sNSChatTable[chatId]')
           and _contains(body, 'self.view.nameTxt.text = chatCfg.name')
           and _contains(body, 'self.m_chatId = chatId')
           and _contains(body, 'self.m_dialogIds = SNSUtils.processDialogIds(chatId, dialogId, isTopic)'))
    body = _function(scripts['core_ctrl'], 'SNSDialogContentCore._InitSNSDialogData')
    _check(_contains(body, 'dialogInfo:ProcessContentLink()')
           and _contains(body, 'if contentLinkNode.additive then')
           and _contains(body, 'local latestContentInfo = dialogContentInfo[#dialogContentInfo]')
           and _contains(body, 'latestContentInfo and latestContentInfo.contentId or 0')
           and _contains(body, 'if contentLinkNode.linkNodeType == SNSContentLinkNodeType.Option then'))
    cell_retention(scripts['core_ctrl'])
    _check(re.search(r'\[SNSDialogContentType\.System\]\s*=\s*"SystemMsg"', scripts['cell_ctrl']))
    body = _function(scripts['cell_ctrl'], 'SNSDialogContentCoreCell.InitContent')
    _check(_contains(body, 'local contentCfg = rawDialogCfg[contentInfo.contentId]')
           and _contains(body, 'local node = self.view.systemContentNode')
           and _contains(body, 'if contentCfg.isEnd then')
           and _contains(body, 'widget:InitSNSContentBase(contentInfo, callback, notifyCellSizeChange)'))
    body = _function(scripts['base_ctrl'], 'SNSContentBase.InitSNSContentBase')
    _check(_contains(body, 'local contentCfg = Tables.sNSDialogTable[dialogId].dialogContentData[contentInfo.contentId]')
           and _contains(body, 'self.m_contentCfg = contentCfg'))
    body = _function(scripts['system_ctrl'], 'SNSContentSystemMsg._OnSNSContentInit')
    _check(_contains(body, 'if self.m_contentInfo.forceSystemMsg then')
           and _contains(body, 'self.view.contentTxt:SetAndResolveTextStyle(SNSUtils.resolveTextPlayerName(self.m_contentCfg.content))'))
    return configs['SNSBarker'], configs['SNSMission'], configs['SNSFriend']


def layout_ownership(layouts):
    def bound(role, keys):
        objects = layouts[role]
        binding = _bindings(objects, keys)
        found = [_object(objects, binding[key]) for key in keys]
        _check(len({id(value) for value in found}) == len(keys))
        return found
    bound('basic_layout', ('title',))
    for role in ('barker_layout', 'mission_layout'):
        core, = bound(role, ('snsDialogContentCore',))
        _check(core.get('m_Name') == 'SNSDialogContentCore')
    bound('core_layout', ('nameTxt', 'dialogScrollList', 'optionsNode'))
    bound('cell_layout', ('systemContentNode', 'selfNode', 'otherNode'))
    bound('system_layout', ('contentTxt',))


@lru_cache(maxsize=3)
def original_ui(tools, stamp):
    base, rows = release.group(tools, stamp, 4)
    manifest, = [file for file in rows if file.name == 'Data/Bundles/Windows/manifest.hgmmap']
    raw = registry.inflate(release._whole(tools, base, manifest, 160 * 1024**2), 384 * 1024**2)
    names = {path: 'Data/Bundles/Windows/' + bundle for _, path, bundle in
             registry.bindings(raw, path_prefixes=tuple(UI_PATHS.values()))}
    _check(names.keys() == set(UI_PATHS.values()))
    del raw
    found = {}
    for role, block in [('initial', 2), ('main', 11)]:
        wanted = frozenset(name for name in names.values() if name.startswith('Data/Bundles/Windows/' + role + '/'))
        if wanted:
            base, files = release.group(tools, stamp, block, wanted)
            found.update((file.name, (base, file)) for file in files)
    _check(set(names.values()) <= found.keys())
    layouts, sources = {}, {}
    for role, path in UI_PATHS.items():
        source = found[names[path]]
        _, _, layouts[role], _ = assets._asset(tools, source, path, classes=(1, 114, 224))
        sources[role] = source[1].content_hashes[1]
    layout_ownership(layouts)
    root = metadata.cache_root(tools)
    secret = metadata._one(r'XxteaKey\s*=\s*(?:System\.Text\.)?Encoding.UTF8.GetBytes\("([^"\\]*)"\)',
                           (root / 'Keys.cs').read_text(encoding='utf-8-sig'))
    key = secret.encode('utf8')[:16].ljust(16, b'\0')
    base, original = release.group(tools, stamp, 17, frozenset(LUA_PATHS.values()))
    files = {file.name: file for file in original}
    _check(files.keys() == set(LUA_PATHS.values()))
    scripts = {}
    for role, path in LUA_PATHS.items():
        file = files[path]
        scripts[role] = decode_lua(release._whole(tools, base, file, 256 * 1024), key)
        sources[role] = file.content_hashes[1]
    return sources, controller_labels(scripts)


def authored_chains(groups, records):
    """The original normal-content producer follows nextContentId, not ordinals.

    Emoji results and options are additive/separate node types. End/force-system
    placeholders are not original written bodies. A converging branch is not
    accepted by this bounded complete-cell route.
    """
    rows = {row['text_id']: row for row in records}
    chains = []
    for group_id, group in groups.items():
        _check(isinstance(group, dict) and isinstance(group.get('chatId'), str)
               and isinstance(group.get('dialogContentData'), dict))
        items = {str(number): value for number, value in group['dialogContentData'].items()}
        incoming = defaultdict(list)
        for number, cfg in items.items():
            _check(isinstance(cfg, dict) and type(cfg.get('contentId')) is int
                   and str(cfg['contentId']) == number and type(cfg.get('contentType')) is int
                   and type(cfg.get('nextContentId')) is int and type(cfg.get('preContentId')) is int
                   and type(cfg.get('optionType')) is int and type(cfg.get('isEnd')) is bool
                   and isinstance(cfg.get('dialogOptionIds'), list))
            incoming[str(cfg['nextContentId'])].append(number)
        def valid(number):
            cfg = items.get(number)
            identity = f'endfield:SNSDialogTable:{group_id}:{number}'
            return (cfg is not None and identity in rows and not cfg['isEnd']
                    and cfg['optionType'] == 0 and not cfg['dialogOptionIds'])
        for start in items:
            if not valid(start):
                continue
            numbers = [start]
            for _ in range(3):
                previous = numbers[-1]
                following = str(items[previous]['nextContentId'])
                if (following in numbers or not valid(following)
                        or str(items[following]['preContentId']) != previous or incoming[following] != [previous]):
                    break
                numbers.append(following)
                chains.append({'chat_id': group['chatId'],
                               'text_ids': [f'endfield:SNSDialogTable:{group_id}:{number}' for number in numbers]})
    return chains


def cues(catalog, records, tables):
    sources, keys = original_ui(catalog.tools, catalog.stamp)
    sources = dict(sources)
    labels = catalog.file('TableCfg/TextTable.json')
    chats = catalog.file('TableCfg/SNSChatTable.json')
    groups = catalog.file('TableCfg/SNSDialogTable.json')
    for role, table in [('chat_table', 'SNSChatTable'), ('dialog_table', 'SNSDialogTable'), ('label_table', 'TextTable')]:
        sources[role] = catalog.files[f'Data/TableCfg/{table}.bytes'].content_hashes[1]
    locales = {}
    for locale, table in tables.items():
        modes = [display_text(table.get(str(labels.get(key, {}).get('id')), '')) for key in keys]
        names = {identity: display_text(table.get(str(row.get('name', {}).get('id')), ''))
                 for identity, row in chats.items() if isinstance(row, dict) and isinstance(row.get('name'), dict)}
        names = {identity: name for identity, name in names.items()
                 if normalize_text(name, locale) and not re.search(r'[{}\r\n\0]', name)}
        if all(modes) and names:
            locales[locale] = {'modes': modes[:2], 'friends': modes[2], 'chats': names}
    rows = {row['text_id']: row for row in records}
    chains = authored_chains(groups, records)
    def context(chain, locale, config):
        name = config['chats'].get(chain['chat_id'])
        texts = [rows[identity]['texts'].get(locale) for identity in chain['text_ids']]
        if name and all(texts):
            return (locale, normalize_text(name, locale), *(normalize_text(text, locale) for text in texts))
        return None
    interested = {key for chain in chains if any(rows[identity].get('dialogue_kind') == 'message_system'
                                                for identity in chain['text_ids'])
                  for locale, config in locales.items() if (key := context(chain, locale, config)) is not None}
    # Keep every other prepared SNS type with the same complete visible context
    # as a conflict peer. Filtering merely to System rows would lose that veto.
    selected = [chain for chain in chains if any(context(chain, locale, config) in interested
                                                for locale, config in locales.items())]
    return validate_sns_dialogue_ui({'schema': 1, 'revision': catalog.stamp, 'sources': sources,
                                    'locales': locales, 'chains': selected})
