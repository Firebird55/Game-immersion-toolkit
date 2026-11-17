// Current publisher CameraAnim overrides use separate SubtitleClips and a
// whole-film Wwise event. Follow actual TimelineAsset/track/clip PPtrs. Names
// and positions in the object table never establish ownership or voice order.
import {unityObjects} from './cinematic-links.mjs';

class Reader {
  constructor(bytes, position=0) { this.bytes=bytes; this.position=position; }
  take(size) { const start=this.position; this.position+=size;
    if (!Number.isSafeInteger(size)||size<0||this.position>this.bytes.length) throw Error('Truncated ZZZ cinema timeline');
    return this.bytes.subarray(start,this.position); }
  u32() { return this.take(4).readUInt32LE(); }
  double() { const value=this.take(8).readDoubleLE(); if (!Number.isFinite(value)) throw Error('Invalid ZZZ timeline time'); return value; }
  pointer() { const raw=this.take(12); return {file:raw.readInt32LE(),id:raw.readBigInt64LE(4).toString()}; }
  string() { const size=this.u32(); if (size>4096) throw Error('Invalid ZZZ timeline string');
    const value=new TextDecoder('utf-8',{fatal:true}).decode(this.take(size)); this.take((4-size%4)%4); return value; }
  count() { const value=this.u32(); if(value>10000) throw Error('Invalid ZZZ timeline array'); return value; }
  zero(size) { const start=this.position; if (this.take(size).some(Boolean)) throw Error('Unsupported ZZZ timeline fields at '+start); }
  end() { if(this.position!==this.bytes.length) throw Error('Changed ZZZ timeline schema'); }
}
const local = pointer => pointer.file===0&&pointer.id!=='0';

function typedObjects(bytes) {
  const objects=unityObjects(bytes), result=new Map();
  for(const object of objects.values()) {
    if(object.kind!==114||object.bytes.length<32)continue;
    const r=new Reader(object.bytes,16), pointer=r.pointer(), name=r.string();
    const script=local(pointer)&&objects.get(pointer.id); if(script?.kind!==115)continue;
    const s=new Reader(script.bytes); s.string(); s.take(20);
    const type=s.string(), namespace=s.string(), assembly=s.string(); s.end();
    if ((namespace==='UnityEngine.Timeline'&&assembly==='Unity.Timeline.dll')||
        (namespace==='MoleMole.Timeline'&&assembly==='Logic.dll')) result.set(object.id,{...object,name,type,namespace,body:r.position});
  }
  return result;
}
function clip(r, owner) {
  if(r.u32()!==1)throw Error('Unsupported ZZZ TimelineClip version');
  const start=r.double(), offset=r.double(), asset=r.pointer(), duration=r.double(), speed=r.double(), parent=r.pointer();
  if(start<0||duration<=0||duration>1000000||offset<0||speed<=0||!local(parent)||parent.id!==owner)throw Error('Invalid ZZZ TimelineClip ownership');
  r.take(32); // Ease and blend durations; they do not change subtitle identity.
  for(let i=0;i<2;i++){const count=r.count();r.take(count*28+12);} // Unity Keyframes and infinity/rotation modes.
  r.take(8); for(let i=0,n=r.count();i<n;i++)r.string();
  r.pointer(); r.take(12); r.double(); r.double(); const name=r.string();
  return {asset,start,duration,offset,speed,name};
}
function track(object) {
  const r=new Reader(object.bytes,object.body);
  if(r.u32()!==3)throw Error('Unsupported ZZZ TrackAsset version');
  // Frozen original track schema: no muted/locked/custom data or curves.
  r.zero(36); const parent=r.pointer(), children=Array.from({length:r.count()},()=>r.pointer());
  r.string(); const clips=Array.from({length:r.count()},()=>clip(r,object.id));
  if(r.count()!==0)throw Error('Unsupported ZZZ timeline markers');
  let language=null;
  if(object.type==='SubtitleTrack')language=r.u32();
  else if(object.type==='WwiseAudioTrack')r.zero(12); // No parameters, locale or player exclusions.
  r.end(); return {parent,children,clips,language};
}

