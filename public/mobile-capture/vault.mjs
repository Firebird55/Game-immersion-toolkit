// Encrypted vault by default; explicit trusted-device mode stores a plaintext key.
const encoder = new TextEncoder();
const aad = encoder.encode('proxy-transcript/lexirise-vault/v1');
export const BACKGROUND_LOCK_MS = 300000;
async function derive(passphrase, salt, usage) {
  const material = await crypto.subtle.importKey('raw', encoder.encode(passphrase), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',hash:'SHA-256',iterations:600000,salt}, material, {name:'AES-GCM',length:256}, false, [usage]);
}
export async function encryptKey(key, passphrase, confirmation) {
  if (typeof passphrase !== 'string' || [...passphrase].length < 4 || passphrase !== confirmation) throw Error('Confirm a passphrase of at least 4 characters.');
  if (typeof key !== 'string' || !key.trim() || key.length > 4096 || /[\r\n]/.test(key)) throw Error('Enter a valid API key.');
  const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
  const derived = await derive(passphrase, salt, 'encrypt');
  const ciphertext = await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad,tagLength:128}, derived, encoder.encode(key.trim()));
  return {version:1,kdf:'PBKDF2',hash:'SHA-256',iterations:600000,algorithm:'AES-256-GCM',salt,iv,ciphertext};
}
export async function decryptKey(record, passphrase) {
  try {
    if (record?.version !== 1 || record.kdf !== 'PBKDF2' || record.hash !== 'SHA-256' || record.iterations !== 600000 || record.algorithm !== 'AES-256-GCM' || record.salt?.byteLength !== 16 || record.iv?.byteLength !== 12 || record.ciphertext?.byteLength < 17 || record.ciphertext.byteLength > 8192) throw Error();
    const derived = await derive(passphrase, record.salt, 'decrypt');
    return new TextDecoder('utf-8',{fatal:true}).decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:record.iv,additionalData:aad,tagLength:128},derived,record.ciphertext));
  } catch { throw Error('Cannot unlock: check the passphrase. If the stored key is damaged or the passphrase is forgotten, reconnect using your API key. Your stored data has not been deleted.'); }
}
export function createVault(storage, {onLock=()=>{},now=Date.now}={}) {
  let key='', revision=0, hiddenAt=null, timer, remembered=false, writes=Promise.resolve(), controller=new AbortController();
  const write=fn=>{const pending=writes.catch(()=>{}).then(fn);writes=pending;return pending;};
  const lock=()=>{revision++;key='';clearTimeout(timer);controller.abort();controller=new AbortController();onLock();};
  return {
    get unlocked(){return Boolean(key);}, get signal(){return controller.signal;}, get remembered(){return remembered;},
    credential(){if(!remembered&&hiddenAt!==null&&now()-hiddenAt>=BACKGROUND_LOCK_MS)lock();if(!key)throw Error('Unlock Lexirise in Settings.');return key;},
    async restoreRemembered(){const token=revision;await writes;const saved=await storage.get('lexirise-remembered');if(token!==revision)return false;if(saved?.version!==1||typeof saved.key!=='string'||!saved.key.trim()||saved.key.length>4096||/[\r\n]/.test(saved.key))return false;key=saved.key;remembered=true;clearTimeout(timer);return true;},
    async remember(enabled){const value=enabled?this.credential():null,token=revision;await write(async()=>{if(token!==revision)throw Error('Credential changed. Retry remembering this device.');if(enabled)await storage.put('lexirise-remembered',{version:1,key:value});else await storage.remove('lexirise-remembered');});if(token===revision){remembered=enabled;if(enabled)clearTimeout(timer);}},
    async connectRemembered(value){if(typeof value!=='string'||!value.trim()||value.length>4096||/[\r\n]/.test(value))throw Error('Enter a valid API key.');lock();const token=revision;await write(async()=>{await storage.remove('lexirise-vault');await storage.put('lexirise-remembered',{version:1,key:value.trim()});});if(token!==revision)throw Error('Connection cancelled.');key=value.trim();remembered=true;clearTimeout(timer);},
    exists:async()=>Boolean(await storage.get('lexirise-vault')),
    async connect(value,passphrase,confirmation){lock();const token=revision;const record=await encryptKey(value,passphrase,confirmation);if(token!==revision)throw Error('Connection cancelled.');await write(async()=>{await storage.remove('lexirise-remembered');await storage.put('lexirise-vault',record);});if(token!==revision)throw Error('Connection cancelled. The stored key remains locked.');remembered=false;key=value.trim();},
    async unlock(passphrase){lock();const token=revision;const value=await decryptKey(await storage.get('lexirise-vault'),passphrase);if(token!==revision)throw Error('Unlock cancelled.');key=value;},
    async linkViewer(code){
      if(remembered)return;
      if(typeof code!=='string'||!/^[a-zA-Z0-9_-]{4,128}$/.test(code))return;
      const value=this.credential(),token=revision,record=await storage.get('lexirise-vault');
      const viewer=await encryptKey(value,code,code);
      if(token!==revision)throw Error('Vault locked. Unlock and reconnect to link this code.');
      await write(async()=>{if(token!==revision)throw Error('Vault locked. Unlock and reconnect to link this code.');await storage.put('lexirise-vault',{...record,viewer});});
    },
    async unlockViewer(code){
      lock();const token=revision,record=await storage.get('lexirise-vault');let value;
      try{value=await decryptKey(record?.viewer??record,code);}
      catch{if(!record?.viewer)throw Error('Unlock Lexirise once in Settings to link this stream code.');value=await decryptKey(record,code);}
      if(token!==revision)throw Error('Unlock cancelled.');key=value;
    },
    async changePassphrase(passphrase,confirmation){const value=this.credential(),token=revision;const record=await encryptKey(value,passphrase,confirmation);if(token!==revision)throw Error('Vault locked. Unlock and retry.');await write(async()=>{await storage.remove('lexirise-remembered');await storage.put('lexirise-vault',record);});remembered=false;},
    async forget(){lock();remembered=false;await write(async()=>{await storage.remove('lexirise-remembered');await storage.remove('lexirise-vault');});}, lock,
    visibility(hidden){clearTimeout(timer);if(hidden){hiddenAt??=now();if(!remembered)timer=setTimeout(lock,Math.max(0,BACKGROUND_LOCK_MS-(now()-hiddenAt)));}else{if(!remembered&&hiddenAt!==null&&now()-hiddenAt>=BACKGROUND_LOCK_MS)lock();hiddenAt=null;}}
  };
}
