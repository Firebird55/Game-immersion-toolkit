import qrcode from './pairing/qrcode.mjs';
import jsQR from './pairing/jsqr.mjs';

function pixelsFor(qr, scale) {
 const count=qr.getModuleCount(),width=(count+8)*scale,pixels=new Uint8ClampedArray(width*width*4).fill(255);
 for(let y=0;y<count;y++)for(let x=0;x<count;x++)if(qr.isDark(y,x))for(let dy=0;dy<scale;dy++)for(let dx=0;dx<scale;dx++){
  const at=(((y+4)*scale+dy)*width+(x+4)*scale+dx)*4;pixels[at]=pixels[at+1]=pixels[at+2]=0;
 }
 return {pixels,width};
}
// Check actual pixels before displaying a code and choose another error-
// correction matrix when jsQR cannot recognize a valid matrix. Connection
// data and the number of transfer frames stay intact.
export function readableQr(text, preferred='L') {
 for(const level of new Set([preferred,'M','Q','H','L'])){
  let qr;try{qr=qrcode(0,level);qr.addData(text,'Alphanumeric');qr.make();}catch{continue;}
  const scale=Math.max(2,Math.floor(960/(qr.getModuleCount()+8))),image=pixelsFor(qr,scale);
  if(jsQR(image.pixels,image.width,image.width,{inversionAttempts:'dontInvert'})?.data!==text)continue;
  const camera=pixelsFor(qr,Math.max(2,Math.floor(512/(qr.getModuleCount()+8))));
  if(jsQR(camera.pixels,camera.width,camera.width,{inversionAttempts:'dontInvert'})?.data!==text)continue;
  return {...image,level};
 }
 throw Error('Cannot make a readable QR for this message. Transfer the pairing file or copy the message instead.');
}
