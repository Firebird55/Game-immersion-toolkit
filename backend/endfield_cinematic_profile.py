"""Verified publisher FMV and in-engine cinematic recordings and subtitle clocks."""
from . import endfield_global_1_6 as fmv

PACKAGES = fmv.PACKAGES

# The Mandarin Valley Fort call has two subtitle windows that overlap. Both
# protagonists use the same recording and localized timeline. Recording-relative
# cuts were checked against the two public playthroughs in the film audit.
_VALLEY_CALL_DIGEST = '523fbe41428c2f0ed2b317a2ce73c2ab70d2503bfebea159f02b185c306122cf'
_VALLEY_CALL_CLOCKS = {
    'cutscene_e1m3_2d1_03': (12.46667, 15.2),
    'cutscene_e1m3_2d1_04': (20.41667, 22.23956),
    'cutscene_e1m3_2d1_04d5': (22.23333, 24.62738),
    'cutscene_e1m3_2d1_05': (29.83333, 34.56667),
}
_VALLEY_CALL_CUTS = {
    'cutscene_e1m3_2d1_04': (19.620, 22.170),
    'cutscene_e1m3_2d1_04d5': (22.170, 24.62738),
}


def verified_recording_captions(film, dub, digest, captions, speech):
    if (dub != 'chinese' or digest != _VALLEY_CALL_DIGEST
            or film not in ('m_cutscene_e1m3_2', 'f_cutscene_e1m3_2') or len(speech) != 1):
        return captions
    event, start, end = speech[0]
    if (event != 'au_vo_cs_e1m3_2' or start != 0 or end < 34.56667
            or len(captions) != len(_VALLEY_CALL_CLOCKS)
            or {key: (a, b) for key, a, b in captions} != _VALLEY_CALL_CLOCKS):
        return captions
    return [(key, *_VALLEY_CALL_CUTS.get(key, (a, b))) for key, a, b in captions]


# Each tuple follows the publisher's Mandarin, English, Japanese, Korean order.
SCENE_FILMS = {
    'f_cutscene_e0m0_5': (
        (836785047, 'd8e21ec7fedff2c5e6c46f54016a0dc9801d0d338a7e6148a43d9a28f461ef63'),
        (1050781516, '973520ffd09b9101f0f6baef37c3da030e8b11ae732388dc657823dbdad6ca11'),
        (57181376, 'b621b82c1bb7bc4ffef42947254f41142632b2842695a0faa700e6fd6a424809'),
        (430673461, 'a5afbaea274b84543c58d99c04d17b3fa361468af5422a31216fcca29c1e7072')),
    'm_cutscene_e0m0_5': (
        (964971386, 'fb6653b3b7d225bc794fdf5b268a6ef04fec1073c7ebd3950baef4baa64ae872'),
        (401041889, 'ea1d531a83607013ebe974bce3a3b819de5d1e29701732de9f1960336641bf04'),
        (316059211, '3649113d9173a6dd68d88cc58a19babd74b32899d4ea522fbaf3ae8a1c435722'),
        (650793155, 'ca68cd5977469197d6cc32b7f92d66f23350a4da588c6252539e3064222dc1f4')),
}
FILMS = fmv.FILMS | SCENE_FILMS
CUES = fmv.CUES | {
    (scene, caption): times
    for scene in SCENE_FILMS
    for caption, times in (
        ('cutscene_e0m0_5_01', (11900, 13817, 12000, 14233, 11667, 14367, 12050, 14400)),
        ('cutscene_e0m0_5_02', (14883, 16767, 14233, 17050, 14367, 17050, 14400, 17067)),
    )
}
EVENTS = fmv.EVENTS | {
    'f_cutscene_e0m0_5': ('au_vo_cs_e0m0_5_f',) * 4,
    'm_cutscene_e0m0_5': ('au_vo_cs_e0m0_5_m',) * 4,
}
# All eight verified subtitle playables display _02 immediately after _01.
SCENE_PREVIOUS = {(scene, 'cutscene_e0m0_5_02'): 'cutscene_e0m0_5_01' for scene in SCENE_FILMS}

