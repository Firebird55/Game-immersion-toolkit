"""Import identities of the previously audited film configs, clocks and banks."""
import argparse
import hashlib
import json
from pathlib import Path
from pprint import pformat

from backend import endfield_film_registry, endfield_global_1_6, endfield_vfs

PREFIX = 'assets/beyond/dynamicassets/gamedata/subtitle/fmv/'


def run(registry, metadata, bundles, bank_hashes):
    meta = json.loads((metadata / 'meta.json').read_bytes())
    selected = {int(index) for index, row in meta.items() if row['path'].startswith(PREFIX) and
                any(row['path'][len(PREFIX):].startswith(('singleconfigs/' + film + '.', film + '_others_'))
                    for film in endfield_global_1_6.FILMS)}
    registry_rows = endfield_film_registry.bindings(registry.read_bytes(), bundle_indices=selected)
    by_name = {meta[str(index)]['bundle']: index for index in selected}
    hashes = {row.name.removeprefix('Data/Bundles/Windows/'): row.content_hashes[1] for row in bundles}
    sources = {}
    for head, path, bundle in registry_rows:
        index = by_name[bundle]
        if path != meta[str(index)]['path'] or bundle not in hashes:
            raise ValueError('Active film asset does not match the audited inventory.')
        digest = hashlib.md5((metadata / (str(index) + '.ab')).read_bytes()).hexdigest()
        if digest != hashes[bundle]:
            raise ValueError('Audited film bundle differs from the publisher content hash.')
        sources[path.removeprefix(PREFIX)] = (head, digest)
    if len(sources) != len(selected):
        raise ValueError('Ambiguous active film asset.')
    return ('"""Derived identifiers and checksums of verified localized cinematic sources."""\n\n'
            'ASSETS = ' + pformat(sources, width=128, sort_dicts=True) + '\n\nBANKS = ' +
            pformat(bank_hashes, width=100, sort_dicts=True) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('registry', 'metadata', 'bundle-index', 'format-cache', 'banks', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    from backend.endfield_metadata import parameters
    bundles = endfield_vfs.parse_index(args.bundle_index.read_bytes(), parameters(args.format_cache), 11, suffix='.ab')
    args.output.write_text(run(args.registry, args.metadata, bundles, json.loads(args.banks.read_bytes())), encoding='utf-8')
