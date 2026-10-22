/** Backend revisions order state. The local scope only owns/cancels requests. */
export type StateContext = {runtime_id:string; state_version:number; account_generation:number};
export function validContext(value: StateContext | undefined): value is StateContext {
  return !!value && typeof value.runtime_id === 'string' && !!value.runtime_id
    && Number.isSafeInteger(value.state_version) && value.state_version >= 0
    && Number.isSafeInteger(value.account_generation) && value.account_generation >= 0;
}

export class StatePoll<T extends {context:StateContext}> {
  private scope = 0;
  private closed = false;
  private current: StateContext | null = null;
  private flight: {controller:AbortController; promise:Promise<void>} | null = null;
  private queued = false;
  private load:(signal:AbortSignal)=>Promise<T>;
  private commit:(value:T)=>void;
  private failed:()=>void;
  constructor(load:(signal:AbortSignal)=>Promise<T>, commit:(value:T)=>void, failed:()=>void = ()=>{}) {
    this.load = load; this.commit = commit; this.failed = failed;
  }

  get context() { return this.current; }
  get generation() { return this.scope; }
  owns(scope:number) { return !this.closed && this.scope === scope; }

  accept(context:StateContext) {
    if (this.closed || !validContext(context)) return false;
    const old = this.current;
    if (old && (context.runtime_id !== old.runtime_id || context.state_version < old.state_version
      || context.account_generation < old.account_generation)) return false;
    this.current = context;
    return true;
  }

  reset(newRuntime = false) {
    this.scope++;
    this.flight?.controller.abort();
    this.flight = null;
    this.queued = false;
    if (newRuntime) this.current = null;
  }

  close() { this.closed = true; this.reset(); }

  request():Promise<void> {
    if (this.closed) return Promise.resolve();
    if (this.flight) { this.queued = true; return this.flight.promise; }
    const scope = this.scope, controller = new AbortController();
    // Defer load so a synchronous loader still sees its owning flight.
    const flight = {controller, promise:Promise.resolve()};
    this.flight = flight;
    flight.promise = Promise.resolve().then(()=>this.load(controller.signal)).then(value=>{
      if (this.owns(scope) && !controller.signal.aborted && this.accept(value.context)) this.commit(value);
    }).catch(()=>{ if (this.owns(scope) && !controller.signal.aborted) this.failed(); }).finally(()=>{
      if (this.flight !== flight) return;
      this.flight = null;
      if (this.queued) {this.queued = false; void this.request();}
    });
    return flight.promise;
  }
}
