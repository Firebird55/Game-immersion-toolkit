"""Steam titles with native dialogue readers and explicit installation identities.

Keep executable identities separate from display names: several Valve games
share hl2.exe, and a launcher's directory is not necessarily the game directory.
Language and dialogue coverage belongs to each reader and the sourced catalog.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SteamGame:
    title: str
    app_id: int
    directory: str
    executable: str
    markers: tuple[str, ...]
    adapter: str
    window_executable: str | None = None
    floating_dialogue: bool = False
    voiced_capture: bool = True


STEAM_GAMES = {
    'spyro': SteamGame('Spyro Reignited Trilogy', 996580, 'Spyro Reignited Trilogy',
        'Spyro.exe', ('Falcon/Content/Paks/pakchunk0-WindowsNoEditor.pak',), 'spyro_assets',
        'Falcon/Binaries/Win64/Spyro-Win64-Shipping.exe'),
    'mgsvtpp': SteamGame('METAL GEAR SOLID V: THE PHANTOM PAIN', 287700, 'MGS_TPP',
        'mgsvtpp.exe', ('master/data1.dat', 'master/chunk0.dat'), 'mgsv_tpp_assets', floating_dialogue=True),
    'mgsvgz': SteamGame('METAL GEAR SOLID V: GROUND ZEROES', 311340, 'Metal Gear Solid Ground Zeroes',
        'MgsGroundZeroes.exe', ('data_02.g0s',), 'mgsv_gz_assets', floating_dialogue=True),
    'deathstranding': SteamGame('DEATH STRANDING', 1190460, 'Death Stranding',
        'ds.exe', ('data',), 'death_stranding_assets', floating_dialogue=True),
    'plaguetaleinnocence': SteamGame('A Plague Tale: Innocence', 752590, 'A Plague Tale Innocence',
        'APlagueTaleInnocence_x64.exe', ('LangDef.tsc', 'TRTEXT', 'SOUNDBANKS'), 'plague_tale_assets'),
    'detroit': SteamGame('Detroit: Become Human', 1222140, 'Detroit Become Human',
        'DetroitBecomeHuman.exe', ('BigFile_PC.idx',), 'detroit_assets'),
    'portal': SteamGame('Portal', 400, 'Portal', 'hl2.exe', ('portal/gameinfo.txt',), 'portal_assets', floating_dialogue=True),
    'portal2': SteamGame('Portal 2', 620, 'Portal 2', 'portal2.exe', ('portal2/gameinfo.txt',), 'portal2_assets', floating_dialogue=True),
    'halflife': SteamGame('Half-Life', 70, 'Half-Life', 'hl.exe', ('valve/liblist.gam',), 'halflife_assets', voiced_capture=False),
    'halflife2': SteamGame('Half-Life 2', 220, 'Half-Life 2', 'hl2.exe', ('hl2/gameinfo.txt',), 'halflife2_assets', floating_dialogue=True),
    'persona5royal': SteamGame('Persona 5 Royal', 1687950, 'P5R', 'P5R.exe', ('CPK/BASE.CPK',), 'persona5_assets', floating_dialogue=True),
    'deusexhrdc': SteamGame("Deus Ex: Human Revolution - Director's Cut", 238010,
        "Deus Ex Human Revolution Director's Cut", 'DXHRDC.exe', ('BIGFILE.000',), 'deusex_hr_assets', floating_dialogue=True),
}
