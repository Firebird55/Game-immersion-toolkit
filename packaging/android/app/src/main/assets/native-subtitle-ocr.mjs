import Tesseract from '/ocr/tesseract.esm.min.js';

const engines = new Map();

async function recognize({image, language, width, height}) {
 if (!['rus', 'tha'].includes(language)) throw Error('Unsupported subtitle language');
 let engine = engines.get(language);
 if (!engine) {
  engine = await Tesseract.createWorker(language, 1, {
   workerPath: '/ocr/verified-worker.js', corePath: '/ocr/core/tesseract-core-lstm.wasm.js',
   langPath: '/ocr/lang/', cacheMethod: 'none', workerBlobURL: false,
  });
  await engine.setParameters({tessedit_pageseg_mode:'11'});
  engines.set(language, engine);
 }
 const source = new Image();
 source.src = 'data:image/png;base64,' + image;
 await source.decode();
 const result = await engine.recognize(source, {}, {text:true, blocks:true});
 const blocks = [], presentation_lines = [];
 function bounds(box) {
  const values = [Math.floor(box.x0 * width / source.naturalWidth),
   Math.floor(box.y0 * height / source.naturalHeight),
   Math.ceil(box.x1 * width / source.naturalWidth), Math.ceil(box.y1 * height / source.naturalHeight)];
  const [x0,y0,x1,y1] = values;
  return x0 >= 0 && y0 >= 0 && x1 <= width && y1 <= height && x0 < x1 && y0 < y1 ? values : null;
 }
 for (const block of (result.data.blocks ?? []).slice(0,128)) {
  const rect = bounds(block.bbox);
  if (rect && block.text.length <= 8192) blocks.push({text:block.text, rect});
  for (const line of block.paragraphs.flatMap(paragraph => paragraph.lines)) {
   const box = bounds(line.bbox);
   const text = line.text.trim();
   if (!box || !text || text.length > 2048 || presentation_lines.length >= 512) continue;
   const [x0,y0,x1,y1] = box;
   presentation_lines.push({text, confidence: Math.max(0, Math.min(1, line.confidence/100)),
    bounding_rect:{x1:x0,y1:y0,x2:x1,y2:y0,x3:x1,y3:y1,x4:x0,y4:y1}});
  }
 }
 return {width, height, blocks, presentation_lines};
}

addEventListener('message', function bind(event) {
 if (event.data !== 'toolkit-native-subtitle-ocr' || event.ports.length !== 1) return;
 removeEventListener('message', bind);
 const port = event.ports[0];
 port.onmessage = async message => {
  try {port.postMessage(JSON.stringify(await recognize(JSON.parse(message.data))));}
  catch {port.postMessage('error');}
 };
 port.postMessage('ready');
});
