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
