"""Explicit registry of local dialogue/original-voice extraction adapters."""
from importlib import import_module
from .steam_games import STEAM_GAMES

LOCAL_GAMES = {"starrail": "Honkai: Star Rail", "genshin": "Genshin Impact", "endfield": "Arknights: Endfield", "cyberpunk": "Cyberpunk 2077", "wuwa": "Wuthering Waves", "witcher3": "The Witcher 3",
               "nte": "Neverness to Everness", "beyond": "BEYOND: Two Souls", "heavyrain": "HEAVY RAIN"}
LOCAL_GAMES.update(riseofthetombraider="Rise of the Tomb Raider", shadowofthetombraider="Shadow of the Tomb Raider")
LOCAL_GAMES.update({game: spec.title for game, spec in STEAM_GAMES.items()})
# Retained for offline format research and regression fixtures only. Archived
# adapters are not enumerated by setup, workers, detection or automatic updates.
ARCHIVED_GAMES = {"honkai3": "Honkai Impact 3rd", "hito": "Hito's World"}
_ADAPTERS = {"starrail": ("starrail_assets", ""), "genshin": ("genshin_assets", ""), "endfield": ("endfield_assets", "EndfieldReader.dll"), "heavyrain": ("heavy_rain_assets", ""), "beyond": ("beyond_assets", ""), "cyberpunk": ("cyberpunk_assets", "WolvenKit.CLI.exe"),
             'zzz': ('zzz_assets', ''),
             'pragmata': ('pragmata_assets', 'REE.Unpacker.exe'),
             "wuwa": ("wuthering_assets", "NteReader.dll"), "witcher3": ("witcher_assets", ""),
             "nte": ("nte_assets", "NteReader.dll"), "honkai3": ("honkai_assets", "")}
_ADAPTERS.update(riseofthetombraider=("rise_tomb_assets", ""), shadowofthetombraider=("shadow_tomb_assets", ""))
_ADAPTERS.update({game: (spec.adapter, '') for game, spec in STEAM_GAMES.items()})


def asset_adapter(game):
    if game not in _ADAPTERS:
        raise ValueError("Unsupported local original-voice adapter")
    module, executable = _ADAPTERS[game]
    return import_module("." + module, __package__), executable
