// Real, offline OCR for public game-image regressions. No game files or accounts.
import {createInterface} from 'node:readline';
import {resolve} from 'node:path';
import {createWorker, PSM} from 'tesseract.js';

const worker = await createWorker('eng', 1, {
  langPath: resolve('node_modules/@tesseract.js-data/eng/4.0.0_best_int'),
  gzip: true, cacheMethod: 'none',
});
await worker.setParameters({tessedit_pageseg_mode: PSM.SPARSE_TEXT});
try {
  for await (const line of createInterface({input: process.stdin, crlfDelay: Infinity})) {
    const input = JSON.parse(line);
    const {data} = await worker.recognize(Buffer.from(input.png, 'base64'), {}, {blocks: true, text: true});
    const lines = (data.blocks ?? []).flatMap(block => block.paragraphs.flatMap(paragraph => paragraph.lines)).map(line => {
      const {x0, y0, x1, y1} = line.bbox;
      return {text: line.text.trim(), confidence: line.confidence / 100,
        bounding_rect: {x1: x0, x2: x1, x3: x1, x4: x0, y1: y0, y2: y0, y3: y1, y4: y1}};
    });
    process.stdout.write(JSON.stringify({lines}) + '\n');
  }
} finally { await worker.terminate(); }
