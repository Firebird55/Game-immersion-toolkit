"""Authored HTTP responses exercise real shared consent/budget contexts.

These checks cover corruption and concurrent spending before adapters can publish
an original snapshot. They are not live publisher or Android acceptance evidence.
"""
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import hashlib
from http.client import IncompleteRead
import io
import threading
from urllib.request import Request

import pytest

from backend.game_data import GameDataService, _Context
from backend.game_data_protocol import GameDataError, GameDataRequest
from backend.publisher_transport import PublisherTransport, _PublisherRedirect

URL = 'https://publisher.example/original'
DATA = b'authored original archive index'


class Response(io.BytesIO):
    def __init__(self, data=DATA, *, status=200, headers=None, url=URL):
        super().__init__(data)
        self.status, self.url, self.headers = status, url, Message()
        for key, value in (headers if headers is not None else {'Content-Length': str(len(data))}).items():
            self.headers[key] = value

    def geturl(self): return self.url


@pytest.fixture
def context(tmp_path):
    service = GameDataService(tmp_path, {})
    ctx = _Context(service, tmp_path, 'local', 'zzz', GameDataRequest('global', 'en'),
        tmp_path / 'stage', 'download', budget=1024)
    yield ctx
    service.close()


def transport(ctx, response, calls=None):
    def open_(request, **kwargs):
        if calls is not None: calls.append(request)
        return response() if callable(response) else response
    return PublisherTransport(ctx, hosts={'publisher.example'}, opener=open_)


def test_verified_range_is_atomic_and_bad_hash_keeps_previous_file(context):
    path = context.cache_directory / 'index.bin'
    path.parent.mkdir(parents=True); path.write_bytes(b'previous verified index')
    calls = []
    def response():
        return Response(status=206, headers={'Content-Length': str(len(DATA)),
            'Content-Range': f'bytes 100-{99 + len(DATA)}/1000'})
    client = transport(context, response, calls)
    for digest, succeeds in [('0' * 64, False), (hashlib.sha256(DATA).hexdigest(), True)]:
        if succeeds:
            receipt = client.download_to(URL, path, limit=len(DATA), original_range=(100, len(DATA), 1000), digests={'sha256': digest})
            assert path.read_bytes() == DATA and receipt.bytes == len(DATA)
            assert receipt.original_range == (100, len(DATA), 1000)
            assert URL not in str(receipt.json())
        else:
            with pytest.raises(GameDataError, match='checksum'):
                client.download_to(URL, path, limit=len(DATA), original_range=(100, len(DATA), 1000), digests={'sha256': digest})
            assert path.read_bytes() == b'previous verified index'
        assert not list(path.parent.glob('*.part'))
    assert all(request.get_header('Range') == f'bytes=100-{99 + len(DATA)}' for request in calls)


@pytest.mark.parametrize('phase,closed,kind', [('plan', False, 'asset'), ('restore', False, 'metadata'), ('download', True, 'asset')])
def test_missing_consent_or_closed_scope_never_opens_connection(context, phase, closed, kind):
    context.phase, context.transfers_closed = phase, closed
    calls = []
    with pytest.raises(GameDataError):
        transport(context, Response(), calls).fetch_bytes(URL, limit=100, kind=kind)
    assert calls == [] and context.consumed == 0


@pytest.mark.parametrize('response', [
    lambda: Response(status=200),  # Ignored Range.
    lambda: Response(status=206, headers={'Content-Range': 'bytes 101-130/1000'}),
    lambda: Response(headers={'Content-Length': '99999'}),
    lambda: Response(headers={'Content-Encoding': 'gzip'}),
    lambda: Response(url='https://unapproved.example/file'),
])
def test_changed_owner_range_encoding_and_size_are_rejected_before_body(context, response):
    value = response()
    kwargs = {'original_range': (100, len(DATA), 1000)} if value.status == 206 or value.headers.get('Content-Length') == str(len(DATA)) and value.geturl() == URL else {}
    with pytest.raises(GameDataError):
        transport(context, value).fetch_bytes(URL, limit=100, **kwargs)
    assert context.consumed == 0


