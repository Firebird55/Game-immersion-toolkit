// Source ownership lives here; transport and OCR never share their own objects.
// A source's options (including private viewer URLs) are memory-only.
export function createReceiverSource(factories) {
 let source=null,kind=null,options=null,intent=false,paused=false,revision=0,pending=null,unsubscribe=null;
 let state={sessionId:null,status:'ready',width:0,height:0,lastFrameTimestamp:null,message:'Choose a screen source.'};
 const listeners=new Set();
 const publish=value=>{state={...value,kind,revision};for(const listener of listeners)listener({...state});};
 const invalidate=()=>{revision++;pending?.abort();pending=null;};
 function detach(){invalidate();unsubscribe?.();unsubscribe=null;source?.dispose();source=null;}
 async function connectSource(){
  const active=source,token=revision;
  unsubscribe=active.subscribe(value=>{if(source===active&&revision===token)publish(value);});
  try{if(source===active&&revision===token)await active.connect(options);}
  catch{if(source===active&&revision===token){const current=active.getState();publish({...current,status:'error',message:current.status==='error'?current.message:'Could not connect. Check the source and try again.'});}}
 }
 const api={
  get active(){return intent;},
  getState:()=>({...state,kind,revision}),
  subscribe(listener){listeners.add(listener);listener(api.getState());return()=>listeners.delete(listener);},
  connect(nextKind,nextOptions={}){
   if(typeof factories[nextKind]!=='function')throw new Error('Unsupported screen source.');
   detach();kind=nextKind;options={...nextOptions};intent=true;paused=false;source=factories[kind]();
   return connectSource();
  },
  disconnect(){intent=false;options=null;paused=false;detach();publish({sessionId:null,status:'ended',width:0,height:0,lastFrameTimestamp:null,message:'Screen source stopped.'});},
  pause(){if(!intent||paused)return;paused=true;detach();publish({sessionId:null,status:'paused',width:0,height:0,lastFrameTimestamp:null,message:'Screen source paused while this page is hidden.'});},
  resume(){if(!intent||!paused)return Promise.resolve();paused=false;source=factories[kind]();return connectSource();},
  async readFrame({signal}={}){
   if(!source||paused||pending||signal?.aborted)return null;
   const active=source,token=revision,controller=new AbortController();pending=controller;
   const abort=()=>controller.abort();signal?.addEventListener('abort',abort,{once:true});
   try{
    const frame=await active.readFrame({signal:controller.signal});
    if(!frame)return null;
    if(controller.signal.aborted||source!==active||revision!==token||frame.sessionId!==active.getState().sessionId){frame.release();return null;}
    return frame;
   }finally{signal?.removeEventListener('abort',abort);if(pending===controller)pending=null;}
  },
  dispose(){api.disconnect();listeners.clear();}
 };
 return api;
}
