export function desktopAddress(value) {
  const text = String(value).trim();
  if (!text || /[\s\\]/.test(text)) throw Error('Enter the desktop address and port, for example 192.168.1.20:3000.');
  let url;
  try { url = new URL(text.includes('://') ? text : 'http://' + text); }
  catch { throw Error('Enter a valid desktop address and port.'); }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) throw Error('Use the desktop address and port shown under Share.');
  if (!url.port && !/:(?:80|443)\/?$/.test(text)) url.port = '3000';
  return url.href;
}
