import test from 'node:test';import assert from 'node:assert/strict';
import {cinematicVoicePairs}from'../scripts/cinematic-links.mjs';

// Owned synthetic Unity objects only: no game file bytes or dialogue.
const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32LE(n);return b;};
const double=n=>{const b=Buffer.alloc(8);b.writeDoubleLE(n);return b;};
const pointer=id=>{const b=Buffer.alloc(12);b.writeBigInt64LE(BigInt(id),4);return b;};
const string=s=>{const b=Buffer.from(s),padding=Buffer.alloc((4-b.length%4)%4);return Buffer.concat([u32(b.length),b,padding]);};
const script=(name,namespace)=>Buffer.concat([string(name),Buffer.alloc(20),string(name),string(namespace),string('Synthetic.dll')]);
const behaviour=(id,name,body)=>Buffer.concat([Buffer.alloc(16),pointer(id),string(name),body]);
function fixture({language='CH',text='CS_Synthetic_01',original=text,clipIn=0,speed=1,wrongParent=false,auxiliary=null}={}){
 const records=[
  [1,115,script('WwiseAudioClip','MoleMole.Timeline')],
  [2,115,script('WwiseAudioTrack','MoleMole.Timeline')],
  [3,115,script('GroupTrack','UnityEngine.Timeline')],
  [10,114,behaviour(1,'WwiseAudioClip',Buffer.concat([string('Play_vo_Synthetic_01'),...(auxiliary===null?[]:[string(auxiliary)]),string(text),string(original)]))],
  [20,114,behaviour(2,'vo',Buffer.concat([u32(3),Buffer.alloc(36),pointer(wrongParent?99:30),u32(0),string('a'.repeat(32)),u32(1),
   u32(1),double(1),double(clipIn),pointer(10),double(2),double(speed),pointer(20)]))],
  [30,114,behaviour(3,language,Buffer.concat([u32(3),Buffer.alloc(36),pointer(0),u32(1),pointer(20)]))],
 ];
 const types=Buffer.concat([u32(2),u32(114),Buffer.alloc(3+16+16),u32(115),Buffer.alloc(3+16)]);
 let pre=Buffer.concat([Buffer.from('2019.4.40f1\0'),u32(19),Buffer.from([0]),types,u32(records.length)]);
 pre=Buffer.concat([pre,Buffer.alloc((4-(20+pre.length)%4)%4)]);
 let offset=0;const table=[],data=[];
 for(const[id,kind,raw]of records){const row=Buffer.alloc(20);row.writeBigInt64LE(BigInt(id));row.writeUInt32LE(offset,8);row.writeUInt32LE(raw.length,12);row.writeUInt32LE(kind===114?0:1,16);table.push(row);data.push(raw);offset+=raw.length;}
 const metadata=Buffer.concat([pre,...table,Buffer.alloc(12)]),dataStart=(20+metadata.length+15)&~15;
 const header=Buffer.alloc(20);header.writeUInt32BE(metadata.length);header.writeUInt32BE(dataStart+offset,4);header.writeUInt32BE(21,8);header.writeUInt32BE(dataStart,12);
 return Buffer.concat([header,metadata,Buffer.alloc(dataStart-20-metadata.length),...data]);
}
test('cinematic subtitles bind to typed Mandarin audio clips through their owning track',()=>{
 assert.deepEqual(cinematicVoicePairs(fixture()),[{text_id:'CS_Synthetic_01',event:'Play_vo_Synthetic_01'}]);
 assert.deepEqual(cinematicVoicePairs(fixture({auxiliary:''})),[{text_id:'CS_Synthetic_01',event:'Play_vo_Synthetic_01'}]);
});
test('other languages, mismatched IDs and edited or unowned clips supply no original mapping',()=>{
 for(const options of [{language:'EN'},{language:'JP'},{original:'CS_Other'},{wrongParent:true},{clipIn:3},{speed:2},{auxiliary:'Unknown'},{auxiliary:'',original:'CS_Other'}])assert.deepEqual(cinematicVoicePairs(fixture(options)),[]);
 assert.throws(()=>cinematicVoicePairs(fixture().subarray(0,-1)),/Unsupported Unity file/);
 assert.throws(()=>cinematicVoicePairs(Buffer.from('Play_vo_Synthetic_01 CS_Synthetic_01')),/Unsupported Unity file/);
});
