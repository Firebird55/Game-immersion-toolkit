import {test} from 'node:test';import assert from 'node:assert/strict';
import {handle,operation} from '../services/lexirise-gateway/worker.mjs';
const env={ALLOWED_ORIGINS:'https://firebird55.github.io',ADMISSION:{limit:async()=>({success:true})},ACCOUNT:{limit:async()=>({success:true})}};
const req=(value,headers={})=>new Request('https://gateway.test/v1/request',{method:'POST',headers:{Origin:env.ALLOWED_ORIGINS,Authorization:'Bearer mock-key','Content-Type':'application/json',...headers},body:JSON.stringify(value)});
test('fixed upstream and allowlisted bounded operations',()=>{
 assert.equal(operation({method:'POST',path:'/v1/analyze/text',payload:{text:'你好',language:'zh',fast:false}}).url,'https://api.lexirise.app/v1/analyze/text');
 for(const path of ['https://evil.test','//evil.test','/v1/uploads','/v1/../admin','/v1/me?token=x'])assert.throws(()=>operation({method:'GET',path}));
 assert.throws(()=>operation({method:'PATCH',path:'/v1/settings',payload:{global:{native_lang:'en'}}}));assert.throws(()=>operation({method:'GET',path:'/v1/decks?limit=100000'}));
 assert.equal(operation({method:'POST',path:'/v1/analyze/context',payload:{language:'zh',text:'你好',charStart:0,charEnd:2}}).method,'POST');
 assert.throws(()=>operation({method:'POST',path:'/v1/analyze/context',payload:{language:'zh',text:'你好',charStart:0,charEnd:3}}));
});
test('cancellation interrupts stalled upstream response streams with a safe error',async()=>{
 const abort=new AbortController(),request=new Request(req({path:'/v1/me',method:'GET'}),{signal:abort.signal});
 const result=handle(request,env,async()=>{setTimeout(()=>abort.abort(),10);return new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('{'));}}));});
 assert.equal((await result).status,504);
});
test('writes only forwarded when requested, auth, cache exclusion, redirect and error redaction',async()=>{
 let calls=0;const mock=async(url,init)=>{calls++;assert.equal(init.redirect,'manual');assert.equal(init.cache,'no-store');assert.equal(init.headers.Authorization,'Bearer mock-key');return Response.json({languages:['zh']});};
 const response=await handle(req({path:'/v1/settings',method:'PATCH',payload:{languages:['zh']}}),env,mock);assert.equal(response.status,200);assert.match(response.headers.get('cache-control'),/no-store/);assert.equal(calls,1);
 assert.equal((await handle(req({path:'/v1/me',method:'GET'},{Authorization:''}),env,mock)).status,401);assert.equal(calls,1);
 assert.equal((await handle(req({path:'/v1/me',method:'GET'},{Origin:'https://evil.test'}),env,mock)).status,403);
 for(const status of [302,401,403,429,500]){const r=await handle(req({path:'/v1/me',method:'GET'}),env,async()=>new Response('sensitive-upstream',{status}));assert.ok(r.status>=400);assert.ok(!(await r.text()).includes('sensitive-upstream'));}
 assert.equal((await handle(req({path:'/v1/me',method:'GET'}),{...env,ACCOUNT:{limit:async()=>({success:false})}},mock)).status,429);
 assert.equal((await handle(req({path:'/v1/me',method:'GET'}),env,async()=>{throw Error('secret') })).status,502);
});
