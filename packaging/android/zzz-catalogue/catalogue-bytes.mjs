// Byte operations used by the confined ZZZ parser. No Node globals or I/O.
const utf8 = new TextDecoder('utf-8', {ignoreBOM: true});
const encoder = new TextEncoder();
export const MAX_FILE_BYTES = 128 * 1024 * 1024;

function encode(value, encoding) {
  if (encoding === 'utf8') return encoder.encode(value);
  if (encoding === 'hex') {
    if (!/^(?:[0-9a-f]{2})*$/i.test(value)) throw Error('Invalid ZZZ format hex');
    const output = new Uint8Array(value.length / 2);
    for (let i = 0; i < output.length; i++) output[i] = Number.parseInt(value.slice(2 * i, 2 * i + 2), 16);
    return output;
  }
  if (encoding !== 'latin1' && encoding !== 'utf16le') throw Error('Unsupported ZZZ text encoding');
  const width = encoding === 'utf16le' ? 2 : 1;
  const output = new Uint8Array(value.length * width);
  for (let i = 0; i < value.length; i++) {
    const char = value.charCodeAt(i);
    output[i * width] = char;
    if (width === 2) output[i * width + 1] = char >>> 8;
  }
  return output;
}

export class CatalogueBytes extends Uint8Array {
  #data = new DataView(this.buffer, this.byteOffset, this.byteLength);

  static isBuffer(value) { return value instanceof CatalogueBytes; }
  static byteLength(value) {
    if (typeof value !== 'string') throw Error('Invalid ZZZ text');
    return encoder.encode(value).length;
  }
  static alloc(size) {
    if (!Number.isSafeInteger(size) || size < 0 || size > MAX_FILE_BYTES) throw Error('ZZZ binary size exceeds limit');
    return new CatalogueBytes(size);
  }
  static allocUnsafe(size) { return CatalogueBytes.alloc(size); }
  static from(value, encoding = 'utf8') {
    let input = value;
    if (typeof value === 'string') input = encode(value, encoding);
    if (!(input instanceof Uint8Array) || input.length > MAX_FILE_BYTES) throw Error('Invalid ZZZ byte input');
    return new CatalogueBytes(input);
  }

  readUInt8(offset = 0) { return this.#data.getUint8(offset); }
  readInt8(offset = 0) { return this.#data.getInt8(offset); }
  readUInt16LE(offset = 0) { return this.#data.getUint16(offset, true); }
  readInt16LE(offset = 0) { return this.#data.getInt16(offset, true); }
  readUInt32LE(offset = 0) { return this.#data.getUint32(offset, true); }
  readUInt32BE(offset = 0) { return this.#data.getUint32(offset, false); }
  readInt32LE(offset = 0) { return this.#data.getInt32(offset, true); }
  readBigUInt64LE(offset = 0) { return this.#data.getBigUint64(offset, true); }
  readBigInt64LE(offset = 0) { return this.#data.getBigInt64(offset, true); }
  readFloatLE(offset = 0) { return this.#data.getFloat32(offset, true); }
  readDoubleLE(offset = 0) { return this.#data.getFloat64(offset, true); }
  writeUInt32LE(value, offset = 0) { this.#data.setUint32(offset, value, true); }
  writeBigUInt64LE(value, offset = 0) { this.#data.setBigUint64(offset, value, true); }

  copy(target, targetStart = 0, sourceStart = 0, end = this.length) {
    const bytes = this.subarray(sourceStart, Math.min(end, sourceStart + target.length - targetStart));
    target.set(bytes, targetStart);
    return bytes.length;
  }

  indexOf(value, start = 0) {
    if (typeof value === 'number') return super.indexOf(value, start);
    if (!(value instanceof Uint8Array) || !value.length || start < 0) throw Error('Invalid ZZZ byte search');
    for (let index = super.indexOf(value[0], start); index >= 0 && index + value.length <= this.length;
         index = super.indexOf(value[0], index + 1)) {
      if (value.every((byte, position) => this[index + position] === byte)) return index;
    }
    return -1;
  }

  toString(encoding = 'utf8', start = 0, end = this.length) {
    const bytes = this.subarray(start, end);
    if (encoding === 'utf8') return utf8.decode(bytes);
    if (!['ascii', 'latin1', 'utf16le'].includes(encoding)) throw Error('Unsupported ZZZ text encoding');
    const width = encoding === 'utf16le' ? 2 : 1;
    const mask = encoding === 'ascii' ? 0x7f : 0xff;
    let result = '';
    const codes = [];
    for (let i = 0; i + width <= bytes.length; i += width) {
      codes.push(width === 2 ? bytes[i] | bytes[i + 1] << 8 : bytes[i] & mask);
      if (codes.length === 4096) {
        result += String.fromCharCode(...codes);
        codes.length = 0;
      }
    }
    return result + String.fromCharCode(...codes);
  }
}
