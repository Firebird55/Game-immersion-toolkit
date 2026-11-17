// Authored rooted emulators only. Production Android never requests root.
export async function waitForAuthoredAdbRoot(adb, until) {
  if (adb('shell', 'id', '-u') === '0') return;
  try {adb('root');}
  catch (error) {
    const text = String(error?.stderr ?? '');
    if (!/unable to connect for root: closed|device offline|device.*not found/.test(text)) throw error;
  }
  await until(() => adb('shell', 'id', '-u') === '0', 'rooted authored emulator after adbd restart', 30_000);
}
