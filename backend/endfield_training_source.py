"""Derive training instruction/goal roles from the selected original release."""
from functools import lru_cache
import json
import re

from . import endfield_release as release
from . import endfield_film_registry as registry, endfield_film_update as assets
from .endfield_presentation_source import (_bindings, _object, _descendants, _check,
    _function, _contains, PROFILE_LABELS)
from .endfield_training_presentation import validate_training_dialogue_ui
from .textmaps import display_text


from .endfield_presentation_owners import UI_ROOT, TRAINING_UI as UI_PATHS
LUA_PATHS = {'step_ctrl': 'Data/LuaScripts/UI/Panels/DungeonCharTutorialStepHud/DungeonCharTutorialStepHudCtrl.lua',
             'task_ctrl': 'Data/LuaScripts/UI/Panels/CommonTaskTrackHud/CommonTaskTrackHudCtrl.lua',
             'goal_ctrl': 'Data/LuaScripts/UI/Widgets/CommonTaskGoalCell.lua'}
JSON_PATHS = {'subgame_table': 'Data/Json/GameplayConfig/SubGameInstanceDataTable.json',
              'task_info_table': 'Data/Json/GameplayConfig/ScriptTaskExtraInfoTable.json'}


def controller_ownership(scripts):
    """Check owned producers, not similarly named HUD text or commented code."""
    required = (
        ('step_ctrl', 'DungeonCharTutorialStepHudCtrl._RefreshStage', (
            'local charTutorialCfg = Tables.dungeonCharTutorialTable[self.m_dungeonId]',
            'local game = GameInstance.dungeonManager.curDungeonLikeSubGame',
            'local stage = game.stage', 'local tutorialStageCfg = charTutorialCfg.tutorialStageData[CSIndex(stage)]',
            'local stepIds = tutorialStageCfg.stepIds', 'self.m_curStepIds = stepIds',
            'local csIndex = CSIndex(luaIndex)', 'local stepId = self.m_curStepIds[csIndex]',
            'local stepCfg = Tables.dungeonCharTutorialStepTable[stepId]',
            'cell.skillDesc.text = stepCfg.iconDesc')),
        ('step_ctrl', 'DungeonCharTutorialStepHudCtrl._UpdateStepDesc', (
            'local curStepId = self.m_curStepIds[CSIndex(self.m_curStep)]',
            'local curStepCfg = Tables.dungeonCharTutorialStepTable[curStepId]',
            'self.view.stepDescTxt.text = curStepCfg.stepDesc')),
        ('task_ctrl', 'CommonTaskTrackHudCtrl._RefreshSubGameTrack', (
            'local mainTask = trackingMgr.mainTask', 'title = mainTask:GetTaskTitle()',
            'Tables.gameMechanicTable:TryGetValue(self.m_subGameId)',
            'title = getGameDataSucc and gameMechanicData.gameName', 'self:_ProcessTitle(title)')),
        ('task_ctrl', 'CommonTaskTrackHudCtrl._ProcessTitle', (
            'self.view.titleDefaultTxt:SetAndResolveTextStyle(title)',
            'self.view.titleFailTxt:SetAndResolveTextStyle(title)',
            'self.view.titleFinishTxt:SetAndResolveTextStyle(title)')),
        ('task_ctrl', 'CommonTaskTrackHudCtrl._RefreshMainTask', (
            'local mainTask = trackingMgr.mainTask', 'local taskKey = mainTask ~= nil and mainTask.taskKey or ""',
            'cell:InitCommonTaskGoalCell(taskKey, index, CS.Beyond.Gameplay.LevelScriptTaskType.Main)')),
        ('goal_ctrl', 'CommonTaskGoalCell._Refresh', (
            'self.m_taskTracking:TryGetValueObjectiveDescription(self.m_taskTrackingObjective)',
            'self.view.goalTxt:SetAndResolveTextStyle(failText)',
            'self.view.progressTxt:SetAndResolveTextStyle(progressText)')))
    for role, function, statements in required:
        body = _function(scripts[role], function)
        _check(all(_contains(body, statement) for statement in statements))
    for function, field in [('_RefreshStage', 'cell.skillDesc.text'), ('_UpdateStepDesc', 'self.view.stepDescTxt.text')]:
        body = _function(scripts['step_ctrl'], 'DungeonCharTutorialStepHudCtrl.' + function)
        _check(len(re.findall(re.escape(field) + r'\s*=(?!=)', body)) == 1)


