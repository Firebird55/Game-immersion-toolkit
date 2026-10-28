/** Stable game identifiers shared by transcript, setup and calibration UI. */
export const GAME_NAMES = {
  zzz: 'Zenless Zone Zero', pragmata: 'PRAGMATA', cyberpunk: 'Cyberpunk 2077',
  wuwa: 'Wuthering Waves', witcher3: 'The Witcher 3', nte: 'Neverness to Everness',
  beyond: 'BEYOND: Two Souls', heavyrain: 'HEAVY RAIN', starrail: 'Honkai: Star Rail',
  genshin: 'Genshin Impact', endfield: 'Arknights: Endfield',
  riseofthetombraider: 'Rise of the Tomb Raider', shadowofthetombraider: 'Shadow of the Tomb Raider',
  spyro: 'Spyro Reignited Trilogy', mgsvtpp: 'METAL GEAR SOLID V: THE PHANTOM PAIN',
  mgsvgz: 'METAL GEAR SOLID V: GROUND ZEROES', deathstranding: 'DEATH STRANDING',
  plaguetaleinnocence: 'A Plague Tale: Innocence', detroit: 'Detroit: Become Human',
  portal: 'Portal', portal2: 'Portal 2', halflife: 'Half-Life', halflife2: 'Half-Life 2',
  persona5royal: 'Persona 5 Royal', deusexhrdc: "Deus Ex: Human Revolution - Director's Cut",
  hito: "Hito's World",
} as const;
export type GameId = keyof typeof GAME_NAMES;

export function captureRegionKey(game: GameId, channel: 'dialogue' | 'tip' | 'cinematic') {
  if (game === 'zzz' || game === 'pragmata') {
    return channel === 'tip' ? 'tip_region' : channel === 'cinematic' ? 'cinematic_region' : 'region';
  }
  if (channel === 'tip') {
    if (game === 'wuwa') return 'wuwa_tip_region';
    if (game === 'cyberpunk') return 'cyberpunk_tip_region';
    if (game === 'witcher3') return 'witcher3_tip_region';
    if (game === 'hito') return 'hito_tip_region';
  }
  if (game === 'wuwa' && channel === 'cinematic') return 'wuwa_cinematic_region';
  return `${game}_region` as const;
}
