from types import SimpleNamespace
import platform
import sys

import pytest

from backend import genshin_native_x64 as native
from backend.genshin_native_sources import index_caches, descriptor_asset


requires_decoder = pytest.mark.skipif(not (sys.platform == 'win32' and platform.machine().lower() in ('amd64', 'x86_64')),
                                     reason='Pinned Windows-amd64 decoder only')


def image_for(codes):
    sequences = {rva: list(native.decoder().disasm(bytes.fromhex(code), 0x1000 + rva))
                 for rva, code in codes.items()}

    def instructions(rva):
        if rva not in sequences:
            raise ValueError('No synthetic owned native method')
        return sequences[rva]

    def window(rva):
        raise ValueError('No synthetic target body')

    return SimpleNamespace(base=0x1000, instructions=instructions, window=window)


def paths(*rvas):
    return [{'method_rva': rva, 'reference_rva': rva,
             'literals': ({'path': 'Data/_BinOutput/IndexDic/Current'},)} for rva in rvas]


@requires_decoder
@pytest.mark.parametrize('offset', ['40', '68'])
def test_source_index_cache_binds_typed_call_output_not_field_position(offset):
    # literal -> rcx; out stack -> rdx; call actual typed loader;
    # out value -> rax; arena global -> rbx; cache <- rax.
    code = '488b0d00000000488d542420e8f0010000488b442420488b1d00000000488943' + offset + 'c3'
    view = SimpleNamespace(image=image_for({100: code}))
    loader = 100 + 12 + 5 + 0x1f0
    owned = {'paths': ('Data/_BinOutput/IndexDic/Current', 'Data/_BinOutput/IndexDic/Unknown'),
             'loader': {'rva': loader}}
    result = index_caches(view, paths(100), owned)
    assert result['caches'][0]['cache_offset'] == int(offset, 16)
    assert result['caches'][0]['arena_global_rva'] == 100 + 29
    assert result['unresolved_paths'] == ('Data/_BinOutput/IndexDic/Unknown',)


@requires_decoder
@pytest.mark.parametrize('middle', ['31c0', 'e800000000'])
def test_clobbered_or_unproved_post_call_output_cannot_own_cache(middle):
    code = '488b0d00000000488d542420e8f0010000488b442420' + middle + '488b1d0000000048894340c3'
    view = SimpleNamespace(image=image_for({100: code}))
    owned = {'paths': ('Data/_BinOutput/IndexDic/Current',), 'loader': {'rva': 100 + 12 + 5 + 0x1f0}}
    with pytest.raises(ValueError, match='No original source-index cache'):
        index_caches(view, paths(100), owned)


@requires_decoder
def test_direct_branch_and_nonvolatile_pointer_survive_unrelated_call():
    code = '488b0d00000000488d542420e8f0010000488b742420eb00e800000000488b1d0000000048897340c3'
    view = SimpleNamespace(image=image_for({100: code}))
    owned = {'paths': ('Data/_BinOutput/IndexDic/Current',), 'loader': {'rva': 100 + 12 + 5 + 0x1f0}}
    result = index_caches(view, paths(100), owned)
    assert result['caches'][0]['cache_offset'] == 64


@requires_decoder
def test_passing_local_output_address_to_another_call_invalidates_it():
    code = '488b0d00000000488d542420e8f0010000488d4c2420e800000000488b742420488b1d0000000048897340c3'
    view = SimpleNamespace(image=image_for({100: code}))
    owned = {'paths': ('Data/_BinOutput/IndexDic/Current',), 'loader': {'rva': 100 + 12 + 5 + 0x1f0}}
    with pytest.raises(ValueError, match='No original source-index cache'):
        index_caches(view, paths(100), owned)


@requires_decoder
@pytest.mark.parametrize('overwrite', ['488d5c242048c70300000000', '488d5c242048895c2428'])
def test_aliased_local_write_or_escaped_address_invalidates_index_output(overwrite):
    code = ('488b0d00000000488d542420e8f0010000' + overwrite
            + '488b742420488b1d0000000048897340c3')
    view = SimpleNamespace(image=image_for({100: code}))
    owned = {'paths': ('Data/_BinOutput/IndexDic/Current',), 'loader': {'rva': 100 + 12 + 5 + 0x1f0}}
    with pytest.raises(ValueError, match='No original source-index cache'):
        index_caches(view, paths(100), owned)


