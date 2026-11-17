import test from 'node:test';
import assert from 'node:assert/strict';
import {validateGameDataRow, validateGameDataList, formatGameBytes, canDownloadGame} from '../lib/game-data-client.mjs';
const row = () => ({id:'zzz',title:'Zenless Zone Zero',state:'not_downloaded',revision:null,installed_revision:null,can_activate:false,region:'global',content_mode:'text',source_locale:'ja',target_locales:['en'],
 installed_bytes:0,deletable_bytes:0,retained_bytes:0,download_bytes:null,download_is_upper_bound:false,required_disk_bytes:null,
 plan_id:null,job:null,can_plan:true,can_download:false,can_delete:false,message:'Check size first.'});
test('unknown sizes remain unknown and cannot start an asset transfer', () => {
 const value = validateGameDataRow(row()); assert.equal(formatGameBytes(value.download_bytes),'Unknown'); assert.equal(formatGameBytes(0),'0 B');
 value.can_download=true;value.plan_id='plan'; assert.equal(canDownloadGame(value,value),false);
 value.download_bytes=8192;assert.equal(canDownloadGame(value,value),true);
 assert.equal(canDownloadGame(value,{...value,source_locale:'en'}),false);
 assert.equal(canDownloadGame(value,{...value,target_locales:['ko']}),false);
 assert.equal(canDownloadGame(value,{...value,content_mode:'text-audio'}),false);
});
test('unsafe sizes, duplicate entries and malformed job progress fail closed', () => {
 for(const key of ['download_bytes','installed_bytes','required_disk_bytes'])
  for(const value of [-1,Infinity,Number.MAX_SAFE_INTEGER+1,'0'])assert.throws(()=>validateGameDataRow({...row(),[key]:value}));
 assert.throws(()=>validateGameDataList({schema:'game-data-v1',games:[row(),row()]}));
 assert.throws(()=>validateGameDataRow({...row(),job:{id:'job',status:'running',phase:'download',downloaded_bytes:-1,total_bytes:null,message:''}}));
});
test('selection uses downloaded identity even when a later estimate or error exists', () => {
 const value={...row(),state:'error',revision:'new-estimate',installed_revision:'working-original',can_activate:true};
 assert.equal(validateGameDataRow(value).installed_revision,'working-original');
 assert.throws(()=>validateGameDataRow({...value,installed_revision:null}));
 assert.throws(()=>validateGameDataRow({...value,can_activate:'yes'}));
});
