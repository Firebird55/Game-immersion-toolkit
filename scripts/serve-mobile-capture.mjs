import https from 'node:https';
import { readFileSync } from 'node:fs';
import { networkInterfaces } from 'node:os';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const option = name => args[args.indexOf(name) + 1];
if (!args.includes('--cert') || !args.includes('--key')) {
  console.error('Usage: node scripts/serve-mobile-capture.mjs --cert <trusted-certificate.pem> --key <private-key.pem> [--port 8443]');
  process.exit(1);
}
const port = Number(args.includes('--port') ? option('--port') : 8443);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid port');
const root = new URL('../public/mobile-capture/', import.meta.url);
const routes = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/capture.js', ['capture.js', 'text/javascript; charset=utf-8']],
  ['/core.mjs', ['core.mjs', 'text/javascript; charset=utf-8']],
  ['/style.css', ['style.css', 'text/css; charset=utf-8']],
]);
const server = https.createServer({ cert: readFileSync(option('--cert')), key: readFileSync(option('--key')) }, (request, response) => {
  const route = routes.get(new URL(request.url, 'https://localhost').pathname);
  if (!route || !['GET', 'HEAD'].includes(request.method)) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, {
    'Content-Type': route[1], 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'",
  });
  response.end(request.method === 'HEAD' ? undefined : readFileSync(fileURLToPath(new URL(route[0], root))));
});
server.listen(port, '0.0.0.0', () => {
  console.log(`Mobile capture test: https://localhost:${port}/`);
  for (const entries of Object.values(networkInterfaces())) for (const entry of entries ?? []) {
    if (entry.family === 'IPv4' && !entry.internal) console.log(`Device address: https://${entry.address}:${port}/`);
  }
  console.log('Serves only the capture test assets. No transcript data, credentials, signaling, or gameplay uploads.');
});
