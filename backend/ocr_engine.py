"""One OCR response format for native Windows and offline portable readers."""
from __future__ import annotations

import logging
from importlib.util import find_spec
from pathlib import Path
import sys

log = logging.getLogger(__name__)

MODEL_SHA256 = {
    'ch_PP-OCRv4_det_infer.onnx': 'd2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9',
    'ch_PP-OCRv4_rec_infer.onnx': '48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b',
    'ch_ppocr_mobile_v2.0_cls_infer.onnx': 'e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c',
}


def portable_models_available():
    spec = find_spec('rapidocr_onnxruntime')
    return bool(spec and spec.origin and all((Path(spec.origin).parent / 'models' / name).is_file()
                                            for name in MODEL_SHA256))


class PortableOcrEngine:
    """Models ship in the pinned wheel; recognition never downloads files."""
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)

    def recognize_pil(self, image):
        result, _ = self.engine(image, use_cls=False)
        return {'lines': [{'text': text, 'confidence': float(score), 'bounding_rect': {
            **{f'x{i+1}': float(point[0]) for i, point in enumerate(box)},
            **{f'y{i+1}': float(point[1]) for i, point in enumerate(box)}}}
            for box, text, score in (result or [])]}


def OcrEngine():
    if sys.platform == 'win32':
        try:
            from oneocr import OcrEngine as NativeEngine
            engine = NativeEngine()
            log.info('Subtitle OCR ready: Windows native engine')
            return engine
        except (ImportError, OSError, RuntimeError) as error:
            log.info('Windows OCR unavailable (%s); starting bundled offline OCR', type(error).__name__)
    engine = PortableOcrEngine()
    log.info('Subtitle OCR ready: bundled offline engine')
    return engine
