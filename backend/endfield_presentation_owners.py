"""Original asset paths consumed by the shared Endfield capture validators.

These are reader contract paths, not a version-specific bundle or dialogue-ID
list. The selected original registry must supply every exact UI owner.
"""

UI_ROOT = 'assets/beyond/dynamicassets/gameplay/ui/prefabs/'
DIALOG_GRAPHS = 'assets/beyond/dynamicassets/gameplay/dialog/json/'
WORLD_UI = {'dialog': UI_ROOT + 'dialog/dialogpanel.prefab',
            'top': UI_ROOT + 'dialog/topright.prefab',
            'profile': UI_ROOT + 'charinfo/charinfoprofilepanel.prefab'}
SNS_UI = {'basic_layout': UI_ROOT + 'sns/snsbasicpanel.prefab',
          'barker_layout': UI_ROOT + 'sns/snsbarkerpanel.prefab',
          'mission_layout': UI_ROOT + 'sns/snsmissionpanel.prefab',
          'core_layout': UI_ROOT + 'sns/widgets/snsdialogcontentcore.prefab',
          'cell_layout': UI_ROOT + 'sns/widgets/snsdialogcontentcorecell.prefab',
          'system_layout': UI_ROOT + 'sns/widgets/snscontentsystemmsg.prefab'}
TRAINING_UI = {'step_layout': UI_ROOT + 'dungeon/dungeonchartutorialstephudpanel.prefab',
               'task_layout': UI_ROOT + 'commontasktrack/commontasktrackhudpanel.prefab'}
