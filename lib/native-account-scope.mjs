/** Undefined is desktop; null is an Android document awaiting its first snapshot. */
export function nativeAccountHeaders(generation, headers = {}) {
  if (generation === undefined) return {...headers};
  if (!Number.isSafeInteger(generation) || generation < 0)
    throw Error('Wait for the selected account to load before retrying.');
  return {...headers, 'X-Toolkit-Account-Generation': String(generation)};
}

/** Preview images cannot send request headers. Their scope stays read-only. */
export function nativeAccountQuery(generation) {
  if (generation === undefined) return '';
  nativeAccountHeaders(generation);
  return '&account_generation=' + generation;
}
