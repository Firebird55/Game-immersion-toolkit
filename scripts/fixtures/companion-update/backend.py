import argparse
import json
import os
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int)
parser.add_argument('--standby', action='store_true')
args = parser.parse_args()
running, session, noted = False, '', False
started = time.monotonic()
events = Path(os.environ['PROXY_TRANSCRIPT_PROJECT_ROOT']) / 'data/events.log'


def note(name):
    with events.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'name': name, 'at': time.time()}) + '\n')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        global noted
        if self.path.startswith('/api/runtime/ready'):
            warm = time.monotonic() - started > 1 and not (Path(__file__).parent / 'fail.flag').exists()
            if warm and not noted:
                note('ready')
                noted = True
            self.reply({'ready': warm, 'standby': True})
        elif self.path == '/api/health':
            self.reply({'status': 'ok'})
        else:
            self.reply({'capture': {'running': running, 'active_game': 'zzz'},
                        'session': {'id': session}, 'worker': 'new'})

    def do_POST(self):
        global running, session
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
        if self.path == '/api/runtime/activate':
            running, session = body.get('running', False), body.get('session_id', '')
            note('activated')
        self.reply({'active': True})


ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
