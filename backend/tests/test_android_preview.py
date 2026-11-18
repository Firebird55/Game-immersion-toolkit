"""Actual HTTP preview geometry, privacy fences and late bitmap publication."""
import base64
import io
import json
import threading
import uuid

from PIL import Image, ImageDraw
import pytest

from backend.tests.test_android_host import host, request
from backend.tests.test_android_receiver import control
from backend.tests.test_prepared_session import fixture_library


class BitmapAdapter:
    def __init__(self):
        self.crops = []
        self.entered = self.release = None

    def submit(self, raw, *_):
        with Image.open(io.BytesIO(raw)) as image:
            return json.dumps({'width': image.width, 'height': image.height})

    def preview(self, raw, x, y, width, height):
        self.crops.append((x, y, width, height))
        if self.entered:
            self.entered.set();assert self.release.wait(3)
        with Image.open(io.BytesIO(raw)) as source:
            image = source.crop((x, y, x + width, y + height))
            output = io.BytesIO();image.save(output, format='JPEG')
            return base64.b64encode(output.getvalue()).decode()


def ready(host, tmp_path):
    archive, _ = fixture_library(tmp_path / 'input', game='nte')
    host.session.import_library(archive)
    host.session.update_settings({'nte_picture_area': '16:9',
        'nte_region': {'left': .5, 'top': .5, 'width': .5, 'height': .5}})
    host.native = BitmapAdapter()
    identity = str(uuid.uuid4());_, result = control(host, identity, 1, 'start')
    source = Image.new('RGB', (1600, 1200), 'black')
    draw = ImageDraw.Draw(source);draw.rectangle((0, 150, 1599, 1049), fill='blue')
    draw.rectangle((800, 600, 1599, 1049), fill='red')
    raw = io.BytesIO();source.save(raw, format='PNG')
    headers = {'Content-Type': 'image/png', 'X-Toolkit-Generation': str(result['generation']),
        'X-Toolkit-Frame': '1', 'X-Toolkit-Receiver-Id': identity, 'X-Toolkit-Receiver-Revision': '1',
        'X-Toolkit-Document-Epoch': host.document_epoch}
    assert request(host, 'POST', '/api/capture/frame', raw.getvalue(), headers=headers)[0] == 202
    return identity, raw.getvalue(), headers


def test_preview_uses_real_admitted_frame_and_same_black_bar_crop_as_ocr(host, tmp_path):
    assert request(host, 'GET', '/api/capture/preview.jpg')[0] == 404
    _, _, _ = ready(host, tmp_path)
    epoch, generation = host.document_epoch, host.session.generation
    status, raw = request(host, 'GET', '/api/capture/preview.jpg?t=1')
    assert status == 200 and host.native.crops[-1] == (800, 600, 800, 450)
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == (800, 450) and image.getpixel((0, 0))[0] > 240
    capture = request(host, 'GET', '/api/snapshot')[1]['status']['capture']
    assert capture['window_bounds'] == [0, 0, 1600, 1200] and capture['crop_bounds'] == [800, 600, 800, 450]
    assert request(host, 'GET', '/api/capture/preview.jpg?left=0&top=0&width=1&height=1&picture_area=window')[0] == 200
    assert host.native.crops[-1] == (0, 0, 1600, 1200)
    # Preview GET cannot refresh ownership/generation or change saved settings.
    assert (host.document_epoch, host.session.generation) == (epoch, generation)
    assert host.session.settings.get().nte_region.left == .5
    observed = []
    host.session.observe = lambda *args, **kwargs: observed.append((args[2], kwargs['channel'])) or []
    host.accept_ocr(generation, 1, json.dumps({'width': 1600, 'height': 1200, 'blocks': [
        {'text': 'inside crop', 'rect': [900, 700, 1500, 800]},
        {'text': 'black bar is outside picture', 'rect': [10, 10, 500, 80]},
        {'text': 'outside dialogue crop', 'rect': [20, 200, 500, 300]}]}))
    assert ('inside crop' in observed[0][0]) and 'black bar is outside picture' not in observed[-1][0]


@pytest.mark.parametrize('query', ['left=.1', 'left=0&top=0&width=nan&height=1',
    'left=0&top=0&width=0&height=1', 'left=.8&top=0&width=.5&height=1',
    'picture_area=guess', 'left=0&left=.1&top=0&width=1&height=1'])
def test_malformed_preview_crop_fails_without_native_decode(host, query):
    assert request(host, 'GET', '/api/capture/preview.jpg?' + query)[0] == 422


@pytest.mark.parametrize('invalidate', ['pause', 'settings', 'document', 'stop', 'import'])
def test_slow_bitmap_cannot_publish_after_scope_invalidation(host, tmp_path, invalidate):
    identity, _, _ = ready(host, tmp_path)
    entered, release = threading.Event(), threading.Event()
    host.native.entered, host.native.release = entered, release
    result = []
    worker = threading.Thread(target=lambda: result.append(request(host, 'GET', '/api/capture/preview.jpg')))
    worker.start();assert entered.wait(2)
    if invalidate == 'pause':
        host.pause()
    elif invalidate == 'settings':
        host.session.update_settings({'nte_picture_area': 'window'})
    elif invalidate == 'document':
        request(host, 'GET', '/')
    elif invalidate == 'stop':
        assert control(host, identity, 2, 'stop')[0] == 200
    else:
        archive, _ = fixture_library(tmp_path / 'next', game='nte', text='The next chapter uses a different original recording.')
        host.session.import_library(archive)
    release.set();worker.join(3)
    assert not worker.is_alive() and result[0][0] == 404
    assert host.preview_frame is None and host.frame_geometry is None
    assert request(host, 'GET', '/api/capture/preview.jpg')[0] == 404


def test_old_frame_and_rotation_cannot_replace_current_preview(host, tmp_path):
    _, raw, headers = ready(host, tmp_path)
    original = host.preview_frame
    assert request(host, 'POST', '/api/capture/frame', raw, headers=headers)[0] == 409
    assert host.preview_frame is original
    rotated = io.BytesIO();Image.new('RGB', (1200, 1600)).save(rotated, format='PNG')
    assert request(host, 'POST', '/api/capture/frame', rotated.getvalue(),
        headers={**headers, 'X-Toolkit-Frame': '2'})[0] == 409
    assert host.preview_frame is None and not host.session.running


def test_native_decode_failure_is_an_unavailable_image_without_scope_change(host, tmp_path):
    ready(host, tmp_path)
    generation = host.session.generation
    def failed(*args):
        raise RuntimeError('authored private provider diagnostics')
    host.native.preview = failed
    status, result = request(host, 'GET', '/api/capture/preview.jpg')
    assert status == 404 and 'provider' not in json.dumps(result)
    assert host.session.generation == generation and host.session.running
