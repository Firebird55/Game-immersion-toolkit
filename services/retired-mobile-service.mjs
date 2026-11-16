// The hosted mobile gaming services are retired. This handler deliberately
// reads no body, authorization material or binding and makes no upstream call.
export function retiredResponse(request) {
  return new Response(request.method === 'HEAD' ? null : JSON.stringify({
    error: 'service_retired',
    message: 'The hosted mobile service has been retired. Use the desktop reader. The Android app is in development.',
  }), {status: 410, headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, private',
    'Pragma': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
  }});
}

export default {fetch: retiredResponse};
