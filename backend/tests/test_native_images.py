"""Authored PE bytes exercise static review, never a native loader or compiler."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct

import pytest


@pytest.fixture
def images(monkeypatch):
    folder = Path(__file__).resolve().parents[2] / 'packaging/runtime-bundle'
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location('native_images_fixture', folder / 'native_images.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def authored_pe(*, machine=0x8664, plus=True, dll=True, flags=None, native_header=False,
                entry=None, imports=('KERNEL32.dll',), delayed=('optional.dll',), legacy_delay=False):
    """Independent tiny DOS/COFF/section/import/CLR layout; not executable media."""
    raw = bytearray(0x1400)
    def put(shape, offset, *values): struct.pack_into(shape, raw, offset, *values)
    def position(rva): return rva - 0x1000 + 0x400
    raw[:2] = b'MZ'; put('<I', 60, 0x80); raw[0x80:0x84] = b'PE\0\0'
    optional, width, directory = 0x98, 8 if plus else 4, 112 if plus else 96
    size = 240 if plus else 224
    put('<HH', 0x84, machine, 1); put('<HH', 0x94, size, 0x2002 if dll else 2)
    put('<H', optional, 0x20b if plus else 0x10b)
    base = 0x180000000 if plus else 0x400000
    put('<Q' if plus else '<I', optional + (24 if plus else 28), base)
    put('<II', optional + 32, 0x1000, 0x200)
    put('<II', optional + 56, 0x2000, 0x400)
    put('<I', optional + directory - 4, 16)
    section = optional + size
    raw[section:section + 8] = b'.owned\0\0'
    put('<IIII', section + 8, 0x1000, 0x1000, 0x1000, 0x400)
    put('<I', section + 36, 0x60000020)
    for delayed_table, names in ((False, imports), (True, delayed)):
        if not names: continue
        table = 0x1180 if delayed_table else 0x1100
        stride = 32 if delayed_table else 20
        put('<II', optional + directory + (13 if delayed_table else 1) * 8, table, stride * (len(names) + 1))
        for i, text in enumerate(names):
            name = (0x1380 if delayed_table else 0x1300) + i * 64
            lookup = (0x1580 if delayed_table else 0x1500) + i * 32
            iat = (0x1680 if delayed_table else 0x1600) + i * 32
            hint_name = (0x1780 if delayed_table else 0x1700) + i * 32
            encoded = text.encode('ascii') + b'\0'
            raw[position(name):position(name) + len(encoded)] = encoded
            hint = b'\0\0OwnedFunction\0'
            raw[position(hint_name):position(hint_name) + len(hint)] = hint
            put('<Q' if width == 8 else '<I', position(lookup), hint_name)
            put('<Q' if width == 8 else '<I', position(iat), hint_name)
            if delayed_table:
                convert = lambda rva: rva + base if legacy_delay else rva
                put('<IIIIIIII', position(table) + i * stride, 0 if legacy_delay else 1,
                    convert(name), convert(0x17f0), convert(iat), convert(lookup), 0, 0, 0)
            else:
                put('<IIIII', position(table) + i * stride, lookup, 0, 0, name, iat)
    if flags is not None:
        put('<II', optional + directory + 14 * 8, 0x1800, 72)
        put('<IHH', position(0x1800), 72, 2, 5)
        version = b'v4.0.30319\0'
        version += b'\0' * (-len(version) % 4)
        metadata = bytearray(struct.pack('<IHHII', 0x424a5342, 1, 1, 0, len(version)) + version)
        metadata += struct.pack('<HH', 0, 1)
        stream_start = len(metadata) + 12
        metadata += struct.pack('<II', stream_start, 24) + b'#~\0\0'
        metadata += struct.pack('<IBBBBQQ', 0, 2, 0, 0, 1, 0, 0)
        put('<II', position(0x1800) + 8, 0x1880, len(metadata))
        raw[position(0x1880):position(0x1880) + len(metadata)] = metadata
        token = entry if entry is not None else 0x1f00 if flags & 0x10 else 0 if dll else 0x06000001
        put('<II', position(0x1800) + 16, flags, token)
        if native_header:
            put('<II', position(0x1800) + 64, 0x1a00, 16)
            raw[position(0x1a00):position(0x1a00) + 4] = b'RTR\0'
    return bytes(raw)


def change(raw, shape, offset, *values):
    result = bytearray(raw); struct.pack_into(shape, result, offset, *values); return bytes(result)


def test_authored_native_and_legacy_delay_va_layouts(images):
    x64 = images.inspect_pe(authored_pe())
    assert (x64['machine'], x64['format'], x64['architecture'], x64['implementation']) == ('amd64', 'PE32+', 'x64', 'native')
    assert x64['imports'] == ['KERNEL32.dll'] and x64['delay_imports'] == ['optional.dll'] and x64['clr'] is None
    x86 = images.inspect_pe(authored_pe(machine=0x14c, plus=False, legacy_delay=True))
    assert x86['architecture'] == 'x86' and x86['delay_imports'] == ['optional.dll']
    assert images.inspect_pe(authored_pe(machine=0xaa64))['architecture'] == 'arm64'


@pytest.mark.parametrize('flags,architecture', [(1, 'anycpu'), (3, 'x86'), (0x20003, 'anycpu-32bit-preferred')])
def test_clr_32bit_pair_does_not_confuse_anycpu_with_native_x86(images, flags, architecture):
    value = images.inspect_pe(authored_pe(machine=0x14c, plus=False, flags=flags, dll=False))
    assert value['architecture'] == architecture and value['implementation'] == 'managed-il'
    assert value['clr']['bit32_required'] == (flags == 3)
    assert value['clr']['bit32_preferred'] == (flags == 0x20003)
    assert value['clr']['entry_point'] == 'managed-method'


def test_clr_native_hints_cannot_become_anycpu_and_entrypoint_interpretation_is_explicit(images):
    ready = images.inspect_pe(authored_pe(flags=1, native_header=True))
    assert ready['implementation'] == 'managed-native' and ready['architecture'] == 'x64'
    assert ready['clr']['managed_native_header'] is True
    mixed = images.inspect_pe(authored_pe(machine=0x14c, plus=False, flags=1, native_header=True))
    assert mixed['implementation'] == 'managed-native' and mixed['architecture'] == 'x86'
    assert images.inspect_pe(authored_pe(flags=0x10))['clr']['entry_point'] == 'native-rva'
    assert images.inspect_pe(authored_pe(flags=1, entry=0x26000001))['clr']['entry_point'] == 'managed-file'


@pytest.mark.parametrize('shape,offset,values', [
    ('<I', 60, (0xfffffff0,)), ('<H', 0x86, (97,)), ('<H', 0x94, (95,)),
    ('<H', 0x98, (0x10b,)), ('<I', 0x98 + 108, (17,)),
    ('<I', 0x188 + 20, (0xffffff00,)),
    ('<II', 0x98 + 112 + 8, (0x1ff0, 40)),
    ('<I', 0x500 + 12, (0x3000,)), ('<I', 0x500 + 16, (0,)),
    ('<II', 0x98 + 112 + 8, (0x1100, 20)),
    ('<I', 0x580, (2,)), ('<II', 0x98 + 112 + 13 * 8, (0x1180, 32)),
])
def test_malformed_and_truncated_header_directory_or_import_refuses(images, shape, offset, values):
    raw = change(authored_pe(), shape, offset, *values)
    with pytest.raises(images.NativeImageError): images.inspect_pe(raw)


@pytest.mark.parametrize('raw_overlap', [False, True])
def test_overlapping_virtual_or_raw_sections_are_ambiguous_not_first_match(images, raw_overlap):
    raw = change(authored_pe(), '<H', 0x86, 2)
    raw = change(raw, '<I', 0x98 + 56, 0x4000)
    raw = change(raw, '<IIII', 0x188 + 40 + 8, 0x1000, 0x3000 if raw_overlap else 0x1000, 0x1000 if raw_overlap else 0, 0x400)
    with pytest.raises(images.NativeImageError, match='ambiguous-rva'): images.inspect_pe(raw)


def test_virtual_padding_and_unterminated_name_cannot_borrow_later_file_bytes(images):
    raw = change(authored_pe(), '<I', 0x188 + 16, 0x800)
    raw = change(raw, '<I', 0x500 + 12, 0x1f00)
    with pytest.raises(images.NativeImageError): images.inspect_pe(raw)
    raw = bytearray(change(authored_pe(), '<I', 0x500 + 12, 0x1ff0))
    raw[-16:] = b'A' * 16
    with pytest.raises(images.NativeImageError, match='invalid-import'): images.inspect_pe(bytes(raw))


@pytest.mark.parametrize('name', [r'C:\PRIVATE\module.dll', '../PRIVATE.dll', 'PRIVATE name.dll', 'CON.dll', 'trailing.'])
def test_imports_never_publish_paths_controls_or_windows_aliases(images, name):
    with pytest.raises(images.NativeImageError, match='invalid-import') as failure:
        images.inspect_pe(authored_pe(imports=(name,)))
    assert 'PRIVATE' not in str(failure.value) and name not in str(failure.value)


def test_duplicate_import_descriptors_and_case_aliases_refuse(images):
    with pytest.raises(images.NativeImageError, match='invalid-import'):
        images.inspect_pe(authored_pe(imports=('KERNEL32.dll', 'kernel32.DLL'), delayed=()))


@pytest.mark.parametrize('flags,entry,native_header', [(0x20001, None, False), (0x20003, None, True),
    (0x11, 0x1f00, False), (0x10, 0, False), (1, 0x01000001, False), (0x80, None, False)])
def test_contradictory_or_unknown_clr_flags_and_entry_tokens_refuse(images, flags, entry, native_header):
    with pytest.raises(images.NativeImageError, match='invalid-clr'):
        images.inspect_pe(authored_pe(machine=0x14c, plus=False, flags=flags, entry=entry, native_header=native_header))


@pytest.mark.parametrize('offset,values', [(0xc00, (71,)), (0xc00, (80,)), (0xc08, (0, 64)),
    (0xc08, (0x1880, 0)), (0xc08, (0x1880, 0x1000)), (0xc80, (0,)), (0xc8c, (0xffff,))])
def test_clr_directory_cb_and_metadata_bounds_are_checked(images, offset, values):
    raw = change(authored_pe(flags=1), '<' + 'I' * len(values), offset, *values)
    with pytest.raises(images.NativeImageError): images.inspect_pe(raw)


@pytest.fixture
def candidate(tmp_path):
    base = tmp_path.resolve(); root = base / 'Application 漢字'
    content = {'ProxyTranscriptRuntime.exe': authored_pe(dll=False),
        'asr/ProxyTranscriptAsr.exe': authored_pe(dll=False),
        '_internal/bridge.dll': authored_pe(machine=0x14c, plus=False, flags=1),
        'asr/_internal/engine.pyd': authored_pe(), 'THIRD_PARTY/NOTICE.txt': b'authored notice'}
    for name, raw in content.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    files = [{'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in content.items()]
    directories = sorted({parent.as_posix() for name in content for parent in Path(name).parents if parent != Path('.')})
    value = {'schema': 'proxy-r19-runtime-inventory-v1', 'source_commit': 'a' * 40,
        'build_id': 'authored-image-review', 'profile': 'runtime-experiment', 'files': files, 'directories': directories,
        'file_count': len(files), 'bytes': sum(item['bytes'] for item in files), 'components': [], 'helpers': {},
        'codecs': {}, 'native_input_ownership': {}, 'gates': {}, 'r19_complete': False,
        'native_windows_11_acceptance': 'unavailable', 'installer': 'not-built'}
    path = base / 'RUNTIME-INVENTORY.json'; path.write_text(json.dumps(value), encoding='utf-8')
    return root, path, value


def save(path, value):
    value['file_count'] = len(value['files']); value['bytes'] = sum(item['bytes'] for item in value['files'])
    path.write_text(json.dumps(value), encoding='utf-8')


def test_review_uses_only_existing_inventory_and_binds_main_asr_and_managed_bytes(images, candidate):
    root, path, value = candidate; original = deepcopy(value)
    report = images.review_native_images(value, path, root)
    assert value == original and report['file_count'] == 4
    assert report['inventory'] == {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    records = {item['path']: item for item in report['files']}
    assert records['_internal/bridge.dll']['architecture'] == 'anycpu'
    assert records['asr/_internal/engine.pyd']['tree'] == 'asr' and records['ProxyTranscriptRuntime.exe']['tree'] == 'main'
    assert report['dynamic_loading'] == report['pinvoke_compatibility'] == report['native_closure'] == 'unverified'
    assert report['status'] == 'observed-not-approved'
    assert all(report[key] is False for key in ('source_delivery_approved', 'production_execution_allowed', 'r19_complete'))
    assert str(root) not in json.dumps(report)
    # Unlisted files are neither discovered nor silently added to a second inventory.
    (root / '_internal/unlisted.dll').write_bytes(b'not an image')
    assert images.review_native_images(value, path, root) == report


@pytest.mark.parametrize('flags', [3, 0x20003])
def test_x64_review_refuses_required_or_preferred_x86_without_rejecting_true_anycpu(images, candidate, flags):
    root, path, value = candidate
    target = root / '_internal/bridge.dll'
    raw = authored_pe(machine=0x14c, plus=False, flags=flags, dll=False)
    target.write_bytes(raw)
    value['files'][2].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()); save(path, value)
    with pytest.raises(images.NativeImageError, match='unsupported-architecture'):
        images.review_native_images(value, path, root)


@pytest.mark.parametrize('change', ['native-x86', 'arm64', 'primary-is-dll', 'primary-is-clr'])
def test_wrong_native_or_fixed_primary_architecture_cannot_be_hidden_by_inventory_hashes(images, candidate, change):
    root, path, value = candidate
    raw = authored_pe(machine=0x14c, plus=False, dll=False) if change == 'native-x86' else authored_pe(machine=0xaa64, dll=False) if change == 'arm64' else authored_pe() if change == 'primary-is-dll' else authored_pe(flags=1, dll=False)
    target = root / 'ProxyTranscriptRuntime.exe'; target.write_bytes(raw)
    value['files'][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()); save(path, value)
    with pytest.raises(images.NativeImageError, match='unsupported-architecture'):
        images.review_native_images(value, path, root)


@pytest.mark.parametrize('change', ['traversal', 'alias', 'unknown-field', 'noninteger-size', 'missing-parent', 'wrong-profile', 'root-directory', 'root-file'])
def test_entire_inventory_is_validated_before_any_native_path_is_selected(images, candidate, monkeypatch, change):
    root, path, value = candidate
    if change == 'traversal': value['files'][-1]['path'] = '../PRIVATE.txt'
    elif change == 'alias': value['files'][-1]['path'] = 'proxytranscriptruntime.EXE'
    elif change == 'unknown-field': value['files'][-1]['PRIVATE'] = str(root)
    elif change == 'noninteger-size': value['files'][-1]['bytes'] = True
    elif change == 'missing-parent': value['directories'].remove('_internal')
    elif change == 'root-directory': value['directories'].append('.')
    elif change == 'root-file': value['files'][-1]['path'] = '.'
    else: value['profile'] = 'runtime'
    save(path, value)
    targets = {os.path.normcase(str(root / item['path'])) for item in value['files'][:-1]}
    accesses = []; original = os.lstat
    def guarded(name, *args, **kwargs):
        if os.path.normcase(os.fspath(name)) in targets:
            accesses.append('native-leaf'); raise AssertionError('Native path selected too early')
        return original(name, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(os, 'lstat', guarded)
        with pytest.raises(images.NativeImageError): images.review_native_images(value, path, root)
    assert accesses == []


def test_inventory_raw_bytes_duplicates_and_image_bytes_are_independently_bound(images, candidate):
    root, path, value = candidate
    path.write_text('{"schema":"private duplicate",' + path.read_text()[1:])
    with pytest.raises(images.NativeImageError, match='invalid-inventory'):
        images.review_native_images(value, path, root)
    save(path, value)
    different = deepcopy(value); different['build_id'] = 'other'
    with pytest.raises(images.NativeImageError, match='inventory-changed'):
        images.review_native_images(different, path, root)
    (root / 'ProxyTranscriptRuntime.exe').write_bytes(b'changed image')
    with pytest.raises(images.NativeImageError, match='image-changed'):
        images.review_native_images(value, path, root)


@pytest.mark.parametrize('change', ['image', 'inventory'])
def test_mutation_after_actual_parse_refuses_the_whole_report(images, candidate, monkeypatch, change):
    root, path, value = candidate; original = images.inspect_pe
    def inspect(raw):
        result = original(raw)
        if change == 'image': (root / 'ProxyTranscriptRuntime.exe').write_bytes(raw[:-1] + b'X')
        else: path.write_bytes(path.read_bytes() + b'\n')
        return result
    monkeypatch.setattr(images, 'inspect_pe', inspect)
    with pytest.raises(images.NativeImageError, match='image-changed' if change == 'image' else 'inventory-changed'):
        images.review_native_images(value, path, root)


def test_linked_native_ancestor_refuses_before_leaf_metadata_or_open(images, candidate, monkeypatch):
    root, path, value = candidate
    link = root / '_internal'; outside = root.parent / 'outside'; link.rename(outside)
    try: link.symlink_to(outside, target_is_directory=True)
    except OSError: pytest.skip('This host cannot create the authored directory link.')
    targets = {os.path.normcase(str(folder / 'bridge.dll')) for folder in (link, outside)}
    accesses = []
    def guard(original):
        def called(name, *args, **kwargs):
            if os.path.normcase(os.fspath(name)) in targets:
                accesses.append('forbidden-leaf'); raise AssertionError('Linked native leaf was touched')
            return original(name, *args, **kwargs)
        return called
    with monkeypatch.context() as patch:
        patch.setattr(os, 'lstat', guard(os.lstat)); patch.setattr(os, 'stat', guard(os.stat)); patch.setattr(io, 'open', guard(io.open))
        with pytest.raises(images.NativeImageError, match='unsafe-image-path'):
            images.review_native_images(value, path, root)
    assert accesses == []
