// Tesseract.js 7 loads {code, data} models correctly, but its initialize action
// joins their data instead of their codes. Normalize only that message so the
// pinned upstream worker can initialize the already verified, loaded models.
self.addEventListener('message', event => {
  const message = event.data;
  if (message?.action === 'initialize' && Array.isArray(message.payload?.langs)) {
    message.payload.langs = message.payload.langs.map(lang => typeof lang === 'string' ? lang : lang.code).join('+');
  }
});
importScripts('./worker.min.js');
