"""Data-only Genshin generation receipts; no publisher or native imports."""
import hashlib
import json
import re


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def check(value):
    if not value:
        raise ValueError('The Genshin source receipt is incomplete or belongs to another generation.')


def sha(value, length=64):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{' + str(length) + '}', value)


def validate(receipt, *, publisher, region, metadata_revision):
    """Reopen immutable provenance without fetching sources or relabeling data."""
    check(isinstance(receipt, dict) and receipt.get('schema') == 'genshin-controlled-generation-v1'
          and len(canonical(receipt)) <= 8 * 1024**2
          and region in ('global', 'cn') and receipt.get('region') == region
          and isinstance(publisher, str) and re.fullmatch('sophon-[a-f0-9]{64}', publisher)
          and receipt.get('publisher') == publisher and sha(metadata_revision, 40))
    coverage = {'TextMap': 'original-publisher', 'Readable': 'community-not-converted', 'Subtitle': 'community-not-converted'}
    if isinstance(receipt.get('original_text'), dict) and 'original_tables' in receipt['original_text']:
        coverage['ManualTextMap'] = 'original-publisher'
    check(receipt.get('coverage') == coverage)
    body = {key: value for key, value in receipt.items() if key != 'sha256'}
    check(receipt.get('sha256') == hashlib.sha256(canonical(body)).hexdigest())
    selection = receipt.get('bindings')
    check(isinstance(selection, dict) and selection.get('schema') == 'genshin-binding-selection-v1'
          and selection.get('game') == 'genshin' and selection.get('region') == region
          and selection.get('publisher') == publisher and selection.get('revision') == metadata_revision
          and selection.get('repository') in {'Dimbreath/animegamedata2', 'DimbreathBot/AnimeGameData'}
          and re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', str(selection.get('version')))
          and sha(selection.get('narrative_sha256')))
    markers = selection.get('markers')
    check(isinstance(markers, dict) and set(markers) == {'res', 'silence', 'design'}
          and all(isinstance(value, str) and re.fullmatch('[0-9]{1,12}', value) for value in markers.values()))
    source_region = selection.get('source_region')
    check(source_region in ('global', 'cn'))
    prefix = 'OSRELWin' if source_region == 'global' else 'CNRELWin'
    title = prefix + selection['version'] + '_R{res}_S{silence}_D{design}'.format(**markers)
    check(selection.get('title') == title)
    if source_region != region:
        check(region == 'global' and source_region == 'cn'
              and selection.get('reference_narrative_sha256') == selection['narrative_sha256'])
    else:
        check(selection.get('reference_narrative_sha256') is None)
    bootstrap = receipt.get('bootstrap')
    config = 'config_GIGlb.json' if region == 'global' else 'config_GICN.json'
    check(isinstance(bootstrap, dict) and bootstrap.get('game') == 'genshin'
          and bootstrap.get('region') == region and bootstrap.get('policy') == 'immutable-community-hybrid'
          and bootstrap.get('repository') == 'CollapseLauncher/CollapseLauncher-ReleaseRepo'
          and sha(bootstrap.get('revision'), 40)
          and isinstance(bootstrap.get('files'), dict) and set(bootstrap['files']) == {'config_master.json', config})
    for item in bootstrap['files'].values():
        check(isinstance(item, dict) and set(item) == {'sha256', 'bytes'} and sha(item['sha256'])
              and type(item['bytes']) is int and 0 < item['bytes'] <= 1024**2)
    source = receipt.get('original_text')
    check(isinstance(source, dict) and source.get('schema') == 'genshin-original-text-source-v1'
          and source.get('publisher') == publisher and sha(source.get('official_design_index_sha256'))
          and sha(source.get('catalog_sha256')) and sha(source.get('helper_identity')))
    software = source.get('format_software')
    check(isinstance(software, dict) and set(software) == {'genshin_original_containers', 'genshin_official_text', 'genshin_official_source'}
          and all(sha(value) for value in software.values()))
    build = source.get('publisher_descriptor')
    check(isinstance(build, dict) and build.get('channel') == 'genshin-' + region
          and build.get('version') == selection['version']
          and 'sophon-' + hashlib.sha256(json.dumps(build, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == publisher)
    hotfix = build.get('hotfix')
    check(isinstance(hotfix, dict) and isinstance(hotfix.get('revisions'), dict)
          and all(isinstance(hotfix['revisions'].get(name), (list, tuple)) and len(hotfix['revisions'][name]) == 2
                  and str(hotfix['revisions'][name][0]) == markers[name] for name in markers)
          and isinstance(hotfix.get('indexes'), dict) and isinstance(hotfix['indexes'].get('design'), (list, tuple))
          and len(hotfix['indexes']['design']) == 2
          and sha(source.get('official_design_index_md5'), 32)
          and source['official_design_index_md5'] == hotfix['indexes']['design'][0])
    codec = source.get('codec_description')
    check(isinstance(codec, dict) and sha(codec.get('parameters_sha256')))
    if codec.get('policy') == 'controlled-community-codec-description-v1':
        # Retained snapshots keep their original, honestly weaker provenance.
        check(codec.get('repository') == 'Escartem/AnimeStudio'
              and codec.get('path') == 'AnimeStudio/Crypto/CryptoHelper.cs'
              and sha(codec.get('revision'), 40) and sha(codec.get('sha256'))
              and type(codec.get('bytes')) is int and 0 < codec['bytes'] <= 1024**2)
    else:
        check(codec.get('policy') == 'official-native-blb-parameters-v1'
              and sha(codec.get('native_sha256')) and sha(codec.get('publisher_md5'), 32)
              and sha(codec.get('reader_sha256')) and codec.get('semantic_owner_claim') is False
              and type(codec.get('bytes')) is int and 512 <= codec['bytes'] <= 768 * 1024**2
              and isinstance(codec.get('method_sha256s'), list) and 1 <= len(codec['method_sha256s']) <= 128
              and codec['method_sha256s'] == sorted(set(codec['method_sha256s']))
              and all(sha(method) for method in codec['method_sha256s']))
    native = source.get('native')
    methods = native.get('method_sha256s') if isinstance(native, dict) else None
    check(isinstance(native, dict) and sha(native.get('sha256')) and sha(native.get('publisher_md5'), 32)
          and native.get('name') == ('GenshinImpact.exe' if region == 'global' else 'YuanShen.exe')
          and type(native.get('bytes')) is int and 512 <= native['bytes'] <= 768 * 1024**2
          and sha(native.get('template_reader_sha256'))
          and sha(native.get('parameters_sha256')) and native.get('semantic_owner_claim') is False
          and isinstance(methods, list) and 1 <= len(methods) <= 128 and methods == sorted(set(methods))
          and all(sha(method) for method in methods))
    if codec['policy'] == 'official-native-blb-parameters-v1':
        check(codec['native_sha256'] == native['sha256'] and codec['publisher_md5'] == native['publisher_md5']
              and codec['bytes'] == native['bytes'])
    if 'original_tables' in source:
        check(codec['policy'] == 'official-native-blb-parameters-v1')
        tables = source['original_tables']
        check(isinstance(tables, dict) and set(tables) == {'ManualTextMapConfigData'})
        table = tables['ManualTextMapConfigData']
        check(isinstance(table, dict) and isinstance(table.get('owner'), dict) and isinstance(table.get('proof'), dict))
        owner, proof = table['owner'], table['proof']
        manifests = build.get('manifests')
        check(isinstance(manifests, dict) and isinstance(manifests.get('game'), (list, tuple))
              and 0 < len(manifests['game']) <= 32)
        logical = b'Data/_ExcelBinOutput/ManualTextMapConfigData.MiHoYoBinData'
        logical += bytes(256 - len(logical) % 256)
        expected_asset = int.from_bytes(hashlib.md5(logical).digest()[:8], 'little')
        check(owner.get('publisher') == publisher and owner.get('native_sha256') == native['sha256']
              and owner.get('catalog_sha256') == source['catalog_sha256']
              and owner.get('manifest_sha256') == hashlib.sha256(json.dumps(manifests['game'],
                  sort_keys=True, separators=(',', ':')).encode()).hexdigest()
              and owner.get('asset_index') == expected_asset and type(owner.get('bundle')) is int and owner['bundle'] > 0
              and sha(owner.get('payload_sha256')))
        metadata = owner.get('metadata')
        check(isinstance(metadata, dict) and metadata.get('name') ==
              ('GenshinImpact_Data' if region == 'global' else 'YuanShen_Data') + '/Native/Data/Metadata/global-metadata.dat'
              and sha(metadata.get('sha256')) and sha(metadata.get('publisher_md5'), 32)
              and type(metadata.get('bytes')) is int and 512 <= metadata['bytes'] <= 256 * 1024**2)
        software = owner.get('software_sha256')
        check(isinstance(software, dict) and 4 <= len(software) <= 64
              and {'genshin_original_excel.py', 'genshin_original_dialogue.py', 'genshin_native_words.py',
                   'genshin_native_contracts.py'} <= software.keys()
              and all(isinstance(name, str) and re.fullmatch(r'genshin_(?:native|original)_[a-z0-9_]+\.py', name)
                      and sha(value) for name, value in software.items()))
        check(proof.get('schema') == 'genshin-original-manual-table-v1' and proof.get('strict_eof') is True
              and proof.get('source_kind') == 'original-publisher'
              and type(proof.get('rows')) is int and 0 < proof['rows'] <= 1_000_000
              and proof.get('payload_sha256') == owner['payload_sha256']
              and type(proof.get('payload_bytes')) is int and 4 <= proof['payload_bytes'] <= 64 * 1024**2
              and sha(proof.get('canonical_sha256')) and sha(proof.get('contract_sha256'))
              and isinstance(proof.get('method_sha256s'), list) and 1 <= len(proof['method_sha256s']) <= 3
              and all(sha(method) for method in proof['method_sha256s'])
              and proof['method_sha256s'] == sorted(set(proof['method_sha256s'])))
    locales = source.get('locales')
    check(isinstance(locales, dict) and 0 < len(locales) <= 15)
    for code, item in locales.items():
        check(code in {'CHS', 'CHT', 'EN', 'JP', 'KR', 'FR', 'DE', 'ES', 'PT', 'RU', 'TH', 'VI', 'ID', 'IT', 'TR'}
              and isinstance(item, dict) and item.get('schema') == 'genshin-original-textmap-generation-v1'
              and item.get('locale') == code and item.get('catalog_sha256') == source['catalog_sha256']
              and item.get('method_sha256s') == methods and item.get('parameters_sha256') == native['parameters_sha256']
              and type(item.get('rows')) is int and item['rows'] > 0 and sha(item.get('tables_sha256')))
        shards = item.get('shards')
        check(isinstance(shards, list) and all(isinstance(row, dict) for row in shards)
              and 0 < len(shards) < 4096 and len(shards) & (len(shards) - 1) == 0
              and [row.get('suffix') for row in shards] == list(range(len(shards))))
        for row in shards:
            check(row.get('namespace') in {'TextMap', 'TextMap_Medium'} and type(row.get('identity')) is int
                  and 0 <= row['identity'] < 1 << 64 and type(row.get('bundle')) is int and row['bundle'] > 0
                  and sha(row.get('sha256')) and type(row.get('bytes')) is int and 8 <= row['bytes'] <= 64 * 1024**2)
    packages = source.get('packages')
    check(isinstance(packages, dict) and 1 <= len(packages) <= 4096)
    for name, package in packages.items():
        check(isinstance(name, str) and re.fullmatch(r'blocks/[0-9]{2,10}/[0-9]{1,10}\.blk', name)
              and isinstance(package, dict) and sha(package.get('publisher_md5'), 32)
              and sha(package.get('decoded_sha256')) and type(package.get('publisher_bytes')) is int
              and 0 < package['publisher_bytes'] <= 160 * 1024**2 and type(package.get('decoded_bytes')) is int
              and 0 < package['decoded_bytes'] <= 512 * 1024**2)
    return receipt


def make(catalog, publisher, region):
    source = getattr(catalog, 'official_source', None)
    check(source is not None)
    receipt = {'schema': 'genshin-controlled-generation-v1', 'publisher': publisher, 'region': region,
               'bindings': catalog.selection_receipt, 'bootstrap': catalog.bootstrap_receipt,
               'original_text': source.receipt(),
               'coverage': {'TextMap': 'original-publisher', 'Readable': 'community-not-converted',
                            'Subtitle': 'community-not-converted'}}
    if 'original_tables' in receipt['original_text']:
        receipt['coverage']['ManualTextMap'] = 'original-publisher'
    receipt['sha256'] = hashlib.sha256(canonical(receipt)).hexdigest()
    return validate(receipt, publisher=publisher, region=region, metadata_revision=catalog.revision)