def layout_ownership(layouts):
    step, task = layouts['step_layout'], layouts['task_layout']
    bindings = _bindings(step, ('stepDescNode', 'stepDescTxt', 'actionStepCell', 'actionStepScrollView'))
    def inside(objects, parent, child):
        root = _object(objects, parent)
        identity, = [identity for identity, value in objects.items() if value is root]
        return _object(objects, child) in [objects[key] for key in _descendants(objects, identity)]
    _check(inside(step, bindings['stepDescNode'], bindings['stepDescTxt']))
    labels = _bindings(step, ('skillDesc', 'skillIcon', 'imageSelect'))
    _check(inside(step, bindings['actionStepCell'], labels['skillDesc']))
    _check(_object(step, bindings['stepDescTxt']) != _object(step, labels['skillDesc']))
    scroll = step[bindings['actionStepScrollView']['m_PathID']]
    _check(scroll.get('m_Horizontal') == 1 and scroll.get('m_Vertical') == 0
           and scroll.get('disableScroll') == 0)
    content = _object(step, scroll['m_Content'])
    layouts = [step[item['component']['m_PathID']] for item in content['m_Component']
               if item['component']['m_PathID'] in step and 'm_ReverseArrangement' in step[item['component']['m_PathID']]]
    _check(len(layouts) == 1 and layouts[0]['m_ReverseArrangement'] == 0 and layouts[0].get('m_Spacing', -1) >= 0)
    bound = _bindings(task, ('titleDefaultTxt', 'titleFailTxt', 'titleFinishTxt', 'mainGoalCell'))
    root = _object(task, bound['mainGoalCell'])
    identity, = [identity for identity, value in task.items() if value is root]
    subtree = {key: task[key] for key in _descendants(task, identity)}
    # Include components of descendants: bindings are on the owned cell root.
    subtree.update((key, value) for key, value in task.items()
                   if value.get('m_GameObject', {}).get('m_PathID') in subtree)
    goals = _bindings(subtree, ('goalTxt', 'progressTxt'))
    objects = [_object(task, bound[key]) for key in ('titleDefaultTxt', 'titleFailTxt', 'titleFinishTxt')]
    objects += [_object(task, goals[key]) for key in ('goalTxt', 'progressTxt')]
    _check(len({id(value) for value in objects}) == len(objects))


@lru_cache(maxsize=3)
def original_ui(tools, stamp):
    base, files = release.group(tools, stamp, 4)
    manifest, = [file for file in files if file.name == 'Data/Bundles/Windows/manifest.hgmmap']
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
    layouts, sources = {}, {}
    for role, path in UI_PATHS.items():
        source = found[names[path]]
        _, _, layouts[role], _ = assets._asset(tools, source, path, classes=(1, 114, 224))
        sources[role] = source[1].content_hashes[1]
    layout_ownership(layouts)
    base, files = release.group(tools, stamp, 17, frozenset(LUA_PATHS.values()))
    files = {file.name: file for file in files}
    _check(files.keys() == set(LUA_PATHS.values()))
    from .endfield_lua_parameters import scripts as original_scripts
    scripts = original_scripts(tools, stamp, {role: (base, files[path]) for role, path in LUA_PATHS.items()})
    for role, path in LUA_PATHS.items():
        sources[role] = files[path].content_hashes[1]
    controller_ownership(scripts)
    return sources