@requires_decoder
def test_same_source_path_conflicting_native_cache_stores_reject():
    prefix = '488b0d00000000488d542420'
    first = prefix + 'e8f0010000488b442420488b1d0000000048894340c3'
    second = prefix + 'e88c010000488b442420488b1d0000000048894368c3'
    view = SimpleNamespace(image=image_for({100: first, 200: second}))
    owned = {'paths': ('Data/_BinOutput/IndexDic/Current',), 'loader': {'rva': 100 + 12 + 5 + 0x1f0}}
    with pytest.raises(ValueError, match='conflicting native caches'):
        index_caches(view, paths(100, 200), owned)


@requires_decoder
@pytest.mark.parametrize('element', ['488b4cd320', '488b7cd3204889f9'])
def test_registered_array_element_origin_accepts_direct_and_copied_arguments(element):
    from backend.genshin_native_talk import array_element_origin
    from backend.genshin_native_words import Context
    image = image_for({100: '4889ce488b5e10' + element + 'e800000000c3'})
    context = Context(image, 100)
    call = next(ins for ins in context.seq if ins.mnemonic == 'call')
    assert array_element_origin(context, native.Definitions(context.seq), call.address) == ('field', ('input', 'rcx'), 16)


@requires_decoder
@pytest.mark.parametrize('element', ['8b4cd320', '488b4c9320'])
def test_array_element_proof_rejects_scalar_and_wrong_stride(element):
    from backend.genshin_native_talk import array_element_origin
    from backend.genshin_native_words import Context
    image = image_for({100: '4889ce488b5e10' + element + 'e800000000c3'})
    context = Context(image, 100)
    call = next(ins for ins in context.seq if ins.mnemonic == 'call')
    with pytest.raises(ValueError):
        array_element_origin(context, native.Definitions(context.seq), call.address)


@requires_decoder
@pytest.mark.parametrize('instance,offset', [(False, 40), (True, 72)])
def test_descriptor_asset_role_uses_original_static_or_instance_argument(instance, offset):
    from backend.genshin_native_attributes import Attributes, attribute_profile
    from backend.tests.test_genshin_native_attributes import fixture
    import struct
    attribute_view, initializer, _ = fixture(1)
    attributes = Attributes.__new__(Attributes)
    attributes.view, attributes.profile = attribute_view, attribute_profile(attribute_view, initializer)
    code = bytes.fromhex('4889d7' if instance else '4889cf') + bytes.fromhex('488b4f') + bytes([offset])
    code += b'\xe8' + struct.pack('<i', 0x300 - 0x100 - len(code) - 5) + b'\xc3'
    image = image_for({0x100: code.hex(), 0x300: 'c3'})
    method = {'index': 1 if instance else 0, 'rva': 0x100, 'return_type': {'kind': 1},
              'parameters': [{'type': {'definition': 7, 'kind': 18}}]}
    opener = {'index': 0, 'rva': 0x300, 'return_type': {'index': 123, 'kind': 18},
              'parameters': [{'type': {'kind': 11}}]}
    view = SimpleNamespace(image=image, methods=lambda definition: [method],
                           methods_at=lambda rva: [{'owner': {'definition': 8}, 'method': opener}] if rva == 0x300 else [],
                           field_offsets=lambda definition: [{'authored_offset_word': offset, 'type': {'kind': 11}}])
    role = descriptor_asset(view, 9, 7, 123, attributes)
    assert role['asset_offset'] == offset
    assert role['proofs'][0]['descriptor_argument'] == ('rdx' if instance else 'rcx')
    # Identical native field syntax must not be assigned to Descriptor when
    # current original metadata proves the opposite incoming argument slot.
    method['index'] = 0 if instance else 1
    with pytest.raises(ValueError, match='no unique native owner'):
        descriptor_asset(view, 9, 7, 123, attributes)
