// Authored acceptance telemetry only: no credentials, account IDs or payloads.
const routes = new Set(['/api/lexirise/accounts', '/api/lexirise/accounts/select', '/api/lexirise/accounts/recover']);
const kinds = new Set(['account_generation_changed', 'account_recovery_required', 'account_recovery_not_required',
 'account_recovery_busy', 'account_recovery_superseded', 'account_selection_pending', 'account_selection_superseded']);
const phases = new Set(['before-fill', 'after-fill', 'before-submit']);
const integer = value => Number.isSafeInteger(value) && value >= 0 ? value : null;
const boolean = value => typeof value === 'boolean' ? value : null;

export function recoveryGenerationHeader(value) {
 if (typeof value !== 'string' || !/^(?:0|[1-9][0-9]{0,15})$/.test(value)) return null;
 return integer(Number(value));
}

export function recoveryRoute(value, origin) {
 try {const url = new URL(value);return url.origin === origin && url.protocol === 'http:'
  && ['127.0.0.1', 'localhost'].includes(url.hostname) && !url.username && !url.password
  && !url.search && !url.hash && routes.has(url.pathname) ? url.pathname : null;}
 catch {return null;}
}

export function createAuthoredRecoveryObservation() {
 // Polling reads must never evict the one recovery POST that explains failure.
 const http = new Map([...routes].map(path => [path, []])), predicates = [], forms = [];
 let generation = null, latestScopedRead = null;
 const push = (rows, value, changed = false) => {
  if (!changed || JSON.stringify(rows.at(-1)) !== JSON.stringify(value)) rows.push(value);
  if (rows.length > 32) rows.shift();
 };
 return {
  generation(value) {const valid = integer(value);if (valid !== null) generation = valid;},
  request(path, method, header) {
   if (!routes.has(path) || !['GET', 'POST'].includes(method)) return null;
   const expected = recoveryGenerationHeader(header);
   if (path === '/api/lexirise/accounts' && method === 'GET' && expected !== null) latestScopedRead = expected;
   const receipt = {path, method, expected_generation: expected, last_snapshot_generation: generation,
    status: null, kind: null};
   push(http.get(path), receipt);return receipt;
  },
  response(receipt, status, kind) {
   // A response cannot attach to an unknown or evicted request.
   if (![...http.values()].some(rows => rows.includes(receipt))) return;
   receipt.status = Number.isInteger(status) && status >= 100 && status <= 599 ? status : null;
   receipt.kind = kinds.has(kind) ? kind : null;
   receipt.response_snapshot_generation = generation;
  },
  predicate(value) {
   push(predicates, {owner_matches: boolean(value?.owner_matches),
    account_recovery_present: boolean(value?.account_recovery_present),
    platform_recovery_present: boolean(value?.platform_recovery_present), library_import: boolean(value?.library_import),
    last_snapshot_generation: generation}, true);
  },
  form(phase, value) {
   if (!phases.has(phase)) throw Error('Unknown authored recovery observation phase');
   push(forms, {phase, input_connected: boolean(value?.input_connected), input_present: boolean(value?.input_present),
    input_nonempty: boolean(value?.input_nonempty), input_valid: boolean(value?.input_valid),
    submit_disabled: boolean(value?.submit_disabled), last_scoped_accounts_generation: latestScopedRead,
    last_snapshot_generation: generation});
  },
  snapshot() {return JSON.parse(JSON.stringify({http: [...http.values()].flat(), predicates, forms}));},
 };
}

export async function observeRecoveryForm(page, observation, phase, input = null) {
 if (!observation) return;
 // An element handle belongs only to this explicitly authored form and is never
 // persisted. Reading its connection state detects replacement without a key.
 try {
  const value = await page.evaluate(input => {
   const current = document.querySelector('.account-entry input[type="password"]');
   const submit = current?.closest('form')?.querySelector('button[type="submit"]');
   return {input_connected: input ? input.isConnected : null, input_present: !!current,
    input_nonempty: current ? current.value.length > 0 : null, input_valid: current ? current.validity.valid : null,
    submit_disabled: submit ? submit.disabled : null};
  }, input);
  observation.form(phase, value);
 } catch {observation.form(phase, null);}
}

export async function observeRecoveryPredicate(page, identity, observation) {
 const value = await page.evaluate(async identity => {
  const accounts = await (await fetch('/api/lexirise/accounts')).json();
  const capabilities = await (await fetch('/api/platform')).json();
  return {passed: accounts.active === identity && !accounts.recovery && !capabilities.account_recovery && capabilities.library_import,
   owner_matches: accounts.active === identity, account_recovery_present: !!accounts.recovery,
   platform_recovery_present: !!capabilities.account_recovery, library_import: capabilities.library_import};
 }, identity);
 observation?.predicate(value);
 // Keep the original acceptance predicate, including its capability requirement.
 return value.passed;
}