def authored_descriptor(stamp, sources, records, tutorials, steps, games, subgames, task_infos, labels, tables):
    """Literal ordinary task-title route; custom/native-config titles fail closed.

    The format's TaskExtraInfo flag defaults false; true selects a different
    native configuration route and cannot borrow the fallback title. Script
    scope and mainTask UID come from the original subgame, never stage names.
    Goal descriptions are role-veto evidence only, never new dialogue rows.
    """
    rows = {row['text_id']: row for row in records}
    stages, owners, goals = [], {}, []
    for owner, tutorial in tutorials.items():
        subgame, game = subgames.get(owner, {}), games.get(owner, {})
        if (game.get('gameCategory') != 'dungeon_chartutorial' or subgame.get('id') != owner
                or not str(subgame.get('$type', '')).startswith('Beyond.Gameplay.Core.DungeonSubGameData,')
                or subgame.get('modeId') != 'dungeon_training' or subgame.get('disableTracking')):
            continue
        script = str(subgame.get('bindScriptId'))
        scopes = [scripts[script] for scripts in task_infos.values()
                  if isinstance(scripts, dict) and script in scripts]
        if len(scopes) != 1 or not isinstance(subgame.get('mainTasks'), list) or not subgame['mainTasks']:
            continue
        tasks = [scopes[0].get(task.get('taskId')) for task in subgame['mainTasks']]
        if any(not isinstance(task, dict) or task.get('taskTitleUseConfig', False) is not False
               or not isinstance(task.get('taskTitle'), dict) or not task['taskTitle'].get('key') for task in tasks):
            continue
        title_keys = {task['taskTitle']['key'] for task in tasks}
        owners[owner] = (title_keys, game.get('gameName'))
        for number, stage in enumerate(tutorial['tutorialStageData']):
            ids = ['endfield:DungeonCharTutorialStepTable:' + identity for identity in stage['stepIds']]
            if ids and all(identity in rows for identity in ids):
                stages.append({'owner': owner, 'stage': number, 'text_ids': ids})
        for task in tasks:
            for objective in task.get('trackingInfoDict', {}).values():
                ref = objective.get('description', {})
                if objective.get('descriptionUseConfig', False) is False and isinstance(ref, dict) and ref.get('key'):
                    goals.append({'owner': owner, 'key': ref['key']})
    def literal(table, ref):
        return display_text(table.get(str(ref.get('id')), '')) if isinstance(ref, dict) else ''
    def keyed(table, key):
        return literal(table, labels.get(key))
    locales = {}
    for locale, table in tables.items():
        titles = {}
        for owner, (keys, fallback) in owners.items():
            names = [keyed(table, key) for key in keys]
            if all(names):
                # The fallback is a peer, not an assumed current override.
                titles[owner] = sorted(set(names + ([literal(table, fallback)] if literal(table, fallback) else [])))
        label_rows = {'endfield:DungeonCharTutorialStepTable:' + identity: literal(table, cfg.get('iconDesc'))
                      for identity, cfg in steps.items()}
        label_rows = {identity: text for identity, text in label_rows.items() if text and identity in rows}
        if titles and label_rows:
            locales[locale] = {'titles': titles, 'labels': label_rows,
                              'profile': [value for key in PROFILE_LABELS if (value := keyed(table, key))]}
    return validate_training_dialogue_ui({'schema': 1, 'revision': stamp, 'sources': sources, 'locales': locales,
        'stages': [stage for stage in stages if any(stage['owner'] in config['titles'] for config in locales.values())],
        'goals': [{'owner': goal['owner'], 'texts': {locale: value for locale, table in tables.items()
                   if locale in locales and (value := keyed(table, goal['key'])) and not re.search(r'[{}\r\n\0]', value)}}
                  for goal in goals]})


def cues(catalog, records, tables):
    sources = dict(original_ui(catalog.tools, catalog.stamp))
    base, files = release.group(catalog.tools, catalog.stamp, 19, frozenset(JSON_PATHS.values()))
    files = {file.name: file for file in files}
    data = {}
    for role, path in JSON_PATHS.items():
        file = files[path]
        data[role] = json.loads(release._whole(catalog.tools, base, file, 16 * 1024**2))['dataTable']
        sources[role] = file.content_hashes[1]
    original = {}
    for role, table in [('tutorial_table', 'DungeonCharTutorialTable'), ('step_table', 'DungeonCharTutorialStepTable'),
                        ('game_table', 'GameMechanicTable'), ('label_table', 'TextTable')]:
        original[role] = catalog.file('TableCfg/' + table + '.json')
        sources[role] = catalog.files['Data/TableCfg/' + table + '.bytes'].content_hashes[1]
    return authored_descriptor(catalog.stamp, sources, records, original['tutorial_table'], original['step_table'],
        original['game_table'], data['subgame_table'], data['task_info_table'], original['label_table'], tables)
