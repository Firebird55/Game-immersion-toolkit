"""Complete original TextMap namespaces over publisher-owned design objects.

The fixed format describes logical names. Current catalog membership determines
the shard inventory and package route; no translated community row is an input.
Activation and publisher/helper generation receipts belong to the caller.
"""
import hashlib
import json
import re

from .genshin_original_containers import DesignCatalog, DataObjects, asset_identity
from .genshin_original_textmap import NativeTextMapParameters, _decode_shard, decode_textmaps


CODES = frozenset({'CHS', 'CHT', 'EN', 'JP', 'KR', 'FR', 'DE', 'ES', 'PT', 'RU', 'TH', 'VI', 'ID', 'IT', 'TR'})
MAX_SUFFIX = 4096


def check(value):
    if not value:
        raise ValueError('Incomplete or ambiguous original Genshin TextMap generation.')


class OriginalTables:
    """Read all current catalog-owned shards for one requested official locale."""
    def __init__(self, catalog, load_bundle, parameter_descriptions):
        check(isinstance(catalog, DesignCatalog) and callable(load_bundle))
        descriptions = tuple(parameter_descriptions)
        check(descriptions and all(isinstance(p, NativeTextMapParameters) for p in descriptions)
              and len({p.fingerprint() for p in descriptions}) == 1)
        self.catalog, self.load_bundle = catalog, load_bundle
        # Decoding uses the shared numeric contract; every equivalent method's
        # identity remains in the receipt. No native semantic owner is selected.
        self.descriptions = descriptions
        self.tables, self.receipts = {}, {}

    def inventory(self, code):
        check(code in CODES)
        entries = []
        for suffix in range(MAX_SUFFIX):
            found = []
            for namespace in ('TextMap', 'TextMap_Medium'):
                path = f'Data/_ExcelBinOutput/{namespace}/{code}/Hash/{suffix}'
                identity = asset_identity(path)
                if identity in self.catalog.assets:
                    found.append({'identity': identity, 'namespace': namespace, 'suffix': suffix,
                                  'bundle': self.catalog.locate(identity).bundle})
            check(len(found) <= 1)
            entries.extend(found)
        count = len(entries)
        check(0 < count < MAX_SUFFIX and count & (count - 1) == 0
              and [entry['suffix'] for entry in entries] == list(range(count)))
        return entries

    def read(self, code):
        check(code in CODES)
        if code in self.tables:
            return self.tables[code]
        entries = self.inventory(code)
        count = len(entries)
        groups = {}
        for entry in entries:
            groups.setdefault(entry['bundle'], []).append(entry)
        payloads, identities, proof = [], {'TextMap': set(), 'TextMap_Medium': set()}, []
        parameters = self.descriptions[0]  # Identical numeric contract, all method hashes retained below.
        for bundle, wanted in sorted(groups.items()):
            location = self.catalog.locate(wanted[0]['identity'])
            objects = self.load_bundle(location)
            check(isinstance(objects, DataObjects))
            for entry in wanted:
                payload = objects.resolve(self.catalog, entry['identity'], bundle)
                direct, aliases = _decode_shard(payload, parameters)
                keys = direct.keys() | aliases.keys()
                check(all(identity & (count - 1) == entry['suffix'] for identity in keys))
                identities[entry['namespace']].update(keys)
                payloads.append(payload)
                proof.append({**entry, 'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'rows': len(keys)})
        merged = decode_textmaps(payloads, parameters)
        check(len(proof) == count and merged
              and identities['TextMap'].isdisjoint(identities['TextMap_Medium'])
              and merged.keys() == identities['TextMap'] | identities['TextMap_Medium'])
        tables = {'full': {str(identity): text for identity, text in merged.items()},
                  'medium': {str(identity): merged[identity] for identity in identities['TextMap_Medium']}}
        receipt = {'schema': 'genshin-original-textmap-generation-v1', 'locale': code,
                   'catalog_sha256': self.catalog.sha256, 'parameters_sha256': parameters.fingerprint(),
                   'method_sha256s': sorted({p.method_sha256 for p in self.descriptions}),
                   'shards': sorted(proof, key=lambda row: row['suffix']), 'rows': len(merged),
                   'tables_sha256': hashlib.sha256(json.dumps(tables, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}
        # Publish only after every package, shard, alias, key and EOF succeeds.
        self.tables[code], self.receipts[code] = tables, receipt
        return tables

    def file(self, relative):
        match = re.fullmatch(r'TextMap/TextMap(_Medium)?([A-Z]{2,3})(?:_([01]))?\.json', relative)
        check(match and match[2] in CODES and (match[3] is None or match[2] in {'RU', 'TH'}))
        # Community catalogs split these two JSON exports. The original locale
        # has one complete shard inventory, shared by both legacy file aliases.
        return self.read(match[2])['medium' if match[1] else 'full']
