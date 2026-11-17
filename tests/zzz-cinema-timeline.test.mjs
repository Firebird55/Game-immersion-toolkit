import test from 'node:test';
import assert from 'node:assert/strict';
import {cinemaSubtitleTimeline, cinemaSubtitleLinks} from '../scripts/zzz-cinema-timeline.mjs';

// Entirely owned synthetic Unity v21 objects; no publisher text or asset bytes.
const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32LE(n);return b;};
const double=n=>{const b=Buffer.alloc(8);b.writeDoubleLE(n);return b;};
const pointer=(id,file=0)=>{const b=Buffer.alloc(12);b.writeInt32LE(file);b.writeBigInt64LE(BigInt(id),4);return b;};
const string=s=>{const b=Buffer.from(s);return Buffer.concat([u32(b.length),b,Buffer.alloc((4-b.length%4)%4)]);};
const script=(name,unity=false)=>Buffer.concat([string(name),Buffer.alloc(20),string(name),
  string(unity?'UnityEngine.Timeline':'MoleMole.Timeline'),string(unity?'Unity.Timeline.dll':'Logic.dll')]);
const behaviour=(id,name,body)=>Buffer.concat([Buffer.alloc(16),pointer(id),string(name),body]);
const timelineClip=(asset,owner,{offset=0,speed=1}={})=>Buffer.concat([u32(1),double(1),double(offset),pointer(asset),double(2),double(speed),pointer(owner),
  Buffer.alloc(32),u32(0),Buffer.alloc(12),u32(0),Buffer.alloc(12),Buffer.alloc(8),u32(0),pointer(0),Buffer.alloc(12),double(0),double(0),string('Synthetic')]);
const track=(parent,children,clips,tail=Buffer.alloc(0),{muted=false}={})=>Buffer.concat([u32(3),u32(muted?1:0),Buffer.alloc(32),pointer(parent),
  u32(children.length),...children.map(id=>pointer(id)),string('a'.repeat(32)),u32(clips.length),...clips,u32(0),tail]);

function fixture({language=3,clipLanguage=language,wrongParent=false,external=false,muted=false,secondEvent=false,offset=0,cyclic=false,unknownTrack=false}={}) {
  const records=[
    [1,115,script('TimelineAsset',true)],[2,115,script('GroupTrack',true)],
    [3,115,script('SubtitleTrack')],[4,115,script('SubtitleClip')],
    [5,115,script('WwiseAudioTrack')],[6,115,script('WwiseAudioClip')],
    [10,114,behaviour(1,'Synthetic_Timeline',Buffer.concat([u32(0),u32(1),pointer(20,external?1:0)]))],
    [20,114,behaviour(2,'Synthetic',track(10,[30,40,...(cyclic?[20]:[]),...(unknownTrack?[80]:[])],[]))],
    [30,114,behaviour(3,'NoLocaleInName',track(wrongParent?999:20,[],[timelineClip(50,30)],u32(language),{muted}))],
    [40,114,behaviour(5,'NoVoiceInName',track(20,[],[timelineClip(60,40,{offset}),...(secondEvent?[timelineClip(61,40)]:[])],Buffer.alloc(12)))],
    [50,114,behaviour(4,'SubtitleClip',Buffer.concat([string('SyntheticCaption'),u32(clipLanguage),u32(0)]))],
    [60,114,behaviour(6,'WwiseAudioClip',Buffer.concat([string('Play_vo_Synthetic'),Buffer.alloc(64)]))],
    [61,114,behaviour(6,'WwiseAudioClip',Buffer.concat([string('Play_vo_Other'),Buffer.alloc(64)]))],
  ];
  const types=Buffer.concat([u32(2),u32(114),Buffer.alloc(35),u32(115),Buffer.alloc(19)]);
  let pre=Buffer.concat([Buffer.from('2019.4.40f1\0'),u32(19),Buffer.from([0]),types,u32(records.length)]);
  pre=Buffer.concat([pre,Buffer.alloc((4-(20+pre.length)%4)%4)]);
  let offsetAt=0;const table=[],data=[];
  for(const [id,kind,raw] of records){const row=Buffer.alloc(20);row.writeBigInt64LE(BigInt(id));row.writeUInt32LE(offsetAt,8);row.writeUInt32LE(raw.length,12);row.writeUInt32LE(kind===114?0:1,16);table.push(row);data.push(raw);offsetAt+=raw.length;}
  const metadata=Buffer.concat([pre,...table,Buffer.alloc(12)]),start=(20+metadata.length+15)&~15,header=Buffer.alloc(20);
  header.writeUInt32BE(metadata.length);header.writeUInt32BE(start+offsetAt,4);header.writeUInt32BE(21,8);header.writeUInt32BE(start,12);
  return Buffer.concat([header,metadata,Buffer.alloc(start-20-metadata.length),...data]);
}
test('separate subtitle tracks retain original language and whole-film context ownership',()=>{
  for(const [language,locale] of [[1,'en'],[2,'zh-Hans'],[3,'ja'],[4,'ko']]){
    const result=cinemaSubtitleTimeline(fixture({language}));
    assert.deepEqual(result.unsupported,[]);
    assert.deepEqual(result.subtitles,[{text_id:'SyntheticCaption',locale,start:1,duration:2,
      timeline:'Synthetic_Timeline',event:'Play_vo_Synthetic',audio_scope:'context'}]);
  }
});
test('external, mismatched, muted and changed locale tracks never supply subtitle or voice pairs',()=>{
  for(const options of [{wrongParent:true},{external:true},{muted:true},{clipLanguage:2},{language:99}]){
    const result=cinemaSubtitleTimeline(fixture(options));assert.equal(result.subtitles.length,0);assert.equal(result.unsupported.length,1);
  }
});
test('multiple whole-voice events or a source offset cannot be assigned to a caption by order',()=>{
  for(const options of [{secondEvent:true},{offset:1}])assert.equal(cinemaSubtitleTimeline(fixture(options)).subtitles[0].event,null);
});
test('publisher voice namespaces select their own subtitle language without certifying absent recordings',()=>{
  for(const [language,namespace,locale] of [[1,'English(EN)','en'],[2,'Chinese(PRC)','zh-Hans'],[3,'Japanese(JP)','ja'],[4,'Korean(KR)','ko']]){
    const links=cinemaSubtitleLinks(cinemaSubtitleTimeline(fixture({language})),namespace);
    assert.equal(links.length,1);assert.equal(links[0].locale,locale);
    assert.equal(links[0].voice_status,'unavailable');assert.equal(links[0].cinematic_event,'Play_vo_Synthetic');
    assert.deepEqual(cinemaSubtitleLinks(cinemaSubtitleTimeline(fixture({language})),language===1?'Japanese(JP)':'English(EN)'),[]);
  }
  assert.throws(()=>cinemaSubtitleLinks({subtitles:[]},'Unknown'),/namespace/);
});
test('a valid subtitle remains available when another track is cyclic or unsupported, with unresolved audio',()=>{
  for(const options of [{cyclic:true},{unknownTrack:true}]){
    const result=cinemaSubtitleTimeline(fixture(options));assert.equal(result.subtitles.length,1);
    assert.equal(result.subtitles[0].event,null);assert.equal(result.unsupported.length,1);
    assert.equal(cinemaSubtitleLinks(result,'Japanese(JP)')[0].voice_status,'unknown');
  }
});
