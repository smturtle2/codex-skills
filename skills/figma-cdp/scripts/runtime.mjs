/* Trusted browser runtime; caller-authored code is confined to fallback run. */
export async function browserRequest(request, factories, program) {
  const {requestId, expectedFileKey, operation, input} = request;
  const completedSteps = [], createdNodeIds = [], createdEntities = [], affectedEntities = [];
  const entities = new WeakMap(), stepErrors = new Map(), errorDetails = new Map();
  const loadedPages = new Set();
  let serializationRemaining = 10000;
  let mutation = 'none', phase = 'file-check', ledgerTruncated = false, operationResults, figma;
  const message = error => { try { return String(error?.message ?? error); } catch { return 'Unprintable error'; } };
  const marker = (type, extra = {}) => ({$type: type, ...extra});
  const assertObject = (value, label = 'value') => {
    if (!value || typeof value !== 'object' || Array.isArray(value) || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) throw new TypeError(`${label} must be a plain object`);
    return value;
  };
  const assertId = (value, label = 'id') => {
    if (typeof value !== 'string' || !value.trim()) throw new TypeError(`${label} must be a nonempty string`);
    return value;
  };
  const integer = (value, fallback, max, label, min = 0) => {
    const result = value === undefined ? fallback : value;
    if (!Number.isInteger(result) || result < min || result > max) throw new TypeError(`${label} must be an integer from ${min} to ${max}`);
    return result;
  };
  const identity = (target, kind = 'node') => kind === 'image' ? {kind, hash: target.hash}
    : {kind, id: target.id, ...(kind === 'mode' && {collectionId: target.collectionId})};
  const remember = (target, kind = 'node') => { if (target && typeof target === 'object') entities.set(target, kind); return target; };
  const retain = (list, entry) => {
    if (list.some(item => item.kind === entry.kind && item.id === entry.id && item.hash === entry.hash && item.collectionId === entry.collectionId)) return;
    if (list.length < 2000) list.push(entry); else ledgerTruncated = true;
  };
  const trackCreated = (target, kind = 'node') => {
    const ref = identity(target, kind);
    if (typeof (ref.id ?? ref.hash) !== 'string') throw new TypeError('A created entity needs a native identity');
    remember(target, kind); retain(createdEntities, ref);
    if (kind === 'node' && !createdNodeIds.includes(target.id)) {
      if (createdNodeIds.length < 2000) createdNodeIds.push(target.id); else ledgerTruncated = true;
    }
    return target;
  };
  const trackAffected = (target, kind = 'node') => { remember(target, kind); retain(affectedEntities, identity(target, kind)); return target; };
  const beginStep = (label, fn) => {
    if (typeof label !== 'string' || !label || label.length > 200 || typeof fn !== 'function') throw new TypeError('step needs a label and function');
    if (completedSteps.length >= 2000) throw new Error('Completed step result limit reached');
    phase = label;
  };
  const step = async (label, fn) => {
    beginStep(label, fn);
    try { const value = await fn(); completedSteps.push(label); return value; }
    catch (error) { if (!stepErrors.has(error)) stepErrors.set(error, label); throw error; }
  };
  const write = (label, fn) => step(label, () => { mutation = 'possible'; return fn(); });
  const writeSync = (label, fn) => {
    beginStep(label, fn);
    mutation = 'possible';
    try {
      const value = fn();
      if (value != null && typeof value.then === 'function') throw new TypeError('A synchronous write cannot return a promise');
      completedSteps.push(label);
      return value;
    } catch (error) { if (!stepErrors.has(error)) stepErrors.set(error, label); throw error; }
  };
  const error = (label, detail, details) => {
    const result = new Error(detail);
    stepErrors.set(result, label);
    if (details !== undefined) errorDetails.set(result, details);
    return result;
  };
  const loadPage = async target => {
    if (target?.type === 'PAGE' && typeof target.loadAsync === 'function' && !loadedPages.has(target.id)) {
      await target.loadAsync();
      loadedPages.add(target.id);
    }
    return target;
  };
  const node = async id => {
    assertId(id);
    const value = await figma.getNodeByIdAsync(id);
    if (!value || value.removed) throw new Error(`Missing node: ${id}`);
    return remember(value);
  };
  const entity = async (kind, id) => {
    assertId(id);
    if (['node', 'component', 'page'].includes(kind)) return node(id);
    let value;
    if (kind === 'style') value = await figma.getStyleByIdAsync(id);
    else if (kind === 'variable') value = await figma.variables.getVariableByIdAsync(id);
    else if (kind === 'collection') value = await figma.variables.getVariableCollectionByIdAsync(id);
    else if (kind === 'image') value = figma.getImageByHash(id);
    else throw new TypeError(`Unsupported entity kind: ${kind}`);
    if (!value || value.removed) throw new Error(`Missing ${kind}: ${id}`);
    return remember(value, kind);
  };
  const serialize = (value, origin) => {
    const ancestors = new WeakSet();
    const continuation = (path, offset = 0) => origin && ({kind: 'property', id: origin.id, entityKind: origin.entityKind ?? 'node', path, offset});
    const visit = (item, depth, path) => {
      const next = continuation(path);
      if (--serializationRemaining < 0) return marker('truncated', {reason: 'value-budget', ...(next && {continuation: next})});
      if (item === figma.mixed) return marker('mixed');
      if (item === null || typeof item === 'boolean') return item;
      if (typeof item === 'string') return item.length <= 4000 ? item : marker('truncated', {reason: 'string', value: item.slice(0, 4000), length: item.length, ...(origin && {continuation: continuation(path, 4000)})});
      if (typeof item === 'number') return Number.isFinite(item) ? item : marker('number', {value: String(item)});
      if (item === undefined) return marker('undefined');
      if (typeof item !== 'object') return marker('unsupported', {kind: typeof item});
      try {
        const kind = entities.get(item) ?? (typeof item.getPluginData === 'function' && typeof item.remove === 'function' && typeof item.id === 'string' && typeof item.type === 'string' ? 'node' : undefined);
        if (kind) return marker('reference', {...identity(item, kind), ...(item.type && {type: item.type})});
        if (ancestors.has(item)) return marker('circular');
        if (depth >= 6) return marker('truncated', {reason: 'value-depth', ...(next && {continuation: next})});
        const array = Array.isArray(item);
        if (!array && ![Object.prototype, null].includes(Object.getPrototypeOf(item))) return marker('unsupported', {kind: Object.prototype.toString.call(item)});
        const keys = array ? Array.from({length: Math.min(item.length, 100)}, (_, i) => i) : Object.keys(item).slice(0, 100);
        const result = array ? [] : Object.create(null);
        ancestors.add(item);
        for (const key of keys) {
          try { result[key] = visit(item[key], depth + 1, [...path, key]); }
          catch (error) { result[key] = marker('error', {message: message(error)}); }
        }
        ancestors.delete(item);
        const length = array ? item.length : Object.keys(item).length;
        return length <= 100 ? result : marker('truncated', {reason: array ? 'array' : 'object', value: result, length, ...(origin && {continuation: continuation(path, 100)})});
      } catch (error) { return marker('error', {message: message(error)}); }
    };
    return visit(value, 0, origin?.path ?? []);
  };
  const fields = (target, names) => {
    const kind = entities.get(target) ?? 'node';
    const result = {...identity(target, kind), ...(target.type && {type: target.type})};
    for (const name of names) {
      if (['id', 'type', 'kind', 'hash'].includes(name)) continue;
      try {
        if (name === 'parentId' && kind === 'node') result.parentId = target.parent?.id ?? null;
        else if (name in target) result[name] = serialize(target[name], {id: target.id ?? target.hash, entityKind: kind, path: [name]});
      } catch (error) { result[name] = marker('error', {message: message(error)}); }
    }
    return result;
  };
  const brief = target => fields(target, ['name', 'parentId', 'x', 'y', 'width', 'height', 'layoutMode', 'characters', 'fontName']);
  const ctx = {node, entity, loadPage, remember, trackCreated, trackAffected, step, write, writeSync, error, serialize, fields, brief, assertObject, assertId, integer, children: target => 'children' in target ? target.children : []};
  const describe = descriptor => {
    const {execute, ...data} = descriptor, missing = [];
    for (const path of descriptor.requires ?? []) {
      let value = figma;
      try { for (const part of path.split('.')) value = value?.[part]; } catch { value = undefined; }
      if (typeof value !== 'function') missing.push(path);
    }
    return {...data, availability: {state: missing.length ? 'unavailable' : descriptor.targetMethods?.length ? 'target-dependent'
      : descriptor.requires?.length ? 'available' : 'not-checked', missing}};
  };
  const shape = (value, descriptor, common = []) => {
    assertObject(value);
    const keys = new Set([...common, ...(descriptor.required ?? []), ...(descriptor.optional ?? [])]);
    for (const key of Object.keys(value)) if (!keys.has(key)) throw new TypeError(`Unknown ${value.kind ?? ''} ${value.action ?? ''} field: ${key}`);
    for (const key of descriptor.required ?? []) if (!Object.hasOwn(value, key)) throw new TypeError(`Missing field: ${key}`);
  };
  try {
    const url = new URL(location.href), match = url.pathname.match(/^\/(?:design|file)\/([^/]+)(?:\/|$)/);
    if (url.protocol !== 'https:' || url.hostname !== 'www.figma.com' || !match || match[1] !== expectedFileKey) throw new Error('The active Figma file URL does not match the bound fileKey');
    phase = 'api-check'; figma = window.figma;
    if (!figma || typeof figma.getNodeByIdAsync !== 'function') throw new Error('Native window.figma API is unavailable');
    ctx.figma = figma; remember(figma.root); ctx.requestPage = remember(figma.currentPage);
    for (const entry of factories) ctx[entry.name] = entry.create(ctx);
    const edits = new Map(), queries = new Map();
    for (const entry of factories) {
      for (const descriptor of ctx[entry.name].edits ?? []) {
        const key = `${descriptor.kind}:${descriptor.action}`;
        if (edits.has(key)) throw new Error(`Duplicate operation owner: ${key}`);
        edits.set(key, descriptor);
      }
      for (const descriptor of ctx[entry.name].queries ?? []) {
        if (queries.has(descriptor.kind)) throw new Error(`Duplicate query owner: ${descriptor.kind}`);
        queries.set(descriptor.kind, descriptor);
      }
    }
    ctx.catalog = () => ({primary: ['inspect', 'edit', 'view', 'export'], fallback: ['run'], edits: [...edits.values()].map(describe), queries: [...queries.values()].map(describe), view: ctx.view.definition, export: ctx.exports.definition, note: 'Availability checks API exposure; target restrictions, permissions, fonts, and plan limits can still reject an operation.'});
    let value;
    if (operation === 'inspect') {
      const descriptor = queries.get(input.kind);
      if (!descriptor) throw new TypeError(`Unsupported inspection kind: ${input.kind}`);
      shape(input, descriptor, ['kind']); phase = `inspect:${input.kind}`;
      value = await descriptor.execute(input);
    } else if (operation === 'edit') {
      operationResults = [];
      for (const op of input.operations) {
        const descriptor = edits.get(`${op.kind}:${op.action}`);
        if (!descriptor) throw new TypeError(`Unsupported edit: ${op.kind}:${op.action}`);
        shape(op, descriptor, ['kind', 'action']);
        if (op.props !== undefined && descriptor.propsKind === 'node') {
          phase = `${op.kind}:${op.action}:props`;
          ctx.nodes.validateBasicProps(op.props);
        }
      }
      for (let index = 0; index < input.operations.length; index++) {
        const op = input.operations[index], descriptor = edits.get(`${op.kind}:${op.action}`);
        try {
          phase = `${op.kind}:${op.action}`;
          operationResults.push({index, kind: op.kind, action: op.action, ok: true, value: await descriptor.execute(op)});
        } catch (error) {
          operationResults.push({index, kind: op.kind, action: op.action, ok: false, error: {message: message(error)}});
          throw error;
        }
      }
      value = {operations: operationResults};
    } else if (operation === 'view') value = await ctx.view.update(input);
    else if (operation === 'export') value = await ctx.exports.export(input);
    else if (operation === 'run') {
      phase = 'fallback-program'; mutation = 'possible';
      value = serialize(await program({figma, input, node, apply: ctx.nodes.apply, brief, step, recordCreated: trackCreated}));
    } else throw new TypeError(`Unsupported tool: ${operation}`);
    return {ok: true, requestId, value, completedSteps, createdNodeIds, createdEntities, affectedEntities, mutation, ...(ledgerTruncated && {ledgerTruncated: true})};
  } catch (error) {
    return {ok: false, requestId, error: {kind: 'remote', message: message(error), ...(errorDetails.has(error) && {details: serialize(errorDetails.get(error))})}, failurePoint: stepErrors.get(error) ?? phase,
      completedSteps, createdNodeIds, createdEntities, affectedEntities, mutation,
      ...(operationResults && {partial: {operations: operationResults, unstarted: input.operations.slice(operationResults.length).map((op, offset) => ({index: operationResults.length + offset, kind: op.kind, action: op.action}))}}),
      ...(ledgerTruncated && {ledgerTruncated: true})};
  }
}

export function buildExpression(request, factories, program) {
  const definitions = factories.map(entry => `{name:${JSON.stringify(entry.name)},create:(${entry.create.toString()})}`).join(',');
  const fallback = program === undefined ? 'undefined' : `async ({figma,input,node,apply,brief,step,recordCreated}) => {\n${program}\n}`;
  return `(${browserRequest.toString()})(JSON.parse(${JSON.stringify(JSON.stringify(request))}),[${definitions}],${fallback})`;
}
