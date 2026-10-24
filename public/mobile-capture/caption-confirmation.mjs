// One missing scan is tolerated; two actual matching observations are required.
export function confirmCaptions(previous, identities, now, grace = false) {
 const active=new Set(identities),next=new Map();
 for(const [id,value] of previous) {
  if(!active.has(id)&&grace&&value.misses===0&&now-value.seen<=750)
   next.set(id,{...value,misses:1});
 }
 for(const id of active) {
  const old=previous.get(id);
  next.set(id,{count:old&&now-old.seen<=750?old.count+1:1,seen:now,misses:0});
 }
 return next;
}
// Comic scans can take seconds. Require two observed frames independently for
// each bubble, without republishing a bubble that stays on screen.
export function confirmComicCaptions(previous,identities){
 const active=new Set(identities),state=new Map(),ready=new Set();
 for(const [id,old] of previous)if(!active.has(id)&&!old.misses)state.set(id,{...old,misses:1});
 for(const id of active){const old=previous.get(id),count=(old?.count??0)+1,published=old?.published??false;
  if(count>=2&&!published)ready.add(id);
  state.set(id,{count,published:published||ready.has(id),misses:0});
 }
 return {state,ready};
}
