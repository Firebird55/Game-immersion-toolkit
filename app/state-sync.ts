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
  private failed:(error:unknown)=>void;
  private reconcile?: (value:T)=>T;
  constructor(load:(signal:AbortSignal)=>Promise<T>, commit:(value:T)=>void, failed:(error:unknown)=>void = ()=>{}, reconcile?: (value:T)=>T) {
    this.load = load; this.commit = commit; this.failed = failed; this.reconcile = reconcile;
  }

  get context() { return this.current; }
  get generation() { return this.scope; }
  owns(scope:number) { return !this.closed && this.scope === scope; }

  accept(context:StateContext, partial = false) {
    if (this.closed || !validContext(context)) return false;
    const old = this.current;
    if (old && (context.runtime_id !== old.runtime_id || (!partial && context.state_version < old.state_version)
      || context.account_generation < old.account_generation)) return false;
    this.current = !old || context.state_version >= old.state_version ? context
      : {...context, state_version:old.state_version};
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
    const scope = this.scope, observedContext = this.current, controller = new AbortController();
    // Defer load so a synchronous loader still sees its owning flight.
    const flight = {controller, promise:Promise.resolve()};
    this.flight = flight;
    flight.promise = Promise.resolve().then(()=>this.load(controller.signal)).then(value=>{
      if (this.owns(scope) && !controller.signal.aborted && this.accept(value.context, !!this.reconcile))
        this.commit(this.reconcile ? this.reconcile(value) : value);
    }).catch(error=>{
      // A newer accepted event also invalidates a late HTTP failure indicator.
      if (this.owns(scope) && !controller.signal.aborted && this.current === observedContext) this.failed(error);
    }).finally(()=>{
      if (this.flight !== flight) return;
      this.flight = null;
      if (this.queued) {this.queued = false; void this.request();}
    });
    return flight.promise;
  }
}

/** A partial event only supersedes the same domain/record. Complete snapshots
 * replay newer events before committing, so frequent capture updates cannot
 * starve transcript/account reads or erase an independent late line event. */
export class StateEvents<E extends {context:StateContext}> {
  private snapshot:StateContext|null = null;
  private events = new Map<string,E>();
  reset() {this.snapshot = null; this.events.clear();}
  record(key:string,event:E) {
    const context = event.context, previous = this.events.get(key)?.context;
    if (!validContext(context)) return false;
    if (this.snapshot && (context.runtime_id !== this.snapshot.runtime_id
      || context.account_generation < this.snapshot.account_generation
      || context.state_version <= this.snapshot.state_version)) return false;
    if (previous && context.state_version <= previous.state_version) return false;
    this.events.set(key,event);
    return true;
  }
  reconcile<T extends {context:StateContext}>(value:T, apply:(value:T,event:E)=>T):T {
    const context=value.context;
    for(const [key,event] of this.events) {
      if (event.context.runtime_id !== context.runtime_id || event.context.account_generation !== context.account_generation
        || event.context.state_version <= context.state_version) this.events.delete(key);
    }
    const pending=[...this.events.values()].sort((a,b)=>a.context.state_version-b.context.state_version);
    this.snapshot=context;
    return pending.reduce(apply,value);
  }
}
