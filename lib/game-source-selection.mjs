/** Serialize explicit choices; only the newest queued choice starts afterward.
 * Aborting an HTTP request cannot roll back a committed source activation.
 * @param {{activate:(game:string)=>Promise<unknown>, current:()=>boolean,
 * committed?:()=>void, failed?:()=>void}} options
 */
export function createGameSourceSelection({activate, current, committed = () => {}, failed = () => {}}) {
  let revision = 0, pending = null, disposed = false, running = false, drain = Promise.resolve();
  const owns = choice => !disposed && choice.revision === revision && current();
  return {
    select(game) {
      if (disposed) return drain;
      pending = {game, revision: ++revision};
      if (!running) {
        running = true;
        drain = (async () => {
          try {
            while (pending && !disposed) {
              const choice = pending; pending = null;
              if (!owns(choice)) continue;
              try {
                await activate(choice.game);
                if (owns(choice)) committed();
              } catch {
                if (owns(choice)) failed();
              }
            }
          } finally {running = false;}
        })();
      }
      return drain;
    },
    cancel() {revision++; pending = null;},
    dispose() {disposed = true; revision++; pending = null;},
  };
}
