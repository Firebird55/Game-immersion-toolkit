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
    "riseofthetombraider": GameProfile(id="riseofthetombraider", name="Rise of the Tomb Raider", process_names=("ROTTR.exe",),
        title_needles=("Rise of the Tomb Raider",),
        subtitle_region=CaptureRegion(left=.08, top=.65, width=.84, height=.33)),
    "shadowofthetombraider": GameProfile(id="shadowofthetombraider", name="Shadow of the Tomb Raider", process_names=("SOTTR.exe",),
        title_needles=("Shadow of the Tomb Raider",),
        subtitle_region=CaptureRegion(left=.08, top=.65, width=.84, height=.33)),
    "starrail": GameProfile(id="starrail", name="Honkai: Star Rail", process_names=("StarRail.exe",),
        title_needles=("Honkai: Star Rail", "崩坏：星穹铁道", "崩壞：星穹鐵道"),
        subtitle_region=CaptureRegion(left=.10, top=.70, width=.80, height=.28)),
    "genshin": GameProfile(id="genshin", name="Genshin Impact", process_names=("GenshinImpact.exe", "YuanShen.exe"),
        title_needles=("Genshin Impact", "原神"),
        subtitle_region=CaptureRegion(left=.10, top=.70, width=.80, height=.28)),
    "endfield": GameProfile(id="endfield", name="Arknights: Endfield", process_names=("Endfield.exe",),
        title_needles=("Arknights: Endfield", "Endfield", "明日方舟：终末地", "明日方舟：終末地"),
        subtitle_region=CaptureRegion(left=.10, top=.70, width=.80, height=.28)),
    "heavyrain": GameProfile(id="heavyrain", name="HEAVY RAIN", process_names=("HeavyRain.exe",),
        title_needles=("HEAVY RAIN", "Heavy Rain"),
        subtitle_region=CaptureRegion(left=.05, top=.70, width=.90, height=.28)),
    "beyond": GameProfile(id="beyond", name="BEYOND: Two Souls", process_names=("BeyondTwoSouls_Steam.exe",),
        title_needles=("BEYOND: Two Souls", "BEYOND Two Souls"),
        subtitle_region=CaptureRegion(left=.05, top=.70, width=.90, height=.28)),
    "nte": GameProfile(id="nte", name="Neverness to Everness", process_names=("HTGame.exe",),
        title_needles=("Neverness to Everness", "NTE", "异环"),
        subtitle_region=CaptureRegion(left=.10, top=.70, width=.80, height=.28)),
    "witcher3": GameProfile(id="witcher3", name="The Witcher 3", process_names=("witcher3.exe",),
        title_needles=("The Witcher 3",),
        subtitle_region=CaptureRegion(left=.08, top=.63, width=.84, height=.34)),
    "wuwa": GameProfile(id="wuwa", name="Wuthering Waves", process_names=("Client-Win64-Shipping.exe",),
        title_needles=("Wuthering Waves", "鸣潮"),
        subtitle_region=CaptureRegion(left=.10, top=.64, width=.80, height=.32)),
    "cyberpunk": GameProfile(id="cyberpunk", name="Cyberpunk 2077", process_names=("Cyberpunk2077.exe",),
        title_needles=("Cyberpunk 2077",),
        subtitle_region=CaptureRegion(left=.12, top=.59, width=.76, height=.37)),
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
