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
  return {platform: 'android', library_import: value.library_import, protected_accounts: value.protected_accounts,
    capture_source: value.capture_source, message: value.message,
    receiver_protocol: value.receiver_protocol === 'leased-frames-v1' ? value.receiver_protocol : undefined,
    max_frame_bytes: value.max_frame_bytes};
}

export function canCaptureDeviceFrames(capabilities) {
  return capabilities?.capture_source === 'remote-stream' || capabilities?.capture_source === 'media-projection';
}
