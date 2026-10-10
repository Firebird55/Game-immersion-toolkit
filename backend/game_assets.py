"""Explicit registry of local dialogue/original-voice extraction adapters."""
from importlib import import_module

LOCAL_GAMES = {"cyberpunk": "Cyberpunk 2077", "wuwa": "Wuthering Waves", "witcher3": "The Witcher 3",
               "nte": "Neverness to Everness", "honkai3": "Honkai Impact 3rd"}
_ADAPTERS = {"cyberpunk": ("cyberpunk_assets", "WolvenKit.CLI.exe"),
             "wuwa": ("wuthering_assets", "FModelCLI.exe"), "witcher3": ("witcher_assets", ""),
             "nte": ("nte_assets", "NteReader.dll"), "honkai3": ("honkai_assets", "")}


def asset_adapter(game):
    if game not in _ADAPTERS:
        raise ValueError("Unsupported local original-voice adapter")
    module, executable = _ADAPTERS[game]
    return import_module("." + module, __package__), executable
