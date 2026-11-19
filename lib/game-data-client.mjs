export const LIVE_GAME_IDS = Object.freeze(['zzz', 'genshin', 'starrail', 'endfield', 'wuwa', 'nte', 'reverse1999', 'infinitynikki']);
const states = new Set(['not_downloaded', 'planning', 'ready', 'downloading', 'update_available', 'error', 'unsupported']);
const bytes = value => Number.isSafeInteger(value) && value >= 0;
const text = (value, maximum = 512) => typeof value === 'string' && value.length <= maximum && !/[\u0000-\u001f\u007f]/.test(value);

export function validateGameDataRow(value) {
  if (!value || !LIVE_GAME_IDS.includes(value.id) || !text(value.title, 200) || !states.has(value.state)
      || !['text', 'text-audio'].includes(value.content_mode)
      || !(value.installed_revision === null || text(value.installed_revision, 256)) || typeof value.can_activate !== 'boolean'
      || value.can_activate && value.installed_revision === null
      || !(value.revision === null || text(value.revision)) || !text(value.region, 32) || !text(value.source_locale, 32)
      || !Array.isArray(value.target_locales) || value.target_locales.length > 128 || !value.target_locales.every(code => text(code, 32))
      || !['installed_bytes', 'deletable_bytes', 'retained_bytes'].every(key => bytes(value[key]))
      || value.last_download_bytes != null && !bytes(value.last_download_bytes)
      || value.has_checkpoint !== undefined && typeof value.has_checkpoint !== 'boolean'
      || !['download_bytes', 'required_disk_bytes'].every(key => value[key] === null || bytes(value[key]))
      || typeof value.download_is_upper_bound !== 'boolean' || !['can_plan', 'can_download', 'can_delete'].every(key => typeof value[key] === 'boolean')
      || !(value.plan_id === null || text(value.plan_id, 128) && value.plan_id.length > 0) || !text(value.message, 1000))
    throw Error('Game data information is unavailable. Retry in Settings.');
  const job = value.job;
  const installed = value.installed_request;
  if (installed !== undefined && installed !== null && (value.installed_revision === null || !installed || typeof installed !== 'object'
      || !['global', 'cn'].includes(installed.region) || !['text', 'text-audio'].includes(installed.content_mode)
      || !text(installed.source_locale, 32) || !installed.source_locale
      || !Array.isArray(installed.target_locales) || installed.target_locales.length > 128
      || !installed.target_locales.every(code => text(code, 32) && code.length > 0)))
    throw Error('Downloaded game selection is unavailable. Refresh Settings.');
  if (job !== null && (!job || !text(job.id, 128) || !text(job.status, 64) || !text(job.phase, 64)
      || job.progress_percent !== undefined && (!bytes(job.progress_percent) || job.progress_percent > 100)
      || job.completed_stages !== undefined && !bytes(job.completed_stages)
      || job.stop_requested !== undefined && typeof job.stop_requested !== 'boolean'
      || !bytes(job.downloaded_bytes) || !(job.total_bytes === null || bytes(job.total_bytes)) || !text(job.message, 1000)))
    throw Error('Game download progress is unavailable. Refresh Settings.');
  return value;
}

export function validateGameDataList(value) {
  if (!value || value.schema !== 'game-data-v1' || !Array.isArray(value.games) || value.games.length > LIVE_GAME_IDS.length)
    throw Error('Game data information is unavailable. Retry in Settings.');
  value.games.forEach(validateGameDataRow);
  if (new Set(value.games.map(game => game.id)).size !== value.games.length) throw Error('Duplicate game information. Refresh Settings.');
  return value;
}

export function formatGameBytes(value) {
  if (value === null) return 'Unknown';
  if (!bytes(value)) throw Error('Invalid game data size');
  if (value < 1024) return `${value} B`;
  const unit = Math.min(3, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** unit).toFixed(1)} ${['B', 'KiB', 'MiB', 'GiB'][unit]}`;
}

export function canDownloadGame(row, selection) {
  return !!row?.can_download && row.plan_id !== null && row.download_bytes !== null
    && row.content_mode === selection.content_mode
    && row.region === selection.region && row.source_locale === selection.source_locale
    && JSON.stringify([...row.target_locales].sort()) === JSON.stringify([...selection.target_locales].sort());
}
