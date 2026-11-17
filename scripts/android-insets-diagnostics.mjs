// Empty-reader emulator only. Never retain UI text, raw dumps or error messages.
import {mkdirSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {authoredReaderBounds} from './android-authored-reader-insets.mjs';

export function numericInsetsSample(xml, size, requested, packageName) {
  const sample = {requested_rotation: requested, physical_size: size, hierarchy_rotation: null,
    hierarchy_bytes: typeof xml === 'string' ? Buffer.byteLength(xml) : 0,
    reader_bounds: [], system_bar_bounds: [], strict_bounds_passed: false};
  if (typeof xml !== 'string' || xml.length > 1024 * 1024) return sample;
  const rotation = /<hierarchy[^>]*\brotation="([0-3])"/.exec(xml);
  if (rotation) sample.hierarchy_rotation = Number(rotation[1]);
  for (const match of xml.matchAll(/<node\s+([^>]+)>/g)) {
    const attrs = Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(v => [v[1], v[2]]));
    const rectangle = /^\[(-?\d{1,5}),(-?\d{1,5})\]\[(-?\d{1,5}),(-?\d{1,5})\]$/.exec(attrs.bounds ?? '');
    if (!rectangle) continue;
    const bounds = rectangle.slice(1).map(Number);
    if (attrs.package === packageName && attrs.class === 'android.webkit.WebView' && sample.reader_bounds.length < 8)
      sample.reader_bounds.push(bounds);
    if (attrs.package === 'com.android.systemui' && sample.system_bar_bounds.length < 8) {
      const kind = /:id\/(?:status_bar|status_bar_container)$/.test(attrs['resource-id'] ?? '') ? 'status'
        : /:id\/(?:navigation_bar_frame|navigation_bar_view)$/.test(attrs['resource-id'] ?? '') ? 'navigation' : null;
      if (kind) sample.system_bar_bounds.push({kind, bounds});
    }
  }
  try { sample.strict_bounds_passed = !!authoredReaderBounds(xml, ...size, packageName); } catch {}
  return sample;
}

export function createInsetsDiagnostics({output, sourceCommit, apkSha256, packageName}) {
  if (!/^[a-f0-9]{40}$/.test(sourceCommit) || !/^[a-f0-9]{64}$/.test(apkSha256)
      || packageName !== 'io.github.firebird55.gameimmersiontoolkit.debug') throw Error('Invalid authored diagnostic identity');
  mkdirSync(output, {recursive: true});
  let size = [null, null], requested = null, dump = {completed: false, idle_error: false, bytes: 0};
  const report = {schema: 'toolkit-authored-insets-diagnostic-v1', source_commit: sourceCommit,
    apk_sha256: apkSha256, samples: [], failures: [], dump_count: 0,
    unchanged_apk: true, production_fix_acceptance: false, real_account_writes: false};
  const save = () => writeFileSync(join(output, 'android-insets-diagnostic.json'), JSON.stringify(report, null, 2) + '\n');
  const isDump = args => args.join(' ') === 'shell uiautomator dump /sdcard/toolkit-authored-insets.xml';
  save();
  return {
    record(args, value) {
      const command = args.join(' ');
      if (command === 'shell wm size') {
        report.sizes = [...value.matchAll(/(Physical|Override) size: (\d{1,5})x(\d{1,5})/g)]
          .slice(0, 4).map(m => ({kind: m[1] === 'Physical' ? 'physical' : 'override', size: m.slice(2).map(Number)}));
        size = report.sizes.at(-1)?.size ?? size;
      } else if (/^shell settings put system user_rotation [0-3]$/.test(command)) requested = Number(args.at(-1));
      else if (isDump(args)) {
        report.dump_count++; dump = {completed: true, idle_error: /could not get idle state/i.test(value), bytes: Buffer.byteLength(value)};
      } else if (command === 'shell cat /sdcard/toolkit-authored-insets.xml') {
        const sample = {...numericInsetsSample(value, size, requested, packageName), dump};
        if (JSON.stringify(sample) !== JSON.stringify(report.samples.at(-1))) {
          if (report.samples.length === 64) report.samples.splice(8, 1);
          report.samples.push(sample);
        }
      } else return;
      save();
    },
    failed(args, error) {
      if (!isDump(args)) return;
      report.dump_count++;
      const bytes = Buffer.concat([Buffer.from(error?.stdout ?? ''), Buffer.from(error?.stderr ?? '')]).subarray(0, 8192);
      const item = {requested_rotation: requested, error_code: /could not get idle state/i.test(bytes.toString()) ? 'idle_timeout' : 'dump_failed',
        status: Number.isInteger(error?.status) ? error.status : null};
      if (report.failures.length < 64) report.failures.push(item);
      dump = {completed: false, idle_error: item.error_code === 'idle_timeout', bytes: bytes.length}; save();
    },
  };
}
