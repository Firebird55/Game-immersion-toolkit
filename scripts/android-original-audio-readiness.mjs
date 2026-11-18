/** The first owned caption and its async local recording share one deadline. */
export async function waitForOwnedOriginalAudio(readSnapshot, until, {
  accountGeneration, textId = 'authored:bridge', report = () => {},
}) {
  const evidence = {schema:'toolkit-authored-original-audio-readiness-v1',state:'waiting-for-row',
    polls:0,pending_polls:0,not_ready_polls:0,materialization_failed:false};
  let first = null;
  const reject = reason => ({rejected:reason});
  try {
    const result = await until(async () => {
      const snapshot = await readSnapshot();evidence.polls++;
      const context = snapshot?.context, capture = snapshot?.status?.capture;
      if (context?.account_generation !== accountGeneration) return reject('account-changed');
      if (!Array.isArray(snapshot.lines) || !snapshot.lines.length) return null;
      const line = snapshot.lines[0];
      if (!Number.isSafeInteger(line.id) || line.id < 1 || line.text_id !== textId) return reject('foreign-first-row');
      if (!Number.isSafeInteger(capture?.source_generation) || typeof context.runtime_id !== 'string') return reject('invalid-source-scope');
      if (!first) {
        first = {id:line.id,account:accountGeneration,generation:capture.source_generation,runtime:context.runtime_id};
        Object.assign(evidence,{line_id:first.id,account_generation:first.account,source_generation:first.generation});
      }
      if (line.id !== first.id) return reject('first-row-replaced');
      if (capture.source_generation !== first.generation || context.runtime_id !== first.runtime) return reject('source-changed');
      if (capture.running !== true) return reject('capture-stopped');
      if (line.has_audio === true) return {snapshot};
      evidence.state='waiting-for-original';evidence.not_ready_polls++;
      if (line.original_audio_expected !== true) return reject('original-not-expected');
      if (line.audio_pending === false) {
        evidence.materialization_failed=true;return reject('materialization-failed');
      }
      if (line.audio_pending !== true) return reject('invalid-audio-state');
      evidence.pending_polls++;return null;
    }, 'native frame OCR and original audio into the actual reader transcript');
    if (result.rejected) {
      evidence.state='failed';evidence.reason=result.rejected;
      throw Error('Authored original recording was not established: '+result.rejected);
    }
    evidence.state='ready';return result.snapshot;
  } catch (error) {
    if (evidence.state !== 'failed') evidence.state='timeout';
    throw error;
  } finally { report(evidence); }
}
