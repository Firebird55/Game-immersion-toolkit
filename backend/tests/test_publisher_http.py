"""Real HTTP checks for update freshness; format/activation tests live with the adapters."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from backend import publisher_http as http


@pytest.fixture
def publisher():
    routes, requests = {}, []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            row = routes[self.path]
            tag, modified = row.get('etag', ''), row.get('modified', '')
            condition = self.headers.get('If-None-Match') or self.headers.get('If-Modified-Since')
            status = row.get('status', 304 if condition and condition in (tag, modified) else 200)
            requests.append((self.path, condition, status))
            self.send_response(status)
            if tag:
                self.send_header('ETag', row.get('reply_etag', tag))
            if modified:
                self.send_header('Last-Modified', modified)
            if row.get('control'):
                self.send_header('Cache-Control', row['control'])
            if status == 200:
                self.send_header('Content-Length', str(row.get('length', len(row['body']))))
            self.end_headers()
            if status == 200:
                self.wfile.write(row['body'])
            self.close_connection = True

    http._cache.clear()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    try:
        yield SimpleNamespace(routes=routes, requests=requests, url=f'http://127.0.0.1:{server.server_port}')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        http._cache.clear()


def test_every_poll_revalidates_and_regions_and_changed_generations_stay_separate(publisher):
    p = publisher
    p.routes['/global'] = {'body': b'{"text":"old","audio":"one"}', 'etag': '"one"'}
    p.routes['/cn'] = {'body': b'{"text":"regional","audio":"one"}', 'etag': '"one"'}
    original = http.download(p.url + '/global')
    regional = http.download(p.url + '/cn')
    assert http.download(p.url + '/global') == original
    p.routes['/global'] = {'body': b'{"text":"translated","audio":"one"}', 'etag': '"two"'}
    text_update = http.download(p.url + '/global')
    assert json.loads(text_update)['text'] == 'translated'
    p.routes['/global'] = {'body': b'{"text":"translated","audio":"two"}', 'etag': '"three"'}
    voice_update = http.download(p.url + '/global')
    assert json.loads(voice_update)['audio'] == 'two'
    p.routes['/global']['reply_etag'] = 'W/"three"'
    assert http.download(p.url + '/global') == voice_update
    assert http.download(p.url + '/cn') == regional
    assert json.loads(original) == {'text': 'old', 'audio': 'one'}
    assert [row[2] for row in p.requests] == [200, 200, 304, 200, 200, 304, 304]


def test_truncation_network_errors_and_invalid_304_never_reuse_stale_metadata(publisher):
    p = publisher
    p.routes['/source'] = {'body': b'complete', 'etag': '"old"'}
    assert http.download(p.url + '/source') == b'complete'
    p.routes['/source'] = {'body': b'cut', 'etag': '"new"', 'length': 20}
    with pytest.raises(ValueError, match='truncated'):
        http.download(p.url + '/source')
    p.routes['/source']['status'] = 503
    with pytest.raises(HTTPError) as failed:
        http.download(p.url + '/source')
    assert failed.value.code == 503
    def offline(*_args, **_kwargs):
        raise URLError('offline fixture')
    with pytest.raises(URLError):
        http.download(p.url + '/source', opener=offline)
    p.routes['/source'] = {'body': b'complete', 'etag': '"old"', 'reply_etag': '"different"'}
    with pytest.raises(ValueError, match='different'):
        http.download(p.url + '/source')
    del p.routes['/source']['reply_etag']
    assert http.download(p.url + '/source') == b'complete'
    with pytest.raises(ValueError, match='size limit'):
        http.download(p.url + '/source', limit=3)
    assert p.requests[-1][1] is None
    p.routes['/unknown'] = {'body': b'', 'status': 304}
    with pytest.raises(ValueError, match='unsolicited'):
        http.download(p.url + '/unknown')


def test_last_modified_and_no_store_are_revalidated_without_disk_state(publisher):
    p = publisher
    p.routes['/dated'] = {'body': b'body', 'modified': 'Sun, 15 Nov 2026 12:00:00 GMT'}
    assert http.download(p.url + '/dated') == http.download(p.url + '/dated') == b'body'
    assert p.requests[-1][2] == 304
    p.routes['/dated']['control'] = 'no-store'
    assert http.download(p.url + '/dated') == b'body'
    assert http.download(p.url + '/dated') == b'body'
    assert p.requests[-1][1] is None
    p.routes['/dated'].pop('control')
    p.routes['/dated'].pop('modified')
    assert http.download(p.url + '/dated') == http.download(p.url + '/dated') == b'body'
    assert p.requests[-1][1] is None


def test_cache_storage_and_entry_limits_evict_without_suppressing_network_checks(publisher, monkeypatch):
    p = publisher
    monkeypatch.setattr(http, 'MAX_BYTES', 8)
    monkeypatch.setattr(http, 'MAX_ENTRY', 4)
    monkeypatch.setattr(http, 'MAX_ENTRIES', 2)
    for name in ['/first', '/second', '/third']:
        p.routes[name] = {'body': b'four', 'etag': '"same"'}
        assert http.download(p.url + name) == b'four'
    assert http.download(p.url + '/first') == b'four'
    assert p.requests[-1][1] is None
    p.routes['/large'] = {'body': b'five!', 'etag': '"large"'}
    assert http.download(p.url + '/large') == http.download(p.url + '/large') == b'five!'
    assert p.requests[-1][1] is None
    assert len(http._cache) <= 2 and sum(len(x.body) for x in http._cache.values()) <= 8