def test_chunked_complete_body_requires_eof_not_a_matching_prefix(context):
    client = transport(context, lambda: Response(DATA + b'extra', headers={}))
    with pytest.raises(GameDataError) as error:
        client.fetch_bytes(URL, limit=100, expected_size=len(DATA), digests={'sha256': hashlib.sha256(DATA).hexdigest()})
    assert error.value.code == 'publisher_size_changed'
    good, receipt = transport(context, Response(headers={})).fetch_bytes(URL, limit=100, expected_size=len(DATA))
    assert good == DATA and receipt.bytes == len(DATA)


def test_truncated_and_cancelled_downloads_preserve_old_cache(context):
    path = context.cache_directory / 'original.bin'; path.parent.mkdir(parents=True); path.write_bytes(b'old')
    class Truncated(Response):
        def read(self, n=-1): raise IncompleteRead(b'partial', 9)
    class Cancelled(Response):
        def read(self, n=-1):
            result = super().read(n); context.cancel.set(); return result
    for response, code in [(Truncated(), 'metadata_download_interrupted'), (Cancelled(), 'preparation_cancelled')]:
        context.cancel.clear()
        with pytest.raises(GameDataError) as error:
            transport(context, response).download_to(URL, path, limit=100)
        assert error.value.code == code and path.read_bytes() == b'old'
        assert not list(path.parent.glob('*.part'))
        if code == 'metadata_download_interrupted':
            assert context.consumed == len(b'partial')


def test_concurrent_transfers_cannot_spend_the_same_remaining_budget(context):
    context.budget = len(DATA)
    calls = []; start = threading.Barrier(2)
    client = transport(context, lambda: Response(), calls)
    def run():
        start.wait(timeout=2)
        try:
            return client.fetch_bytes(URL, limit=len(DATA), expected_size=len(DATA))[0]
        except GameDataError as error: return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert DATA in results and 'download_budget_exhausted' in results
    assert len(calls) == 1 and context.consumed == len(DATA)


def test_unapproved_urls_redirects_and_destination_cannot_escape_cache(context):
    calls = []; client = transport(context, Response(), calls)
    for url in ['http://publisher.example/original', 'https://user:secret@publisher.example/original',
                'https://publisher.example:444/original', 'https://[invalid/original']:
        with pytest.raises(GameDataError): client.fetch_bytes(url, limit=100)
    with pytest.raises(GameDataError):
        _PublisherRedirect({'publisher.example'}).redirect_request(Request(URL), None, 302, '', {}, 'https://other.example/file')
    with pytest.raises(GameDataError): client.download_to(URL, '../outside.bin', limit=100)
    assert calls == [] and not (context.cache_directory.parent / 'outside.bin').exists()


def test_small_initial_metadata_header_learns_and_then_pins_original_owner(context):
    calls = []
    def response():
        return Response(status=206, headers={'Content-Length': str(len(DATA)),
            'Content-Range': f'bytes 0-{len(DATA)-1}/1000'})
    client = transport(context, response, calls)
    body, receipt = client.fetch_bytes(URL, limit=len(DATA), original_range=(0, len(DATA), None))
    assert body == DATA and receipt.original_range == (0, len(DATA), 1000)
    with pytest.raises(GameDataError) as error:
        client.fetch_bytes(URL, limit=len(DATA), original_range=(0, len(DATA), 999))
    assert error.value.code == 'publisher_range_changed'
    assert context.consumed == len(DATA)
    before = len(calls)
    for kind, original in [('audio', (0, len(DATA), None)), ('asset', (0, len(DATA), None)),
                           ('metadata', (1, len(DATA), None)), ('metadata', (0, 65537, None))]:
        with pytest.raises(ValueError):
            client.fetch_bytes(URL, limit=100000, kind=kind, original_range=original)
    assert len(calls) == before
