// Build-time adaptation of the exact maintained desktop MHY implementation.
import {createHash} from 'node:crypto';

export const COMPILED_READER_SHA256 = '2cf2524bdeb8630fa01d3a183caf15d3040b5c538331719406df9e6edf74fce6';

export function portableMhySource(bytes) {
  if (createHash('sha256').update(bytes).digest('hex') !== COMPILED_READER_SHA256)
    throw Error('The retained ZZZ MHY implementation differs from its source pin');
  const source = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
  const begin = source.indexOf('const MHY_SHIFT_ROW =');
  const end = source.indexOf('const utf16AsciiStrings =');
  if (begin < 0 || end <= begin) throw Error('Incomplete retained ZZZ MHY source');
  let body = source.slice(begin, end);
  const legacyExports = body.indexOf('export { xxHash64 };');
  const formatArithmetic = body.indexOf('const gfMultiply =');
  if (legacyExports < 0 || formatArithmetic <= legacyExports) throw Error('Unexpected retained ZZZ format boundary');
  // Ignore the standalone CLI's older scene-plan helpers. The shared catalogue
  // supplies the maintained planning and lookup operations independently.
  body = body.slice(0, legacyExports) + body.slice(formatArithmetic);
  function replace(before, after) {
    if (body.indexOf(before) === -1 || body.indexOf(before) !== body.lastIndexOf(before))
      throw Error('Unexpected retained ZZZ MHY adaptation site');
    body = body.replace(before, after);
  }
  // The original format uses one AES-128-ECB encryption block. Keep the
  // surrounding format transform, but await the caller's platform primitive.
  replace('const descramble = (data, entrySize) => {', 'const descramble = async (data, entrySize) => {');
  replace("const cipher = createCipheriv('aes-128-ecb', seed, null);\n    cipher.setAutoPadding(false);\n    const encrypted = cipher.update(data.subarray(20, 36));",
    'const encrypted = await aes128EncryptBlock(seed, data.subarray(20, 36));');
  replace('const unpackMhyFile = (file, start) => {', 'const unpackMhyFile = async (file, start, check) => {\n' +
    '    check();\n    if (!Number.isSafeInteger(start) || start < 0 || start + 8 > file.length) throw Error("Invalid ZZZ MHY range");');
  replace('const encryptedInfo = Uint8Array.from(file.subarray(start + 8, start + 8 + infoSize));',
    'if (infoSize < 55 || start + 8 + infoSize > file.length) throw Error("Invalid ZZZ MHY metadata size");\n' +
    '    const encryptedInfo = Uint8Array.from(file.subarray(start + 8, start + 8 + infoSize));');
  replace('    descramble(encryptedInfo, 28);', '    await descramble(encryptedInfo, 28);\n    check();');
  replace('if (this.offset + length > this.data.length)', 'if (!Number.isSafeInteger(length) || length < 0 || this.offset + length > this.data.length)');
  replace('const nodeCount = rawInfo.int();', 'const nodeCount = rawInfo.int();\n' +
    '    if (nodeCount < 0 || nodeCount > Math.floor((rawInfo.data.length - rawInfo.offset) / 275))\n' +
    '        throw Error("Invalid ZZZ MHY node count");');
  replace('const blockCount = rawInfo.int();', 'const blockCount = rawInfo.int();\n' +
    '    if (blockCount < 0 || blockCount > Math.floor((rawInfo.data.length - rawInfo.offset) / 13))\n' +
    '        throw Error("Invalid ZZZ MHY block count");');
  replace('const contents = Buffer.allocUnsafe(rawSize);',
    'if (rawSize > 128 * 1024 * 1024 || blocks.some(block => block.raw <= 0 || block.compressed < 30))\n' +
    '        throw Error("Invalid ZZZ MHY block sizes");\n' +
    '    if (nodes.some(node => node.offset < 0 || node.offset + node.size > rawSize))\n' +
    '        throw Error("Invalid ZZZ MHY node range");\n' +
    '    const contents = Buffer.allocUnsafe(rawSize);');
  replace('const encrypted = Uint8Array.from(file.subarray(sourceOffset, sourceOffset + block.compressed));\n        descramble(encrypted, 8);',
    'check();\n        if (sourceOffset + block.compressed > file.length) throw Error("Incomplete ZZZ MHY block");\n' +
    '        const encrypted = Uint8Array.from(file.subarray(sourceOffset, sourceOffset + block.compressed));\n' +
    '        await descramble(encrypted, 8);\n        check();');
  return '// Adapted from the pinned MIT-licensed ZZZ format reader. See retained source notice.\n' +
    'export function createMhyReader({decompressOodle, aes128EncryptBlock}) {\n' + body +
    '\nreturn unpackMhyFile;\n}\n';
}
