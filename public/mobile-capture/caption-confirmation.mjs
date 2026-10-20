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
