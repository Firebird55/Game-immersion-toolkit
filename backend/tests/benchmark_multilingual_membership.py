"""Paired synthetic benchmark; run as a module, never a CI timing assertion.

python -m backend.tests.benchmark_multilingual_membership --baseline origin/main
Reports retained/peak Python allocations, catalog load, membership, and actual
FastAPI history/favorites requests in the same process with identical inputs.
"""
import argparse
import gc
import json
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time
import tracemalloc
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend import api
from backend.models import TextMatch
from backend.multilingual_index import MultilingualTextIndex
from backend.storage import TranscriptStore


def median_seconds(operation, repeats=5):
    samples = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = operation()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='origin/main')
    parser.add_argument('--records', type=int, default=100000)
    parser.add_argument('--output', default='output/checks/backend-membership-benchmark.json')
    args = parser.parse_args()
    baseline = subprocess.check_output(['git', 'rev-parse', args.baseline], text=True).strip()
    source = subprocess.check_output(['git', 'show', f'{baseline}:backend/multilingual_index.py'], text=True)
    namespace = {'__name__': 'backend.baseline_multilingual_index'}
    exec(compile(source, '<baseline multilingual index>', 'exec'), namespace)
    report = {'baseline': baseline, 'python': platform.python_version(), 'platform': platform.system(),
              'catalog_records': args.records, 'membership_queries': 250, 'history_rows': 250,
              'samples': 5, 'native_capture': 'not started; synthetic data and temporary database only'}
    with tempfile.TemporaryDirectory(prefix='synthetic-membership-') as folder:
        directory = Path(folder)
        records = [dict(text_id=f'fixture:{n}', source_locale='en', source_text=f'Synthetic caption number {n}.',
                        texts={'en': f'Synthetic caption number {n}.'}, audio_locale='en',
                        audio={'file': str(n)} if n % 7 else None, member_text_ids=[f'member:{n}'])
                   for n in range(report['catalog_records'])]
        (directory / 'textmap.json').write_text(json.dumps({'format': 2, 'game': 'cyberpunk',
                                                          'source_locale': 'en', 'records': records}))
        transcript = TranscriptStore(directory / 'history.db')
        for number in range(report['history_rows']):
            identity = f'member:{args.records-1-number}' if number % 2 else f'missing:{number}'
            line = transcript.add(TextMatch(game='cyberpunk', text_id=identity, english='Synthetic',
                chinese='测试文字', source_ocr='Synthetic', score=100, kind='exact'), 'synthetic')
            transcript.update_audio(line.id, None, True)
            transcript.set_favorite(line.id, True)
        results = {}
        for label, cls in [('before', namespace['MultilingualTextIndex']), ('after', MultilingualTextIndex)]:
            gc.collect()
            tracemalloc.start()
            start = time.perf_counter()
            index = cls('cyberpunk', directory)
            elapsed = time.perf_counter() - start
            retained, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert index.ready
            api.runtime = SimpleNamespace(transcript=transcript, game_indexes={'cyberpunk': index})
            client = TestClient(api.app, base_url='http://127.0.0.1:8766')
            query_seconds, membership = median_seconds(lambda: [index.is_capture_text(
                f'member:{args.records-1-n}' if n % 2 else f'missing:{n}', '', 'dialogue') for n in range(250)])
            def get(path):
                response = client.get(path)
                assert response.status_code == 200
                return response.json()
            history_seconds, history = median_seconds(lambda: get('/api/lines?game=cyberpunk'))
            favorites_seconds, favorites = median_seconds(lambda: get('/api/favorites?game=cyberpunk'))
            report[label] = {'load_seconds_with_tracemalloc': elapsed, 'retained_python_bytes': retained,
                             'peak_python_bytes': peak, 'membership_seconds': query_seconds,
                             'history_http_seconds': history_seconds, 'favorites_http_seconds': favorites_seconds}
            results[label] = (membership, history, favorites)
            client.close()
            del index
        assert results['before'] == results['after'], 'History/favorites or membership results changed'
        report['results_identical'] = True
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