SCENE_ASSETS = {
    'assets/beyond/dynamicassets/gamedata/subtitle/cutscene/singleconfigs/f_cutscene_e0m0_5.asset':
        (1062302473511320208, '02398d077e76785e42b06df15b54a067'),
    'assets/beyond/dynamicassets/gamedata/subtitle/cutscene/singleconfigs/m_cutscene_e0m0_5.asset':
        (205196613230855789, '42c432952e0480b9d157ef84be8ade57'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/f_cutscene_e0m0_5.json':
        (1029154595357470646, '4d92900dce3b9901a4cd80b1108a902b'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/playable/f_cutscene_e0m0_5.playable':
        (156270522686942945, '9285c697e3b5c86057d88a1c5d91f406'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/playable/f_cutscene_e0m0_5_audio.playable':
        (869187501166875630, '5421f45a04686b57473e8b82b9a09faa'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/playable/f_cutscene_e0m0_5_others.playable':
        (738136202271103757, 'af99e8149d9e6249cce6d1bcdb2dfffe'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/playable/f_cutscene_e0m0_5_others_au_en.playable':
        (58641720323680580, 'b28d7b12af5e44af1d614f183af55310'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/playable/f_cutscene_e0m0_5_others_au_jp.playable':
        (915738195103720871, '67ccaf3deebb299d1de7135e870de8d1'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/playable/f_cutscene_e0m0_5_others_au_ko.playable':
        (1096208949147426849, '379c2c2b80bd68d654f2f3b978aa397f'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/prefab/f_cutscene_e0m0_5.prefab':
        (309563746509985289, '36290407efa0795e15efa901f7df68a6'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/prefab/f_cutscene_e0m0_5_audio.prefab':
        (481310848788081734, 'edca17d359f3a9b743d7b7b0de42f538'),
    'assets/beyond/dynamicassets/gameplay/cutscene/f_cutscene_e0m0_5/prefab/f_cutscene_e0m0_5_others.prefab':
        (242026198141753005, 'f38aff4fbb51c7981291a36c154bcc65'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/m_cutscene_e0m0_5.json':
        (890769779962517334, '0043f0bfda628ab65f4952463966c0a2'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/playable/m_cutscene_e0m0_5.playable':
        (1063521694865238929, 'deb16168783577b726204bc8be362afa'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/playable/m_cutscene_e0m0_5_audio.playable':
        (1032626210224015364, 'e424cd00dc9241be046baacc3a83ba51'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/playable/m_cutscene_e0m0_5_others.playable':
        (133650894816849749, 'd2a10b4a27bbe3ea28b93533cd5b69b9'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/playable/m_cutscene_e0m0_5_others_au_en.playable':
        (14011778107153510, 'c8aaf3e7bbc9294d530daca8f80a064e'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/playable/m_cutscene_e0m0_5_others_au_jp.playable':
        (771335723250759683, '6f5573ea43a7cce846521bc05b091c83'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/playable/m_cutscene_e0m0_5_others_au_ko.playable':
        (591301167480109409, 'dbbf6a922d92545ab4903114a7140a00'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/prefab/m_cutscene_e0m0_5.prefab':
        (871424925821461913, 'a671750145fc97b135c29e99ef0fdb9a'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/prefab/m_cutscene_e0m0_5_audio.prefab':
        (859862897999458268, 'dd53f2dcda878aa8a3637505e48f8e6f'),
    'assets/beyond/dynamicassets/gameplay/cutscene/m_cutscene_e0m0_5/prefab/m_cutscene_e0m0_5_others.prefab':
        (667135860487862485, '867b9ebe1e7ceb61eca48672bbc280fb'),
}


def scene_dependencies(scene, dub):
    root = f'assets/beyond/dynamicassets/gameplay/cutscene/{scene}/'
    configuration = f'assets/beyond/dynamicassets/gamedata/subtitle/cutscene/singleconfigs/{scene}.asset'
    suffix = {'chinese': '', 'english': '_au_en', 'japanese': '_au_jp', 'korean': '_au_ko'}[dub]
    return {
        configuration, root + scene + '.json',
        root + f'prefab/{scene}.prefab', root + f'prefab/{scene}_audio.prefab', root + f'prefab/{scene}_others.prefab',
        root + f'playable/{scene}.playable', root + f'playable/{scene}_audio.playable',
        root + f'playable/{scene}_others{suffix}.playable',
    }
