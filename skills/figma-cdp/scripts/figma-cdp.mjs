/* Public CDP interface. Native mechanics belong to the operation owners. */
import {buildExpression} from './runtime.mjs';
import {factories, normalize, reviewOptions} from './operations/index.mjs';

export function createFigmaCDP(cdp, {fileKey} = {}) {
  if (!cdp || typeof cdp.send !== 'function') throw new TypeError('cdp.send is required');
  if (typeof fileKey !== 'string' || !/^[A-Za-z0-9_-]+$/.test(fileKey)) throw new TypeError('fileKey must be the actual Figma file key');
  let tail = Promise.resolve(), sequence = 0, blockedBy;
  const message = error => { try { return String(error?.message ?? error); } catch { return 'Unprintable error'; } };
  const failure = (requestId, kind, detail, write) => ({ok: false, requestId, error: {kind, message: detail}, failurePoint: 'evaluation', completedSteps: [], createdNodeIds: [], createdEntities: [], affectedEntities: [], mutation: write ? 'unknown' : 'none'});
  const evaluate = async (operation, input, requestId, program, write) => {
    let response;
    try { response = await cdp.send('Runtime.evaluate', {expression: buildExpression({requestId, expectedFileKey: fileKey, operation, input}, factories, program), awaitPromise: true, returnByValue: true}); }
    catch (error) { return failure(requestId, 'transport', message(error), write); }
    if (response?.exceptionDetails) return failure(requestId, 'protocol', response.exceptionDetails.text || 'Runtime.evaluate raised an uncaught exception', write);
    const result = response?.result?.value;
    if (!result || result.requestId !== requestId || typeof result.ok !== 'boolean' || !['none', 'possible'].includes(result.mutation) || !Array.isArray(result.completedSteps) || !Array.isArray(result.createdNodeIds) || !Array.isArray(result.createdEntities) || !Array.isArray(result.affectedEntities) || (result.ok ? !Object.hasOwn(result, 'value') : result.error?.kind !== 'remote')) return failure(requestId, 'protocol', 'Missing or invalid Runtime.evaluate result; execution outcome is unknown', write);
    return result;
  };
  const enqueue = (operation, input, options = {}, program) => {
    const requestId = ++sequence, write = ['edit', 'view', 'run'].includes(operation);
    const execute = async () => {
      if (write && blockedBy !== undefined) return {ok: false, requestId, error: {kind: 'blocked', message: 'Reconcile document and editor state, then create a fresh helper before further writes', causeRequestId: blockedBy}, failurePoint: 'queue', completedSteps: [], createdNodeIds: [], createdEntities: [], affectedEntities: [], mutation: 'none'};
      const result = await evaluate(operation, input, requestId, program, write);
      if (!result.ok && write && result.mutation !== 'none') blockedBy = requestId;
      if (result.ok) {
        for (const [key, method] of [['inspect', 'inspect'], ['preview', 'export']]) {
          if (!options[key]) continue;
          const item = result.value?.operations?.length === 1 ? result.value.operations[0].value : result.value;
          const returned = item?.root ?? item?.node ?? item;
          const defaultId = !returned?.kind || returned.kind === 'node' ? returned?.id : undefined;
          let query = options[key];
          const needsTarget = key === 'preview' ? !query.id : query.kind === 'nodes' && !query.ids;
          if (needsTarget) {
            if (!defaultId) { result[key === 'inspect' ? 'inspection' : 'preview'] = {ok: false, error: {kind: 'validation', message: 'Optional observation requires an explicit target or one returned node'}}; continue; }
            query = key === 'inspect' ? {...query, ids: [defaultId]} : {...query, id: defaultId};
          }
          try { result[key === 'inspect' ? 'inspection' : 'preview'] = await evaluate(method, normalize(method, query), requestId, undefined, false); }
          catch (error) { result[key === 'inspect' ? 'inspection' : 'preview'] = {ok: false, error: {kind: 'validation', message: message(error)}}; }
        }
      }
      return result;
    };
    const pending = tail.then(execute); tail = pending.catch(() => {}); return pending;
  };
  return Object.freeze({
    inspect: query => enqueue('inspect', normalize('inspect', query)),
    edit: (request, options) => enqueue('edit', normalize('edit', request), reviewOptions(options)),
    view: (request, options) => enqueue('view', normalize('view', request), reviewOptions(options)),
    export: request => enqueue('export', normalize('export', request)),
    run: (program, input = {}, options) => {
      if (typeof program !== 'string' || !program.trim()) throw new TypeError('Fallback run requires an explicit async JavaScript body');
      return enqueue('run', normalize('run', input), reviewOptions(options), program);
    }
  });
}
