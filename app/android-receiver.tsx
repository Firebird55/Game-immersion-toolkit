'use client';
import {useEffect, useRef, useState} from 'react';
import {Button} from '../components/ui/button';
import {Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription} from '../components/ui/dialog';
import {desktopApiBase} from '../lib/desktop-endpoints';
import {type NativeCapabilities} from '../lib/native-host';
import {useNativeAccountGeneration} from '../lib/native-account-context';
import {createAndroidReceiver} from '../lib/android-receiver.mjs';
import {createReceiverSource} from '../public/mobile-capture/receiver-source.mjs';
import {createVdoFrameSource} from '../public/mobile-capture/vdo-source.mjs';
import {createPastedScreenSource} from '../lib/pasted-screen-source.mjs';
import './android-receiver.css';

type ReceiverState = {status: string; message: string; active: boolean; paused?: boolean;
 width?: number; height?: number; acceptedFrames?: number};

export function AndroidReceiver({online, libraryReady, libraryRevision, capabilities, onChanged}: {
 online: boolean; libraryReady: boolean; libraryRevision: string | null; capabilities: NativeCapabilities | null; onChanged: () => void;
}) {
 const accountGeneration = useNativeAccountGeneration();
 const viewer = useRef<HTMLDivElement>(null);
 const controller = useRef<ReturnType<typeof createAndroidReceiver> | null>(null);
 const pasted = useRef<ReturnType<typeof createPastedScreenSource> | null>(null);
 const privateLink = useRef('');
 const changed = useRef(onChanged); changed.current = onChanged;
 const enabled = useRef(false);
 const previousLibrary = useRef(libraryRevision);
 const documentEpoch = useRef<string | null>(null);
 const [link, setLink] = useState(''), [ready, setReady] = useState(false);
 const [instructions, setInstructions] = useState(false);
 const [state, setState] = useState<ReceiverState>({status: 'ready', message: 'Connect the game device to begin.', active: false});
 const supported = capabilities?.capture_source === 'remote-stream' && capabilities.receiver_protocol === 'leased-frames-v1';
 const maximum = capabilities?.max_frame_bytes ?? 10 * 1024 ** 2;

 useEffect(() => {
  if (previousLibrary.current !== libraryRevision) {
   // Carry a draft into the first preparation. An existing library's source
   // still retires immediately when that library is replaced or removed.
   if (previousLibrary.current !== null) {privateLink.current = ''; setLink('');}
   previousLibrary.current = libraryRevision;
  }
  if (!supported || !viewer.current || accountGeneration === null) return;
  // Never adopt a later platform/snapshot nonce in an old document.
  if (documentEpoch.current === null)
   documentEpoch.current = document.querySelector('meta[name="toolkit-document-epoch"]')?.getAttribute('content') ?? '';
  if (!/^[a-f0-9]{32}$/.test(documentEpoch.current)) {
   setState({status: 'error', active: false, message: 'Reopen the app before connecting a screen source.'}); return;
  }
  const container = viewer.current;
  const source = createReceiverSource({vdo: () => createVdoFrameSource({container})});
  const canvas = document.createElement('canvas');
  const receiver = createAndroidReceiver({source, apiBase: desktopApiBase(), documentEpoch: documentEpoch.current,
   maxFrameBytes: maximum, accountGeneration, encodeFrame: async (frame: {width: number; height: number; image: CanvasImageSource}, {signal}: {signal: AbortSignal}) => {
    if (signal.aborted) throw new DOMException('Screen source changed', 'AbortError');
    canvas.width = frame.width; canvas.height = frame.height;
    const context = canvas.getContext('2d');
    if (!context) throw Error('The app cannot prepare screen frames.');
    context.drawImage(frame.image, 0, 0, frame.width, frame.height);
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value)
     : reject(Error('The app cannot prepare this screen frame.')), 'image/png'));
    if (signal.aborted) throw new DOMException('Screen source changed', 'AbortError');
    return blob;
   }});
  controller.current = receiver;
  const linkSource = createPastedScreenSource({receiver, onChanged: () => changed.current(),
   onError: (message: string) => setState({status: 'error', active: false, message})});
  pasted.current = linkSource;
  const unsubscribe = receiver.subscribe((value: ReceiverState) => setState(value));
  const pause = () => linkSource.replace(privateLink.current, {enabled: false});
  const resume = () => linkSource.replace(privateLink.current, {enabled: enabled.current && !document.hidden});
  const visibility = () => {if (document.hidden) pause(); else resume();};
  window.addEventListener('toolkit-host-pause', pause);
  window.addEventListener('toolkit-host-resume', resume);
  document.addEventListener('visibilitychange', visibility);
  window.addEventListener('pagehide', pause);
  setReady(true);
  return () => {
   setReady(false); unsubscribe(); linkSource.dispose(); receiver.dispose(); controller.current = null; pasted.current = null;
   window.removeEventListener('toolkit-host-pause', pause);
   window.removeEventListener('toolkit-host-resume', resume);
   document.removeEventListener('visibilitychange', visibility);
   window.removeEventListener('pagehide', pause);
  };
 }, [supported, maximum, accountGeneration, libraryRevision]);

 enabled.current = ready && online && libraryReady;
 useEffect(() => {pasted.current?.replace(privateLink.current, {enabled: enabled.current && !document.hidden});}, [ready, online, libraryReady, libraryRevision]);

 return <section className="android-screen-card game-start-card" aria-label="Receive game screen"
  data-capture-ready={supported && enabled.current}>
  <h2>Game screen</h2>
  <label className="sr-only" htmlFor="android-screen-link">VDO.Ninja link or stream code</label>
  <input id="android-screen-link" type="password" value={link} placeholder="VDO.Ninja link or stream code"
   onChange={event => {const value = event.target.value; privateLink.current = value; setLink(value);
    pasted.current?.replace(value, {enabled: enabled.current && !document.hidden});}}
   autoComplete="off" autoCapitalize="none" spellCheck={false} inputMode="url" maxLength={4096} />
  <div className="toolkit-setup-actions">
   <Button variant="outline" onClick={() => setInstructions(true)}>Instructions</Button>
  </div>
  <p role="status">{!supported ? 'Screen reception is unavailable in this app build.'
   : !libraryReady ? 'Finish preparing this game’s data in Settings to connect the stream.'
   : !online ? 'Waiting for the app to reconnect.' : link.trim() || state.status === 'error' ? state.message : ''}</p>
  <div ref={viewer} className="android-screen-viewer" hidden={!state.active}
   style={{aspectRatio: state.width && state.height ? `${state.width}/${state.height}` : '16/9'}} />
  <Dialog open={instructions} onOpenChange={setInstructions}><DialogContent><DialogHeader>
   <DialogTitle>Game screen instructions</DialogTitle>
   <DialogDescription>Start screen broadcasting in VDO.Ninja on your game device. Paste its viewer link or enter its stream code, for example iphone. Keep the broadcast running while you read. Clear the field to disconnect.</DialogDescription>
  </DialogHeader></DialogContent></Dialog>
 </section>;
}
