"""Portable response and engine fallback tests without native DLLs or downloads."""
import sys
from types import SimpleNamespace

from backend import ocr_engine


def test_portable_empty_and_wrapped_lines_use_production_response_shape():
    engine = object.__new__(ocr_engine.PortableOcrEngine)
    engine.engine = lambda image, **kwargs: (None, None)
    assert engine.recognize_pil(object()) == {'lines': []}
    box = [[1, 2], [30, 2], [30, 12], [1, 12]]
    engine.engine = lambda image, **kwargs: ([(box, 'caption', .99)], None)
    line = engine.recognize_pil(object())['lines'][0]
    assert line == {'text': 'caption', 'confidence': .99, 'bounding_rect': {
        'x1': 1., 'y1': 2., 'x2': 30., 'y2': 2., 'x3': 30., 'y3': 12., 'x4': 1., 'y4': 12.}}


def test_windows_without_proprietary_model_uses_bundled_offline_engine(monkeypatch):
    def unavailable():
        raise OSError('Optional native files absent')
    fallback = object()
    monkeypatch.setattr(ocr_engine.sys, 'platform', 'win32')
    monkeypatch.setitem(sys.modules, 'oneocr', SimpleNamespace(OcrEngine=unavailable))
    monkeypatch.setattr(ocr_engine, 'PortableOcrEngine', lambda: fallback)
    assert ocr_engine.OcrEngine() is fallback


def test_other_platforms_never_import_windows_ocr(monkeypatch):
    def forbidden():
        raise AssertionError('Windows engine must not run')
    fallback = object()
    monkeypatch.setitem(sys.modules, 'oneocr', SimpleNamespace(OcrEngine=forbidden))
    monkeypatch.setattr(ocr_engine, 'PortableOcrEngine', lambda: fallback)
    for platform in ('linux', 'darwin'):
        monkeypatch.setattr(ocr_engine.sys, 'platform', platform)
        assert ocr_engine.OcrEngine() is fallback
