'use client';
import {useEffect, useRef, useState} from 'react';
import {Play, Square} from 'lucide-react';
import {Button} from '../components/ui/button';
import {desktopApiBase} from '../lib/desktop-endpoints';
import {type NativeCapabilities} from '../lib/native-host';
import {useNativeAccountGeneration} from '../lib/native-account-context';
import {createAndroidReceiver} from '../lib/android-receiver.mjs';
import {createReceiverSource} from '../public/mobile-capture/receiver-source.mjs';
import {createVdoFrameSource} from '../public/mobile-capture/vdo-source.mjs';
import './android-receiver.css';

type ReceiverState = {status: string; message: string; active: boolean; paused?: boolean;
 width?: number; height?: number; acceptedFrames?: number};

export function AndroidReceiver({online, libraryReady, capabilities, onChanged}: {
 online: boolean; libraryReady: boolean; capabilities: NativeCapabilities | null; onChanged: () => void;
}) {
 const accountGeneration = useNativeAccountGeneration();
 const viewer = useRef<HTMLDivElement>(null);
 const controller = useRef<ReturnType<typeof createAndroidReceiver> | null>(null);
 const documentEpoch = useRef<string | null>(null);
 const [link, setLink] = useState(''), [ready, setReady] = useState(false);
 const [state, setState] = useState<ReceiverState>({status: 'ready', message: 'Connect the game device to begin.', active: false});
 const supported = capabilities?.capture_source === 'remote-stream' && capabilities.receiver_protocol === 'leased-frames-v1';
 const maximum = capabilities?.max_frame_bytes ?? 10 * 1024 ** 2;

 useEffect(() => {
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
  const unsubscribe = receiver.subscribe((value: ReceiverState) => setState(value));
  const pause = () => receiver.pause(), resume = () => {void receiver.resume();};
  const visibility = () => {if (document.hidden) pause(); else resume();};
  window.addEventListener('toolkit-host-pause', pause);
  window.addEventListener('toolkit-host-resume', resume);
  document.addEventListener('visibilitychange', visibility);
  window.addEventListener('pagehide', pause);
  setReady(true);
  return () => {
   setReady(false); unsubscribe(); receiver.dispose(); controller.current = null;
   window.removeEventListener('toolkit-host-pause', pause);
   window.removeEventListener('toolkit-host-resume', resume);
   document.removeEventListener('visibilitychange', visibility);
   window.removeEventListener('pagehide', pause);
  };
 }, [supported, maximum, accountGeneration]);

 useEffect(() => {if (!online || !libraryReady) void controller.current?.stop();}, [online, libraryReady]);

 return <section className="android-screen-card game-start-card" aria-label="Receive game screen">
  <div><h2>Game screen</h2><p>On the iPhone or iPad, start screen broadcasting in the VDO.Ninja app. Paste its viewer link here.</p></div>
  <label htmlFor="android-screen-link">Private viewer link or stream code</label>
  <input id="android-screen-link" type="password" value={link} onChange={event => setLink(event.target.value)}
   autoComplete="off" autoCapitalize="none" spellCheck={false} inputMode="url" />
  <div className="toolkit-setup-actions">
   <Button variant="outline" disabled={!ready || !online || !libraryReady || !link.trim() || state.status === 'stopping'}
    onClick={() => {void controller.current?.connect(link).then(onChanged);}}><Play size={16} />{state.active ? 'Reconnect' : 'Connect screen'}</Button>
   <Button variant="outline" disabled={!state.active || state.status === 'stopping'}
    onClick={() => {void controller.current?.stop().then(onChanged);}}><Square size={16} />Stop screen</Button>
  </div>
  <p role="status">{!supported ? 'Screen reception is unavailable in this app build.'
   : !libraryReady ? 'Import the selected game’s prepared library before connecting.' : state.message}</p>
  <div ref={viewer} className="android-screen-viewer" hidden={!state.active}
   style={{aspectRatio: state.width && state.height ? `${state.width}/${state.height}` : '16/9'}} />
  <p className="toolkit-setup-note">The link stays in memory. VDO.Ninja transports the screen; text recognition and saved recordings are processed on this device. The game device must start or restart its own broadcast.</p>
  <a href="https://docs.vdo.ninja/guides/screen-share-your-iphone-ipad" target="_blank" rel="noreferrer">Screen broadcasting instructions</a>
 </section>;
}
