// Narrow read-only adapter for stripped Unity 21 objects used by ZZZ audio
// timelines. Unknown versions, type trees, external scripts and mixed-language
// tracks supply no mappings. No subtitle/audio ordinal matching is performed.
class Reader {
  constructor(bytes, position=0){this.bytes=bytes;this.position=position;}
  take(size){const start=this.position;this.position+=size;if(size<0||this.position>this.bytes.length)throw Error('Truncated Unity object');return this.bytes.subarray(start,this.position);}
  u32(){return this.take(4).readUInt32LE();}
  i32(){return this.take(4).readInt32LE();}
  align(){this.position=(this.position+3)&~3;}
  string(){const size=this.u32();if(size>1048576)throw Error('Invalid Unity string');const value=this.take(size).toString('utf8');this.align();return value;}
  pointer(){return{file:this.i32(),id:this.take(8).readBigInt64LE().toString()};}
}

export function unityObjects(bytes){
  if(bytes.length<24||bytes.readUInt32BE(8)!==21||bytes[16]!==0||bytes.readUInt32BE(4)!==bytes.length)throw Error('Unsupported Unity file');
  const dataStart=bytes.readUInt32BE(12),metadataEnd=20+bytes.readUInt32BE(0);
  if(dataStart>bytes.length||metadataEnd>dataStart)throw Error('Invalid Unity metadata bounds');
  const zero=bytes.indexOf(0,20);if(zero<20||zero>80)throw Error('Invalid Unity version');
  const reader=new Reader(bytes,zero+1);reader.take(4);
  if(reader.take(1)[0])throw Error('Unity type trees are not supported');
  const count=reader.u32();if(count>10000)throw Error('Invalid Unity types');const types=[];
  for(let i=0;i<count;i++){const kind=reader.i32();types.push(kind);reader.take(3+(kind===114?16:0)+16);}
  const objects=reader.u32();if(objects>200000)throw Error('Invalid Unity object count');
  const result=new Map();
  for(let i=0;i<objects;i++){
    reader.align();const id=reader.take(8).readBigInt64LE().toString(),start=dataStart+reader.u32(),size=reader.u32(),type=reader.i32();
    if(type<0||type>=types.length||start<dataStart||start+size>bytes.length||result.has(id))throw Error('Invalid Unity object range');
    result.set(id,{id,kind:types[type],bytes:bytes.subarray(start,start+size)});
  }
  if(reader.position>metadataEnd)throw Error('Object table exceeds Unity metadata');
  return result;
}

function behaviours(objects){
  const result=new Map();
  for(const object of objects.values()){
    if(object.kind!==114||object.bytes.length<32)continue;
    const reader=new Reader(object.bytes,16),script=reader.pointer(),name=reader.string();
    if(script.file!==0)continue;const source=objects.get(script.id);if(source?.kind!==115)continue;
    const typeReader=new Reader(source.bytes);typeReader.string();typeReader.take(20);
    const type=typeReader.string(),namespace=typeReader.string();
    result.set(object.id,{...object,name,type,namespace,body:reader.position});
  }
  return result;
}

function track(object){
  const reader=new Reader(object.bytes,object.body);
  if(reader.u32()!==3)throw Error('Unsupported Timeline track version');
  reader.take(36);const parent=reader.pointer(),count=reader.u32();
  if(count>10000)throw Error('Invalid Timeline children');
  const children=Array.from({length:count},()=>reader.pointer());
  return{parent,children};
}

export function cinematicVoicePairs(bytes){
  const objects=behaviours(unityObjects(bytes)),mandarin=new Set(),tracks=new Map(),pairs=[];
  for(const object of objects.values()){
    if(object.type==='GroupTrack'&&object.namespace==='UnityEngine.Timeline'&&object.name==='CH'){
      for(const child of track(object).children){
        const candidate=objects.get(child.id);
        if(child.file===0&&candidate?.type==='WwiseAudioTrack'&&candidate.name==='vo'){
          const parent=track(candidate).parent;
          if(parent.file===0&&parent.id===object.id){mandarin.add(candidate.id);tracks.set(candidate.id,candidate);}
        }
      }
    }
  }
  for(const object of objects.values()){
    if(object.type!=='WwiseAudioClip'||object.namespace!=='MoleMole.Timeline')continue;
    const reader=new Reader(object.bytes,object.body),event=reader.string(),textId=reader.string(),originalId=reader.string();
    if(!/^Play_vo_[A-Za-z0-9_]+$/i.test(event)||!/^CS_[A-Za-z0-9_]+$/.test(textId)||originalId!==textId)continue;
    for(const id of mandarin){
      const target=tracks.get(id).bytes;
      // A typed TimelineClip references both its exact audio asset and owning
      // track. Accept only ordinary one-shot clips with no source offset or
      // speed change; unknown edits cannot silently attach the wrong excerpt.
      for(let p=20;p+40<=target.length;p+=4){
        if(target.readInt32LE(p)!==0||target.readBigInt64LE(p+4).toString()!==object.id)continue;
        const start=target.readDoubleLE(p-16),clipIn=target.readDoubleLE(p-8),duration=target.readDoubleLE(p+12),speed=target.readDoubleLE(p+20);
        if(target.readUInt32LE(p-20)!==1||!Number.isFinite(start)||start<0||!Number.isFinite(duration)||duration<=0||duration>600||clipIn!==0||speed!==1||target.readInt32LE(p+28)!==0||target.readBigInt64LE(p+32).toString()!==id)continue;
        pairs.push({text_id:textId,event});break;
      }
    }
  }
  return pairs;
}
