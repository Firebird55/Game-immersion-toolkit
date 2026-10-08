from datetime import datetime, timezone
from types import SimpleNamespace

from PIL import Image

from backend.capture import CaptureService, StableMatchTracker
from backend.models import AppSettings, TextMatch
from backend.storage import TranscriptStore
from backend.windows import WindowInfo


def test_hito_two_boxes_emit_independently_without_voice_and_touch_repeats(tmp_path, monkeypatch):
    service = object.__new__(CaptureService)
    service.settings = SimpleNamespace(get=AppSettings)
    service._tracker = StableMatchTracker(2)
    service._tip_tracker = StableMatchTracker(1)
    service._scan_epoch = 0
    service.agent_recognizer = None
    service.transcript = TranscriptStore(tmp_path / 'db.sqlite')
    service.session_id = 'test'
    service._capture = lambda bounds: Image.new('RGB', (bounds[2], bounds[3]))
    service._set_preview = lambda image: None
    snapshots = []
    service._update_snapshot = lambda **values: snapshots.append(values)
    monkeypatch.setattr('backend.capture.executable_path_for_window', lambda window: None)

    def match(lines):
        text = ' '.join(lines)
        if not text:
            return None
        return TextMatch(game='hito', text_id='hito:'+text, english=text, chinese=text,
                         source_ocr=text, score=100, kind='exact')

    service.hito = SimpleNamespace(ready=True, ensure_game_files=lambda path: None, match_lines=match)
    class Engine:
        calls = 0
        top = 'top'
        def recognize_pil(self, image):
            self.calls += 1
            return {'lines':[{'text':'bottom' if self.calls % 2 else self.top}]}
    engine = Engine()
    window = WindowInfo(handle=1, title="Hito's World", process_name="Hito's World.exe", bounds=(0,0,1920,1200))
    now = datetime.now(timezone.utc)
    first = service._scan_hito(window,engine,0,now).emitted_lines
    assert len(first) == 1 and first[0].channel == 'tip' and not first[0].voiced
    second = service._scan_hito(window,engine,0,now).emitted_lines
    assert len(second) == 1 and second[0].channel == 'dialogue'
    assert not service._scan_hito(window,engine,0,now).emitted_lines
    engine.top = ''
    service._scan_hito(window,engine,0,now)
    service._scan_hito(window,engine,0,now)
    engine.top = 'top'
    repeated = service._scan_hito(window,engine,0,now).emitted_lines
    assert repeated[0].id == first[0].id
    assert service.transcript.count(game='hito') == 2
    assert snapshots[-1]['tip_crop_bounds'] != snapshots[-1]['crop_bounds']


def test_mixed_hito_tutorial_replaces_latin_ocr_and_removes_ruby_pinyin(tmp_path):
    from backend.hito import HitoTextIndex

    def row(text, x, y, width, height, words=None):
        return dict(text=text, bounding_rect=dict(x1=x, y1=y, x2=x+width, y2=y,
                    x3=x+width, y3=y+height, x4=x, y4=y+height), words=words or [])

    image = Image.new('RGB', (600, 180))
    image.paste((255, 170, 70), (450, 95, 550, 155))
    highlighted = row('说话', 450, 95, 100, 60)
    engine = SimpleNamespace(recognize_pil=lambda image: {'lines': [highlighted]})
    response = {'lines': [
        row('I can tap or use the arrow keys', 0, 0, 590, 45),
        row('shuohua', 450, 60, 100, 28),
        row('to move and talk with ixis', 0, 95, 550, 60, [
            row('to move and talk with', 0, 95, 425, 60),
            row('ixis', 450, 95, 100, 60),
        ]),
    ]}
    lines = CaptureService._hito_ocr_lines(image, response, engine)
    assert lines == ['I can tap or use the arrow keys', 'to move and talk with 说话']
    index = HitoTextIndex(tmp_path)
    index._records = [dict(chinese='I can tap or use the arrow keys to move and talk with 说话',
                           english='I can tap or use the arrow keys to move and talk with to speak')]
    index._load_pinyin({'vocabulary': [{'pinyin': 'shuo hua'}]})
    match = index.match_lines(lines)
    assert match and match.score == 100
    assert match.chinese.endswith('说话')


def test_hito_box_detection_follows_resolution_and_game_zoom():
    from PIL import ImageDraw

    for width, height, panel in (
        (1920, 1080, (.28, .78, .72, .93)),
        (3840, 2160, (.28, .78, .72, .93)),
        (1280, 800, (.18, .65, .82, .91)),
    ):
        image = Image.new('RGB', (width, height))
        coords = tuple(round(value * (width if i % 2 == 0 else height)) for i, value in enumerate(panel))
        ImageDraw.Draw(image).rectangle(coords, outline='white', width=max(3, width // 320))
        region = CaptureService._hito_box_regions(image)['dialogue']
        left, top, right, bottom = panel
        assert abs(region.top - top) < .015
        assert abs(region.top + region.height - bottom) < .015
        assert abs(region.left - (left + (right-left)*.18)) < .015
        assert abs(region.left + region.width - right) < .015
