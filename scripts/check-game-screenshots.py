"""Replay user game images through real OCR and production crop/grouping logic.

Catalogs below are authored test doubles of the observed captions, not extracted
game catalogs. They test resolver behavior, never certify original voice files.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from rapidfuzz.fuzz import partial_ratio
from backend.capture import CaptureService
from backend.games import GAME_PROFILES
from backend.languages import normalize_text
from backend.models import AppSettings, CaptureRegion
from backend.multilingual_index import MultilingualTextIndex
from backend.windows import WindowInfo

FIXTURES = ROOT / 'tests/fixtures/game-screenshots'


def regions(case):
    settings = AppSettings()
    if case['presentation'] == 'menu':
        return [CaptureRegion(left=0, top=0, width=1, height=.55), settings.region]
    if case['game'] == 'zzz':
        return [settings.tip_region if case['presentation'] == 'tip' else settings.cinematic_region]
    return [GAME_PROFILES[case['game']].subtitle_region]


class Engine:
    def __init__(self, native, rapid=False):
        self.native = native
        self.rapid = rapid
        if rapid:
            from backend.ocr_engine import PortableOcrEngine
            self.engine = PortableOcrEngine()
        elif native:
            from oneocr import OcrEngine
            self.engine = OcrEngine()
        else:
            self.process = subprocess.Popen(['node', 'scripts/screenshot-ocr-worker.mjs'], cwd=ROOT,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8')

    def read(self, image):
        if self.rapid:
            return self.engine.recognize_pil(image)
        if self.native:
            return self.engine.recognize_pil(image)
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        self.process.stdin.write(json.dumps({'png': base64.b64encode(buffer.getvalue()).decode('ascii')}) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Real OCR worker exited without a result')
        return json.loads(line)

    def close(self):
        if not self.native and not self.rapid:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


def resolver_checks(case, captions, rows):
    if case['partial'] or not case['expected_captions']:
        return 'partial_observation_only' if case['partial'] else 'excluded_menu'
    with tempfile.TemporaryDirectory(prefix='caption-fixture-') as directory:
        path = Path(directory)
        records = [dict(text_id=f'fixture:{case["id"]}:{i}', source_locale='en', source_text=text,
            english=text, chinese='', texts={'en': text}, audio_locale='en',
            audio={'fixture': f'authored-voice-{i}'}, voice_status='voiced', channels=['dialogue', 'cinematic', 'tip'])
            for i, text in enumerate(case['expected_captions'])]
        (path / 'textmap.json').write_text(json.dumps(dict(format=2, game=case['game'], source_locale='en', records=records)), encoding='utf-8')
        index = MultilingualTextIndex(case['game'], path)
        assert index.ready, index.message
        observed = index.match_lines(rows, threshold=88, multiple=True)
        expected_ids = {row['text_id'] for row in records}
        actual_ids = {hit.text_id for hit in observed}
        actual_ids.update(hit.text_id for hit in index.match_line_groups(captions, threshold=88))
        assert actual_ids == expected_ids, 'OCR output did not resolve every authored fixture caption'
        # Captions may include a custom player label or an NPC title; neither
        # must become a required official identity or be prepended to the text.
        for number, text in enumerate(case['expected_captions']):
            observed = [case['speaker'], text] if case['speaker'] else [text]
            match = index.match_lines(observed, exact_only=True)
            assert match and match.text_id == records[number]['text_id']
        for row in records:
            row.update(audio=None, voice_status='unvoiced')
        (path / 'textmap.json').write_text(json.dumps(dict(format=2, game=case['game'], source_locale='en', records=records)), encoding='utf-8')
        silent = MultilingualTextIndex(case['game'], path)
        assert not silent.match_unvoiced_lines(case['expected_captions'])
        silent.capture_unvoiced = True
        assert len(silent.match_unvoiced_lines(case['expected_captions'])) == len(records)
    return 'authored_catalog_voiced_and_explicitly_unvoiced'


def main():
    parser = argparse.ArgumentParser()
    engines = parser.add_mutually_exclusive_group()
    engines.add_argument('--native', action='store_true', help='Use locally installed Windows OCR instead of bundled offline OCR')
    engines.add_argument('--tesseract', action='store_true', help='Compare the browser OCR engine')
    parser.add_argument('--case', help='Run one manifest case')
    args = parser.parse_args()
    manifest = json.loads((FIXTURES / 'manifest.json').read_text(encoding='utf-8'))
    cases = [case for case in manifest['cases'] if not args.case or case['id'] == args.case]
    assert cases, 'No selected screenshots'
    rapid = not args.native and not args.tesseract
    engine, results = Engine(args.native, rapid), []
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip())
    try:
        for case in cases:
            result = {'id': case['id'], 'fixture_sha256': case['sha256'], 'engine': 'rapidocr-onnxruntime-1.4.4' if rapid else 'oneocr' if args.native else 'tesseract.js-7.0.0-eng-1.0.0', 'voice_status': 'unknown'}
            try:
                file = FIXTURES / case['file']
                assert hashlib.sha256(file.read_bytes()).hexdigest() == case['sha256'], 'Fixture changed'
                frame = Image.open(file).convert('RGB')
                assert list(frame.size) == case['dimensions']
                window = WindowInfo(0, 'Game screenshot fixture', 'fixture.exe', (0, 0, *frame.size))
                rows, groups = [], []
                for region in regions(case):
                    x, y, width, height = CaptureService._region_bounds(window, region)
                    crop = CaptureService._ocr_image(frame.crop((x, y, x + width, y + height)), window)
                    response = engine.read(crop)
                    if case['game'] != 'zzz':
                        response = CaptureService._local_subtitle_rows(response, crop.size, region, case['game'])
                    rows.extend(row['text'] for row in response.get('lines', []))
                    groups.extend(CaptureService._spatial_text_groups(response))
                result['observed_rows'], result['observed_groups'] = rows, groups
                if case['presentation'] == 'menu':
                    assert CaptureService._classify_screen_header(rows) == 'menu', 'Account menu not excluded'
                else:
                    observed = normalize_text(' '.join(rows), 'en')
                    assert observed, 'No caption was recognized'
                    scores = [partial_ratio(normalize_text(text, 'en'), observed) for text in case['expected_captions']]
                    result['caption_scores'] = scores
                    assert min(scores) >= 94, f'Incomplete caption: {scores}'
                    for forbidden in case['forbidden_captions']:
                        # A response can quote a phrase in the real subtitle.
                        # Reject it as its own OCR row, not that shared phrase.
                        assert normalize_text(forbidden, 'en') not in [normalize_text(row, 'en') for row in rows], 'Response choice entered caption lane'
                result['resolver_check'] = resolver_checks(case, groups, rows)
                result['passed'] = True
            except Exception as error:
                result['passed'], result['error'] = False, str(error)
            results.append(result)
            print(case['id'], 'PASS' if result['passed'] else 'FAIL: ' + result['error'], flush=True)
    finally:
        engine.close()
    output = ROOT / 'output/checks/game-screenshots'
    output.mkdir(parents=True, exist_ok=True)
    evidence = dict(schema=1, source_commit=source_commit, working_tree_modified=dirty,
        platform=sys.platform, cases=results)
    (output / ('rapid.json' if rapid else 'native.json' if args.native else 'tesseract.json')).write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return 0 if all(row['passed'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
