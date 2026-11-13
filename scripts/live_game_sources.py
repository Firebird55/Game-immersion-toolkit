"""Compare released Windows package inventories without a game installation."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import endfield_release, nte_release, sophon_assets, wuthering_release
from backend.game_tools import _atomic_file

NTE = nte_release.HOSTS
WUWA = {'wuwa-' + region: region for region in wuthering_release.CHANNELS}


def collect(channel, cache, *, resource=None, save=None, voice=None, dub=None):
    if (resource is not None and channel not in NTE or voice is not None and channel not in WUWA or
            (voice is None) != (dub is None) or (save is None) != (resource is None and voice is None)):
        raise ValueError('Select an NTE resource or a Kuro voice and dub, and supply its --save destination.')
    extra = {}
    if channel in WUWA:
        region = WUWA[channel]
        version, base, launcher_files = wuthering_release.launcher(region)
        versions, layers, packages, params, pointers = wuthering_release.discover(cache, version, base, launcher_files, region=region)
        edition = 'Global' if region == 'global' else 'Mainland China'
        scope = edition + ' launcher, core, dub and video files'
        files = {**launcher_files, **layers}
        extra = {'layers': versions, 'previous_scope': edition + ' launcher base PAKs'}
        if voice is not None:
            audio = wuthering_release.voice(cache, packages, dub, voice, params)
            wuthering_release.verify_pointers(pointers)
            if wuthering_release.launcher(region) != (version, base, launcher_files):
                raise ValueError('The Kuro launcher changed during playback preparation. Retry.')
            _atomic_file(save, audio)
    elif channel in NTE:
        branch, revision, items, previous = nte_release.discover(channel)
        extra = {'previous_scope': 'Regional resource list and declared base sections', 'previous_files': previous}
        version, scope = branch + '/' + revision, 'Regional updater files by content identity'
        files = {name: [item.size, item.digest] for name, item in items.items()}
        if resource is not None:
            if resource not in items:
                raise ValueError('The selected NTE resource is absent from this release.')
            def verify():
                latest_branch, latest_revision, _, latest = nte_release.discover(channel)
                if (latest_branch, latest_revision, latest) != (branch, revision, previous):
                    raise ValueError('The NTE publisher release changed during acquisition. Retry.')

            nte_release.save_file(channel, branch, items[resource], save, verify=verify)
    elif channel == 'endfield-global':
        _, raw = endfield_release.discover()
        build = json.loads(raw)
        version, scope = build['version'], 'Global initial and main resource indexes'
        files = {k: [v['version'], v['sha256']] for k, v in build['layers'].items()}
    else:
        build = sophon_assets.release(channel)
        version, scope, files = build['version'], 'Released launcher dub PCKs and game manifest', {}
        game = build['manifests']['game']
        files['game/manifest'] = [game[3], game[4]]
        for field in sorted(set(sophon_assets.VOICE_FIELDS.values())):
            packages = sophon_assets.manifest(cache, channel, tuple(build['manifests'][field]), ('.pck',))
            if not packages:
                raise ValueError('Missing released voice packages for ' + field)
            files.update({field + '/' + name: [asset.size, asset.digest] for name, asset in packages.items()})
    return {'format': 1, 'channel': channel, 'scope': scope, 'version': version, 'files': files, **extra}


def differences(before, after):
    if (after.get('previous_scope') is not None and before.get('channel') == after['channel']
            and before.get('scope') == after['previous_scope']):
        old_files = after.get('previous_files')
        if old_files is None:
            old_files = {k: v for k, v in after['files'].items() if k.startswith('Client/Content/Paks/')}
        return dict(differences(before, {**after, 'scope': before['scope'], 'previous_scope': None, 'files': old_files}),
                    compared_scope=before['scope'])
    if any(before.get(k) != after[k] for k in ('format', 'channel', 'scope')):
        raise ValueError('Cannot compare different regions or inventory formats.')
    old, new = before['files'], after['files']
    return {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
            'changed': sorted(k for k in old.keys() & new.keys() if old[k] != new[k])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('channel', choices=[*sophon_assets.CHANNELS, 'endfield-global', *WUWA, *NTE])
    parser.add_argument('--cache', type=Path, required=True, help='Private directory for launcher manifests')
    parser.add_argument('--previous', type=Path, help='Compare against a previously saved inventory')
    parser.add_argument('--output', type=Path, required=True, help='Write a verified inventory for later comparison')
    parser.add_argument('--resource', help='Exact NTE publisher file path from the inventory')
    parser.add_argument('--save', type=Path, help='Save the selected NTE file or original Kuro WEM')
    parser.add_argument('--voice', help='Exact authored Kuro PlotAudio filename stem for an original external WEM')
    parser.add_argument('--dub', choices=wuthering_release.DUBS, help='Spoken language for --voice')
    args = parser.parse_args()
    if args.save and args.output.resolve() == args.save.resolve():
        parser.error('--save and --output require different destinations')
    before = json.loads(args.previous.read_bytes()) if args.previous else None
    after = collect(args.channel, args.cache.resolve(), resource=args.resource, save=args.save, voice=args.voice, dub=args.dub)
    result = {key: value for key, value in after.items() if key not in ('files', 'previous_scope', 'previous_files')}
    result['entries'] = len(after['files'])
    if before is not None:
        result.update(differences(before, after))
    _atomic_file(args.output, json.dumps(after, sort_keys=True).encode())
    print(json.dumps(result, indent=2))
