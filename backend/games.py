from __future__ import annotations

from dataclasses import dataclass

from .models import CaptureRegion


@dataclass(frozen=True, slots=True)
class GameProfile:
    id: str
    name: str
    process_names: tuple[str, ...]
    title_needles: tuple[str, ...]
    subtitle_region: CaptureRegion


GAME_PROFILES = {
    "nte": GameProfile(id="nte", name="Neverness to Everness", process_names=("HTGame.exe",),
        title_needles=("Neverness to Everness", "NTE", "异环"),
        subtitle_region=CaptureRegion(left=.10, top=.70, width=.80, height=.28)),
    "honkai3": GameProfile(id="honkai3", name="Honkai Impact 3rd", process_names=("BH3.exe",),
        title_needles=("Honkai Impact", "崩坏3"),
        subtitle_region=CaptureRegion(left=.04, top=.72, width=.96, height=.24)),
    "witcher3": GameProfile(id="witcher3", name="The Witcher 3", process_names=("witcher3.exe",),
        title_needles=("The Witcher 3",),
        subtitle_region=CaptureRegion(left=.08, top=.63, width=.84, height=.34)),
    "wuwa": GameProfile(id="wuwa", name="Wuthering Waves", process_names=("Client-Win64-Shipping.exe",),
        title_needles=("Wuthering Waves", "鸣潮"),
        subtitle_region=CaptureRegion(left=.10, top=.64, width=.80, height=.32)),
    "cyberpunk": GameProfile(id="cyberpunk", name="Cyberpunk 2077", process_names=("Cyberpunk2077.exe",),
        title_needles=("Cyberpunk 2077",),
        subtitle_region=CaptureRegion(left=.12, top=.59, width=.76, height=.37)),
    "hito": GameProfile(
        id="hito",
        name="Hito's World Playtest",
        process_names=("Hito's World.exe", "Hito's World Playtest.exe"),
        title_needles=("Hito's World",),
        subtitle_region=CaptureRegion(left=0.365, top=0.815, width=0.34, height=0.125),
    ),
    "zzz": GameProfile(
        id="zzz",
        name="Zenless Zone Zero",
        process_names=("ZenlessZoneZero.exe",),
        title_needles=("Zenless Zone Zero", "ZenlessZoneZero"),
        subtitle_region=CaptureRegion(),
    ),
    "pragmata": GameProfile(
        id="pragmata",
        name="PRAGMATA",
        process_names=("PRAGMATA.exe",),
        title_needles=("PRAGMATA",),
        # Every observed presentation (radio, cutscene and in-world dialogue)
        # uses the centered lower subtitle lane. Keep enough height for the
        # speaker label and two wrapped subtitle rows, but exclude HUD corners.
        subtitle_region=CaptureRegion(left=0.19, top=0.76, width=0.62, height=0.22),
    ),
}


def ordered_profiles(preferred: str = "auto") -> list[GameProfile]:
    profiles = list(GAME_PROFILES.values())
    if preferred in GAME_PROFILES:
        chosen = GAME_PROFILES[preferred]
        profiles.remove(chosen)
        profiles.insert(0, chosen)
    return profiles
