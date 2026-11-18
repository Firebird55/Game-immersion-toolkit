/** Only an owned host document can select native controls; desktop is default. */
export function hostPlatform(document = globalThis.document) {
  return document?.querySelector('meta[name="toolkit-host-platform"]')?.getAttribute('content') === 'android'
    ? 'android' : 'desktop';
}

/** A successful HTTP response alone must never advertise unsupported features. */
export function parseNativeCapabilities(value) {
  if (!value || value.platform !== 'android' || typeof value.library_import !== 'boolean'
      || typeof value.protected_accounts !== 'boolean'
      || !['unavailable', 'authored-observations', 'remote-stream', 'media-projection'].includes(value.capture_source)
      || typeof value.message !== 'string' || value.message.length > 1000) {
    throw Error('The app did not provide a complete device capability report.');
  }
  if (value.max_frame_bytes !== undefined && (!Number.isSafeInteger(value.max_frame_bytes)
      || value.max_frame_bytes < 1 || value.max_frame_bytes > 16777216))
    throw Error('The app did not provide a complete device capability report.');
  if (value.protected_accounts && value.account_protocol !== 'scoped-accounts-v1')
    throw Error('The app did not provide a complete device capability report.');
  const recovery=value.account_recovery;
  if (value.history_migration !== undefined && (typeof value.history_migration !== 'boolean'
      || recovery != null && value.history_migration))
    throw Error('The app did not provide a complete device capability report.');
  if (recovery != null && (!value.protected_accounts || value.library_import || value.capture_source !== 'unavailable'
      || recovery.state !== 'credentials_unreadable' || recovery.data_preserved !== true
      || recovery.action !== 'reenter_verified_account' || typeof recovery.message !== 'string'
      || !recovery.message || recovery.message.length > 1000))
    throw Error('The app did not provide a complete device capability report.');
  return {platform: 'android', library_import: value.library_import, protected_accounts: value.protected_accounts,
    history_migration: value.history_migration === true,
    account_recovery: recovery == null ? undefined : {state: recovery.state, data_preserved: true,
      action: recovery.action, message: recovery.message},
    account_protocol: value.account_protocol === 'scoped-accounts-v1' ? value.account_protocol : undefined,
    capture_source: value.capture_source, message: value.message,
    receiver_protocol: value.receiver_protocol === 'leased-frames-v1' ? value.receiver_protocol : undefined,
    max_frame_bytes: value.max_frame_bytes};
}

export function canCaptureDeviceFrames(capabilities) {
  return capabilities?.capture_source === 'remote-stream' || capabilities?.capture_source === 'media-projection';
}
