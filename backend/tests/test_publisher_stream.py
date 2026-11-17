"""Whole-carrier verification must not buffer or accept an unchecked suffix.

These authored transport cases complement actual publisher APK extraction;
they establish neither Android runtime nor original publisher key rotation.
"""
import hashlib
from http.client import IncompleteRead

import pytest

from backend.game_data_protocol import GameDataError
from backend.publisher_transport import CHUNK
from backend.tests.test_publisher_transport import context, Response, transport, URL, DATA


def test_whole_carrier_is_bounded_while_only_selected_member_and_receipt_return(context):
    raw = b'x' * (CHUNK * 3 + 17)
    context.budget = len(raw)
    reads, leaked = [], []
    class Observed(Response):
        def read(self, size=-1):
            reads.append(size)
            assert 0 < size <= CHUNK
            return super().read(size)
    def consume(stream):
        leaked.append(stream)
        assert stream.read(0) == b''
        digest, selected, offset = hashlib.sha256(), bytearray(), 0
        while piece := stream.read(1024 * 1024):
            digest.update(piece)
            left, right = max(offset, CHUNK - 2), min(offset + len(piece), CHUNK + 3)
            if left < right:
                selected.extend(piece[left-offset:right-offset])
            offset += len(piece)
        return bytes(selected), digest.hexdigest()
    tag = '"original-carrier"'
    client = transport(context, Observed(raw, headers={'Content-Length': str(len(raw)), 'ETag': tag}))
    result, receipt = client.consume_stream(URL, consume, limit=len(raw), expected_size=len(raw),
        headers={'If-Match': tag}, digests={'sha256': hashlib.sha256(raw).hexdigest()})
    assert result == (b'xxxxx', receipt.sha256)
    assert receipt.bytes == context.consumed == len(raw) and receipt.response_etag == tag
    assert len(reads) == 4
    with pytest.raises(ValueError, match='closed'):
        leaked[0].read(1)


@pytest.mark.parametrize('headers,consumed', [({'Content-Length': str(len(DATA))}, 3), ({}, len(DATA))])
def test_return_before_whole_framed_body_or_unframed_eof_cannot_return_a_receipt(context, headers, consumed):
    leaked = []
    def prefix_only(stream):
        leaked.append(stream)
        return stream.read(consumed)
    with pytest.raises(GameDataError) as failure:
        transport(context, Response(headers=headers)).consume_stream(URL, prefix_only,
            limit=100, expected_size=len(DATA))
    assert failure.value.code == 'publisher_stream_incomplete'
    assert context.consumed == consumed
    with pytest.raises(ValueError): leaked[0].read(0)


def test_even_a_full_consumer_result_is_not_returned_when_publisher_hash_rejects(context):
    finished = []
    def consume(stream):
        value = bytearray()
        while chunk := stream.read(7): value.extend(chunk)
        finished.append(bytes(value))
        return 'provisional-only'
    with pytest.raises(GameDataError) as failure:
        transport(context, Response()).consume_stream(URL, consume, limit=100, expected_size=len(DATA),
            digests={'sha256': '0' * 64})
    assert finished == [DATA] and context.consumed == len(DATA)
    assert failure.value.code == 'publisher_checksum_mismatch'


@pytest.mark.parametrize('read_size', [-1, None, True])
def test_consumer_cannot_request_unbounded_or_noninteger_reads(context, read_size):
    with pytest.raises(ValueError, match='bounded'):
        transport(context, Response()).consume_stream(URL, lambda stream: stream.read(read_size),
            limit=100, expected_size=len(DATA))
    assert context.consumed == 0


def test_failed_consumer_releases_scope_and_accounts_only_actual_bytes(context):
    leaked = []
    def rejected(stream):
        leaked.append(stream)
        assert stream.read(3) == DATA[:3]
        raise ValueError('authored carrier parser rejected')
    with pytest.raises(ValueError, match='parser rejected'):
        transport(context, Response()).consume_stream(URL, rejected, limit=100, expected_size=len(DATA))
    assert context.consumed == 3
    with pytest.raises(ValueError): leaked[0].read(1)
    assert transport(context, Response()).fetch_bytes(URL, limit=100)[0] == DATA


def test_interrupt_and_cancellation_charge_actual_partial_input_and_revoke_handle(context):
    class Truncated(Response):
        def read(self, size): raise IncompleteRead(b'part', 9)
    class Cancelled(Response):
        def read(self, size):
            result = super().read(size)
            context.cancel.set()
            return result
    for response, expected, spent in [(Truncated(), 'metadata_download_interrupted', 4),
                                       (Cancelled(), 'preparation_cancelled', len(DATA))]:
        context.cancel.clear()
        before, leaked = context.consumed, []
        def consume(stream):
            leaked.append(stream)
            return stream.read(100)
        with pytest.raises(GameDataError) as failure:
            transport(context, response).consume_stream(URL, consume, limit=100, expected_size=len(DATA))
        assert failure.value.code == expected and context.consumed == before + spent
        with pytest.raises(ValueError): leaked[0].read(1)


@pytest.mark.parametrize('case', ['etag', 'consent', 'size'])
def test_consumer_never_runs_when_source_scope_or_declared_size_is_invalid(context, case):
    called, requests = [], []
    value = Response(headers={'Content-Length': str(len(DATA)), 'ETag': '"old"'})
    if case == 'consent': context.phase = 'plan'
    if case == 'size': value.headers.replace_header('Content-Length', str(len(DATA) + 1))
    options = {'headers': {'If-Match': '"new"'}} if case == 'etag' else {}
    with pytest.raises(GameDataError):
        transport(context, value, requests).consume_stream(URL, lambda stream: called.append(True),
            limit=100, expected_size=len(DATA), **options)
    assert called == [] and context.consumed == 0
    if case == 'consent': assert requests == []