export function cinemaSubtitleTimeline(bytes) {
  const objects=typedObjects(Buffer.from(bytes)), subtitles=[], events=[], failures=[];
  const timelines=[...objects.values()].filter(o=>o.type==='TimelineAsset'&&o.namespace==='UnityEngine.Timeline');
  for(const timeline of timelines) {
    const r=new Reader(timeline.bytes,timeline.body);
    if(r.u32()!==0)throw Error('Unsupported ZZZ TimelineAsset version');
    const roots=Array.from({length:r.count()},()=>r.pointer()), visited=new Set(), captions=[], voices=[], posts=[];
    let complete=true;
    const safelyVisit=(pointer,parent)=>{
      const captionStart=captions.length,voiceStart=voices.length,postStart=posts.length;
      try { visit(pointer,parent); }
      catch(error) { captions.length=captionStart;voices.length=voiceStart;posts.length=postStart;complete=false;
        failures.push({timeline:timeline.name,track:pointer.id,reason:error.message}); }
    };
    const visit=(pointer,parent)=>{
      if(!local(pointer)||visited.has(pointer.id))throw Error('External or cyclic ZZZ cinema track');
      const object=objects.get(pointer.id);
      if(!object||!['GroupTrack','SubtitleTrack','WwiseAudioTrack'].includes(object.type))throw Error('Unsupported ZZZ cinema track');
      visited.add(pointer.id); const value=track(object);
      if(!local(value.parent)||value.parent.id!==parent)throw Error('Mismatched ZZZ cinema track parent');
      for(const child of value.children)safelyVisit(child,object.id);
      for(const entry of value.clips) {
        const target=local(entry.asset)&&objects.get(entry.asset.id);
        if(!target)throw Error('External ZZZ cinema clip');
        const body=new Reader(target.bytes,target.body);
        if(object.type==='SubtitleTrack'&&target.type==='SubtitleClip') {
          const text_id=body.string(), language=body.u32(); body.take(4); body.end();
          if(!/^[A-Za-z0-9_][A-Za-z0-9_.-]*$/.test(text_id)||language!==value.language||![1,2,3,4].includes(language))throw Error('Changed ZZZ cinema subtitle schema');
          captions.push({text_id,locale:({1:'en',2:'zh-Hans',3:'ja',4:'ko'})[language],start:entry.start,duration:entry.duration});
        } else if(object.type==='WwiseAudioTrack'&&target.type==='WwiseAudioClip') {
          const event=body.string(); body.zero(64); body.end();
          posts.push({event,start:entry.start,duration:entry.duration,offset:entry.offset,speed:entry.speed});
          if(/^Play_vo_[A-Za-z0-9_]+$/i.test(event)&&entry.offset===0&&entry.speed===1) voices.push(event);
        } else throw Error('Changed ZZZ cinema clip type');
      }
    };
    for(const root of roots)safelyVisit(root,timeline.id);
    const unique=[...new Set(voices)];
    const primary=posts.filter(row=>row.event===unique[0]);
    const alternatives=posts.filter(row=>row.event!==unique[0]);
    const alternate=complete&&unique.length===1&&primary.length===1&&alternatives.length===1&&
      /^Play_[A-Za-z0-9_]+$/i.test(alternatives[0].event)&&!/^Play_vo_/i.test(alternatives[0].event)&&
      alternatives[0].offset===0&&alternatives[0].speed===1&&
      Math.abs(alternatives[0].start-primary[0].start)<1e-6&&Math.abs(alternatives[0].duration-primary[0].duration)<1e-6
      ? alternatives[0].event:null;
    for(const caption of captions)subtitles.push({...caption,timeline:timeline.name,
      event:complete&&unique.length===1?unique[0]:null,audio_scope:'context',
      ...(alternate?{cinematic_alternates:[alternate]}:{})});
    events.push(...unique);
  }
  return {subtitles,events:[...new Set(events)],unsupported:failures};
}

export function cinemaSubtitleLinks(result, namespace) {
  const locale=({'english(en)':'en','chinese(prc)':'zh-Hans','japanese(jp)':'ja','korean(kr)':'ko'})[namespace.toLowerCase()];
  if(!locale)throw Error('Unsupported ZZZ cinema voice namespace');
  return result.subtitles.filter(subtitle=>subtitle.locale===locale).map(subtitle=>({
    ...subtitle,source:'',cinematic_event:subtitle.event,dialogue_kind:'cutscene',
    channels:['cinematic'],voice_status:subtitle.event?'unavailable':'unknown'}));
}
