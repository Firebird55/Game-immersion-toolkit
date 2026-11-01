"""Independent signed Ubuntu package/source inspection of final Linux bytes."""
from __future__ import annotations

import json
import subprocess

import linux_system as supplier


def inspect(review, snapshot, source_matches, *, gpgv='gpgv'):
    if review.target != 'linux-x64':
        return
    prefix = '_internal/' + supplier.PREFIX + '/'
    try:
        if not any(name.startswith(prefix) for name in review.inventory):
            raise ValueError('Exact Ubuntu binary, source and license evidence is absent.')
        for name in supplier.OWNED:
            if (name not in snapshot.files
                    or not source_matches(snapshot.files[name], supplier.digest(supplier.ROOT / name), name)):
                raise ValueError('Ubuntu verifier policy or recipe differs from the candidate source.')
            recipe_name = prefix + 'recipe/' + name
            item = review.inventory.get(recipe_name, {})
            if (item.get('link') or not source_matches(snapshot.files[name], item.get('sha256'), name)
                    or supplier.digest(review.root / recipe_name) != item.get('sha256')):
                raise ValueError('Retained Ubuntu recipe differs from the reviewed source.')
        policy = json.loads(snapshot.files[supplier.POLICY])
        if policy.get('schema') != 'toolkit-ubuntu-system-inputs-v1':
            raise ValueError('Unknown Ubuntu supplier policy schema.')
        result = supplier.verify_closure(review.root / prefix, policy, gpgv=gpgv)
        for digest, sources in result['origins'].items():
            for source in sources:
                review.origin(digest, 'Ubuntu ' + source['package'] + '=' + source['version']
                              + ' archive:' + source['archive_sha256'] + ' member:' + source['member'])
        counts = {key: value for key, value in result.items() if key != 'origins'}
        review.evidence('native_inputs', ubuntu_archive='signature-and-exact-deb-member', **counts)
        review.evidence('complete_notices', ubuntu_notices='exact-package-copyright-and-common-full-terms', notices=result['notices'])
        review.evidence('corresponding_sources', ubuntu_sources='exact-signed-source-version-original-and-debian-recipe', sources=result['sources'])
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        for check in ('native_inputs', 'complete_notices', 'corresponding_sources'):
            review.block(check, 'ubuntu-supplier-incomplete',
                'Exact Ubuntu archive signatures, binary members, complete source packages and full terms could not all be verified.')
        raise
