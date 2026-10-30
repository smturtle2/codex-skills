/* One registry supplies dispatch, accepted fields, and capability discovery. */
import {createNodeOperations} from './nodes.mjs';
import {createTextOperations} from './text.mjs';
import {createComponentOperations} from './components.mjs';
import {createStructureOperations} from './structure.mjs';
import {createResourceOperations} from './resources.mjs';
import {createInspectionOperations} from './inspect.mjs';
import {createViewOperations} from './view.mjs';
import {createExportOperations} from './export.mjs';

export const factories = [
  {name: 'text', create: createTextOperations}, {name: 'components', create: createComponentOperations},
  {name: 'resources', create: createResourceOperations}, {name: 'nodes', create: createNodeOperations},
  {name: 'structure', create: createStructureOperations}, {name: 'inspection', create: createInspectionOperations},
  {name: 'view', create: createViewOperations}, {name: 'exports', create: createExportOperations}
];
const services = factories.map(entry => entry.create({}));
const edits = new Map(), queries = new Map();
for (const service of services) {
  for (const descriptor of service.edits ?? []) {
    const key = `${descriptor.kind}:${descriptor.action}`;
    if (edits.has(key)) throw new Error(`Duplicate operation owner: ${key}`);
    edits.set(key, descriptor);
  }
  for (const descriptor of service.queries ?? []) {
    if (queries.has(descriptor.kind)) throw new Error(`Duplicate query owner: ${descriptor.kind}`);
    queries.set(descriptor.kind, descriptor);
  }
}
function object(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new TypeError(`${label} must be a plain object`);
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== null && prototype !== Object.prototype) {
    const constructor = Object.getOwnPropertyDescriptor(prototype, 'constructor')?.value;
    const foreignObject = Object.getPrototypeOf(prototype) === null && typeof constructor === 'function' &&
      constructor.prototype === prototype && Function.prototype.toString.call(constructor) === Function.prototype.toString.call(Object);
    if (!foreignObject) throw new TypeError(`${label} must be a plain object`);
  }
  return value;
}
function data(value, ancestors = new Set()) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (!value || typeof value !== 'object') throw new TypeError('Arguments must contain plain JSON data');
  if (ancestors.has(value)) throw new TypeError('Arguments contain a cycle');
  if (!Array.isArray(value)) object(value, 'argument');
  if (Object.getOwnPropertySymbols(value).length) throw new TypeError('Arguments cannot contain symbol keys');
  const copy = Array.isArray(value) ? [] : Object.create(null);
  ancestors.add(value);
  const keys = Array.isArray(value) ? Array.from({length: value.length}, (_, i) => String(i)) : Object.keys(value);
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !('value' in descriptor)) throw new TypeError('Arguments cannot contain getters or sparse arrays');
    copy[key] = data(descriptor.value, ancestors);
  }
  ancestors.delete(value);
  return copy;
}
function shape(value, descriptor, common) {
  object(value, 'request');
  const allowed = new Set([...common, ...(descriptor.required ?? []), ...(descriptor.optional ?? [])]);
  for (const key of Object.keys(value)) if (!allowed.has(key)) throw new TypeError(`Unknown field: ${key}`);
  for (const key of descriptor.required ?? []) if (!Object.hasOwn(value, key)) throw new TypeError(`Missing field: ${key}`);
}
export function normalize(operation, value) {
  const input = data(value === undefined ? {} : value);
  if (operation === 'run') return input;
  object(input, `${operation} request`);
  if (operation === 'inspect') {
    input.kind ??= 'nodes';
    const descriptor = queries.get(input.kind);
    if (!descriptor) throw new TypeError(`Unsupported inspection kind: ${input.kind}`);
    shape(input, descriptor, ['kind']);
  } else if (operation === 'edit') {
    shape(input, {required: ['operations']}, []);
    if (!Array.isArray(input.operations) || !input.operations.length || input.operations.length > 100) throw new TypeError('edit requires 1–100 operations');
    for (const op of input.operations) {
      object(op, 'edit operation'); op.kind ??= 'node';
      const descriptor = edits.get(`${op.kind}:${op.action}`);
      if (!descriptor) throw new TypeError(`Unsupported edit: ${op.kind}:${op.action}`);
      shape(op, descriptor, ['kind', 'action']);
      if (op.props !== undefined && op.kind === 'node' && op.action !== 'text') services.find(service => service.validateBasicProps)?.validateBasicProps(op.props);
    }
  } else if (operation === 'view') shape(input, services.find(service => service.state).definition, []);
  else if (operation === 'export') {
    const definition = services.find(service => service.export).definition;
    shape(input, definition, []);
    input.settings ??= {format: 'PNG'};
    object(input.settings, 'export settings');
    if (!definition.formats.includes(input.settings.format)) throw new TypeError('Unsupported export format');
  } else throw new TypeError(`Unsupported tool: ${operation}`);
  return input;
}
export function reviewOptions(options = {}) {
  const result = data(object(options, 'options'));
  for (const key of Object.keys(result)) if (!['inspect', 'preview'].includes(key)) throw new TypeError(`Unknown observation option: ${key}`);
  if (result.inspect !== undefined) {
    object(result.inspect, 'options.inspect');
    const query = {...result.inspect, kind: result.inspect.kind ?? 'nodes'};
    // A returned node can supply missing node targets after the edit acknowledgement.
    normalize('inspect', query);
    result.inspect = query;
  }
  if (result.preview !== undefined) {
    object(result.preview, 'options.preview');
    const {id, ...rest} = result.preview;
    normalize('export', {id: id ?? 'returned-node', ...rest});
  }
  return result;
}
