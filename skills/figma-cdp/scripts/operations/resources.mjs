/** Native resource identities, lifecycle, discovery, and application. */
export function createResourceOperations(ctx) {
  const styleFactories = {PAINT: 'createPaintStyle', TEXT: 'createTextStyle', EFFECT: 'createEffectStyle', GRID: 'createGridStyle'};
  const styleLists = {PAINT: 'getLocalPaintStylesAsync', TEXT: 'getLocalTextStylesAsync', EFFECT: 'getLocalEffectStylesAsync', GRID: 'getLocalGridStylesAsync'};
  const styleApplications = {
    fill: ['setFillStyleIdAsync', 'PAINT'], stroke: ['setStrokeStyleIdAsync', 'PAINT'],
    effect: ['setEffectStyleIdAsync', 'EFFECT'], grid: ['setGridStyleIdAsync', 'GRID'], text: ['setTextStyleIdAsync', 'TEXT']
  };
  const arrayBindings = {
    fills: 'setBoundVariableForPaint', strokes: 'setBoundVariableForPaint', paints: 'setBoundVariableForPaint',
    effects: 'setBoundVariableForEffect', layoutGrids: 'setBoundVariableForLayoutGrid'
  };
  const resourceFields = {
    style: ['id', 'type', 'name', 'description', 'key', 'remote', 'paints', 'effects', 'layoutGrids', 'fontName', 'fontSize', 'lineHeight', 'letterSpacing', 'boundVariables'],
    variable: ['id', 'name', 'description', 'key', 'remote', 'variableCollectionId', 'resolvedType', 'valuesByMode', 'scopes', 'hiddenFromPublishing', 'codeSyntax'],
    collection: ['id', 'name', 'key', 'remote', 'modes', 'defaultModeId', 'variableIds', 'hiddenFromPublishing']
  };
  const object = (value, label) => ctx.assertObject(value, label);
  const id = (value, label) => ctx.assertId(value, label);
  const string = (value, label, empty = false) => {
    if (typeof value !== 'string' || (!empty && !value.trim())) throw new TypeError(`${label} must be a ${empty ? '' : 'nonempty '}string`);
    return value;
  };
  const keys = (value, allowed, label) => {
    object(value, label);
    for (const key of Object.keys(value)) if (!allowed.includes(key)) throw new TypeError(`Unknown ${label} field: ${key}`);
  };
  const method = (target, name) => {
    if (typeof target?.[name] !== 'function') throw new Error(`Native operation unavailable: ${name}`);
    return target[name].bind(target);
  };
  const writable = (target, props, forbidden = []) => {
    object(props, 'props');
    for (const key of Object.keys(props)) {
      if (['id', 'type', 'key', 'remote', 'removed', 'boundVariables', '__proto__', 'constructor', 'prototype', ...forbidden].includes(key)) {
        throw new TypeError(`Cannot assign resource property: ${key}`);
      }
      if (!(key in target) || typeof target[key] === 'function') throw new TypeError(`Unsupported resource property: ${key}`);
      let owner = target, descriptor;
      while (owner && !descriptor) { descriptor = Object.getOwnPropertyDescriptor(owner, key); owner = Object.getPrototypeOf(owner); }
      if (descriptor && (('writable' in descriptor && !descriptor.writable) || (!('writable' in descriptor) && !descriptor.set))) {
        throw new TypeError(`Read-only resource property: ${key}`);
      }
    }
  };
  const propsFor = op => {
    const props = {...(op.props ?? {})};
    object(op.props ?? {}, 'props');
    if (op.name !== undefined) props.name = string(op.name, 'name');
    return props;
  };
  const describe = (target, kind, requested) => {
    ctx.remember(target, kind);
    if (requested !== undefined && (!Array.isArray(requested) || requested.length > 40 || requested.some(field => typeof field !== 'string' || !/^[A-Za-z][A-Za-z0-9]*$/.test(field) || ['constructor', 'prototype'].includes(field)))) {
      throw new TypeError('fields must contain at most 40 direct property names');
    }
    for (const field of requested ?? []) {
      let value;
      try { value = target[field]; } catch { continue; }
      if (typeof value === 'function') throw new TypeError(`Cannot inspect resource method: ${field}`);
    }
    return {kind, ...ctx.fields(target, requested ?? resourceFields[kind])};
  };
  const local = target => { if (target.remote) throw new Error('This resource is remote and cannot be modified locally'); };
  const applyProps = async (target, props, label, forbidden = []) => {
    writable(target, props, forbidden);
    if (target.type === 'TEXT' && Object.keys(props).some(key => !['name', 'description', 'hiddenFromPublishing'].includes(key))) {
      await ctx.text.prepareStyle(target, props);
    }
    for (const [key, value] of Object.entries(props)) {
      await ctx.write(`${label}:${key}`, () => { target[key] = value; });
    }
  };
  const variable = async value => value === null ? null : ctx.entity('variable', id(value, 'variableId'));
  const validateBindings = async (target, bindings) => {
    if (bindings === undefined) return [];
    if (!Array.isArray(bindings)) throw new TypeError('bindings must be an array');
    const result = [], selectors = new Set();
    for (const binding of bindings) {
      keys(binding, ['field', 'variableId', 'index', 'subfield'], 'binding');
      const field = string(binding.field, 'binding.field');
      const selector = JSON.stringify([field, binding.index ?? null, binding.subfield ?? null]);
      if (selectors.has(selector)) throw new TypeError(`Duplicate binding selector: ${selector}`);
      selectors.add(selector);
      if (!Object.hasOwn(binding, 'variableId')) throw new TypeError('binding.variableId is required; use null to unbind');
      const resolved = await variable(binding.variableId);
      if (binding.index === undefined) {
        if (binding.subfield !== undefined) throw new TypeError('binding.subfield requires an array index');
        method(target, 'setBoundVariable');
        result.push({field, variable: resolved});
      } else {
        if (!Object.hasOwn(arrayBindings, field)) throw new TypeError(`Unsupported binding array: ${field}`);
        const index = ctx.integer(binding.index, undefined, Number.MAX_SAFE_INTEGER, 'binding.index');
        const subfield = string(binding.subfield, 'binding.subfield');
        method(ctx.figma.variables, arrayBindings[field]);
        result.push({field, index, subfield, variable: resolved});
      }
    }
    return result;
  };
  const validateApplication = async (target, op) => {
    const result = {entityKind: op.kind === 'style' ? 'style' : 'node', styles: [], bindings: [], modes: []};
    if (op.styles !== undefined) {
      keys(op.styles, Object.keys(styleApplications), 'styles');
      for (const [field, styleId] of Object.entries(op.styles)) {
        string(styleId, `styles.${field}`, true);
        const [setter, expected] = styleApplications[field];
        method(target, setter);
        const style = styleId === '' ? null : await ctx.entity('style', styleId);
        if (style && style.type !== expected) throw new TypeError(`styles.${field} requires a ${expected} style`);
        result.styles.push({field, styleId, setter, style});
      }
    }
    result.bindings = await validateBindings(target, op.bindings);
    const prospective = new Map();
    for (const binding of result.bindings) {
      if (binding.index === undefined) continue;
      if (!prospective.has(binding.field)) {
        let value = op.props && Object.hasOwn(op.props, binding.field) ? op.props[binding.field] : target[binding.field];
        const styleField = {fills: 'fill', strokes: 'stroke', effects: 'effect', layoutGrids: 'grid'}[binding.field];
        const appliedStyle = result.styles.find(item => item.field === styleField && item.style);
        if (appliedStyle) value = appliedStyle.style[{fill: 'paints', stroke: 'paints', effect: 'effects', grid: 'layoutGrids'}[styleField]];
        if (!Array.isArray(value)) throw new TypeError(`${binding.field} must be a concrete array for indexed binding`);
        writable(target, {[binding.field]: value});
        prospective.set(binding.field, value.map(item => ({...item})));
      }
      const array = prospective.get(binding.field);
      if (binding.index >= array.length) throw new RangeError(`Binding index is outside ${binding.field}`);
      array[binding.index] = ctx.figma.variables[arrayBindings[binding.field]](array[binding.index], binding.subfield, binding.variable);
    }
    if (op.modes !== undefined) {
      object(op.modes, 'modes');
      for (const [collectionId, modeId] of Object.entries(op.modes)) {
        const collection = await ctx.entity('collection', id(collectionId, 'collectionId'));
        if (modeId === null) method(target, 'clearExplicitVariableModeForCollection');
        else {
          id(modeId, 'modeId');
          if (!collection.modes.some(mode => mode.modeId === modeId)) throw new Error(`Mode ${modeId} does not belong to collection ${collectionId}`);
          method(target, 'setExplicitVariableModeForCollection');
        }
        result.modes.push({collection, modeId});
      }
    }
    return result;
  };
  const assignArray = async (target, field, value) => {
    const setter = field === 'fills' ? 'setFillsAsync' : field === 'strokes' ? 'setStrokesAsync' : undefined;
    await ctx.write(`binding:${field}`, async () => {
      if (setter && typeof target[setter] === 'function') await target[setter](value);
      else target[field] = value;
    });
  };
  const resolveValue = async (source, consumer, modeOverrides = {}, modeTarget = consumer) => {
    object(modeOverrides, 'mode overrides');
    // Native resolution covers the current scene context, including extensions.
    if (!Object.keys(modeOverrides).length && consumer && 'parent' in consumer && typeof source.resolveForConsumer === 'function') {
      return source.resolveForConsumer(consumer);
    }
    const effective = {...(consumer?.resolvedVariableModes ?? {})};
    for (const [collectionId, modeId] of Object.entries(modeOverrides)) {
      id(collectionId, 'collectionId');
      if (modeId !== null) effective[collectionId] = id(modeId, 'modeId');
      else {
        delete effective[collectionId];
        for (let ancestor = modeTarget?.parent; ancestor; ancestor = ancestor.parent) {
          const inherited = ancestor.explicitVariableModes?.[collectionId];
          if (inherited !== undefined) { effective[collectionId] = inherited; break; }
        }
      }
    }
    const collections = new Map(), stack = new Set();
    const collection = async collectionId => {
      if (!collections.has(collectionId)) collections.set(collectionId, await ctx.entity('collection', collectionId));
      return collections.get(collectionId);
    };
    const descendsFrom = async (candidate, ancestorId) => {
      const seen = new Set();
      for (let current = candidate; current?.isExtension; current = await collection(current.parentVariableCollectionId)) {
        if (seen.has(current.id)) throw new Error('Variable collection inheritance cycle');
        seen.add(current.id);
        if (current.parentVariableCollectionId === ancestorId) return true;
      }
      return false;
    };
    const visit = async variable => {
      let owner = await collection(variable.variableCollectionId);
      const extensions = [];
      for (const collectionId of Object.keys(effective)) {
        if (collectionId === owner.id) continue;
        const candidate = await collection(collectionId);
        if (candidate.isExtension && candidate.variableIds.includes(variable.id)) extensions.push(candidate);
      }
      for (const candidate of extensions) {
        if (owner.id === variable.variableCollectionId || await descendsFrom(candidate, owner.id)) owner = candidate;
        else if (!await descendsFrom(owner, candidate.id)) throw new Error(`Ambiguous active extensions for variable ${variable.id}`);
      }
      const modeId = effective[owner.id] ?? owner.defaultModeId;
      if (!owner.modes.some(mode => mode.modeId === modeId)) throw new Error(`Mode ${modeId} does not belong to collection ${owner.id}`);
      const key = `${variable.id}:${owner.id}:${modeId}`;
      if (stack.has(key)) throw new Error(`Variable alias cycle at ${variable.id}`);
      stack.add(key);
      const values = owner.id === variable.variableCollectionId ? variable.valuesByMode
        : await method(variable, 'valuesByModeForCollectionAsync')(owner);
      if (!Object.hasOwn(values, modeId)) throw new Error(`Variable ${variable.id} has no value for mode ${modeId}`);
      const value = values[modeId];
      let resolved;
      if (value && typeof value === 'object' && value.type === 'VARIABLE_ALIAS') {
        const referenced = await ctx.entity('variable', id(value.id, 'alias.id'));
        if (referenced.resolvedType !== variable.resolvedType) throw new TypeError('Variable alias type must match its source');
        resolved = await visit(referenced);
      } else resolved = {value, resolvedType: variable.resolvedType};
      stack.delete(key);
      return resolved;
    };
    return visit(source);
  };
  const apply = async (target, op, prepared) => {
    const plan = prepared ?? await validateApplication(target, op);
    if (plan.styles.length || plan.bindings.length || plan.modes.length) await ctx.text.prepareBindings(target, plan);
    if (plan.styles.length || plan.bindings.length || plan.modes.length) ctx.trackAffected(target, plan.entityKind);
    for (const item of plan.styles) {
      if (item.field === 'text' && item.style) await ctx.text.prepareStyle(item.style);
      await ctx.write(`style:${item.field}`, () => target[item.setter](item.styleId));
    }
    const arrays = new Map();
    for (const binding of plan.bindings) {
      if (binding.index === undefined) {
        await ctx.write(`binding:${binding.field}`, () => target.setBoundVariable(binding.field, binding.variable));
      } else {
        if (!arrays.has(binding.field)) {
          const value = target[binding.field];
          if (!Array.isArray(value)) throw new TypeError(`${binding.field} must be a concrete array for indexed binding`);
          arrays.set(binding.field, value.map(item => ({...item})));
        }
        const array = arrays.get(binding.field);
        if (binding.index >= array.length) throw new RangeError(`Binding index is outside ${binding.field}`);
        array[binding.index] = ctx.figma.variables[arrayBindings[binding.field]](array[binding.index], binding.subfield, binding.variable);
      }
    }
    for (const [field, value] of arrays) await assignArray(target, field, value);
    for (const {collection, modeId} of plan.modes) {
      await ctx.write(`mode:${collection.id}`, () => modeId === null
        ? target.clearExplicitVariableModeForCollection(collection)
        : target.setExplicitVariableModeForCollection(collection, modeId));
    }
  };
  const prepareValues = async (collection, values, resolvedType) => {
    if (values === undefined) return [];
    object(values, 'valuesByMode');
    const result = [];
    for (const [modeId, value] of Object.entries(values)) {
      if (!collection.modes.some(mode => mode.modeId === modeId)) throw new Error(`Mode ${modeId} does not belong to collection ${collection.id}`);
      if (value && typeof value === 'object' && value.type === 'VARIABLE_ALIAS') {
        keys(value, ['type', 'id'], 'variable alias');
        const alias = await ctx.entity('variable', id(value.id, 'alias.id'));
        if (alias.resolvedType !== resolvedType) throw new TypeError('Variable alias type must match the target variable type');
        result.push([modeId, {type: 'VARIABLE_ALIAS', id: alias.id}]);
      } else result.push([modeId, value]);
    }
    return result;
  };
  const prepareCode = code => {
    if (code === undefined) return [];
    keys(code, ['WEB', 'ANDROID', 'iOS'], 'codeSyntax');
    return Object.entries(code).map(([platform, value]) => {
      if (value !== null) string(value, `codeSyntax.${platform}`, true);
      return [platform, value];
    });
  };
  const configureVariable = async (target, op, values, code) => {
    if (values.length) method(target, 'setValueForMode');
    for (const [, value] of code) method(target, value === null ? 'removeVariableCodeSyntax' : 'setVariableCodeSyntax');
    ctx.trackAffected(target, 'variable');
    await applyProps(target, propsFor(op), 'variable', ['variableCollectionId', 'resolvedType', 'valuesByMode', 'codeSyntax']);
    for (const [modeId, value] of values) await ctx.write(`variable:value:${modeId}`, () => target.setValueForMode(modeId, value));
    for (const [platform, value] of code) await ctx.write(`variable:code:${platform}`, () => value === null ? target.removeVariableCodeSyntax(platform) : target.setVariableCodeSyntax(platform, value));
    return describe(target, 'variable');
  };
  const createStyle = async op => {
    if (!Object.hasOwn(styleFactories, op.styleType)) throw new TypeError('styleType must be PAINT, TEXT, EFFECT, or GRID');
    const create = method(ctx.figma, styleFactories[op.styleType]);
    const props = propsFor(op);
    const target = await ctx.write('style:create', () => ctx.trackCreated(create(), 'style'));
    await applyProps(target, props, 'style');
    await apply(target, {kind: 'style', bindings: op.bindings});
    return describe(target, 'style');
  };
  const updateStyle = async op => {
    const target = await ctx.entity('style', id(op.id, 'id'));
    local(target);
    const props = propsFor(op);
    writable(target, props);
    const plan = await validateApplication(target, {kind: 'style', props, bindings: op.bindings});
    ctx.trackAffected(target, 'style');
    await applyProps(target, props, 'style');
    await apply(target, {kind: 'style', bindings: op.bindings}, plan);
    return describe(target, 'style');
  };
  const removeResource = async op => {
    const target = await ctx.entity(op.kind, id(op.id, 'id'));
    local(target);
    const remove = method(target, 'remove');
    ctx.trackAffected(target, op.kind);
    const result = {kind: op.kind, removedId: target.id};
    if (op.kind === 'collection') {
      result.removedVariableIds = [...target.variableIds];
      result.removedModeIds = target.modes.map(mode => mode.modeId);
      for (const variableId of result.removedVariableIds) ctx.trackAffected({id: variableId}, 'variable');
      for (const modeId of result.removedModeIds) ctx.trackAffected({id: modeId, collectionId: target.id}, 'mode');
    }
    await ctx.write(`${op.kind}:remove`, remove);
    return result;
  };
  const importResource = async op => {
    const key = id(op.key, 'key');
    const owner = op.kind === 'style' ? ctx.figma : ctx.figma.variables;
    const name = op.kind === 'style' ? 'importStyleByKeyAsync' : 'importVariableByKeyAsync';
    const target = await ctx.write(`${op.kind}:import`, () => method(owner, name)(key));
    ctx.remember(target, op.kind);
    ctx.trackAffected(target, op.kind);
    return {...describe(target, op.kind), imported: true};
  };
  const createCollection = async op => {
    const name = string(op.name, 'name');
    const props = op.props ?? {};
    object(props, 'props');
    const target = await ctx.write('collection:create', () => {
      const created = ctx.trackCreated(method(ctx.figma.variables, 'createVariableCollection')(name), 'collection');
      for (const mode of created.modes) ctx.trackCreated({id: mode.modeId, collectionId: created.id, name: mode.name}, 'mode');
      return created;
    });
    await applyProps(target, props, 'collection', ['modes', 'variableIds', 'defaultModeId', 'isExtension']);
    return describe(target, 'collection');
  };
  const updateCollection = async op => {
    const target = await ctx.entity('collection', id(op.id, 'id'));
    local(target);
    writable(target, propsFor(op), ['modes', 'variableIds', 'defaultModeId', 'isExtension']);
    ctx.trackAffected(target, 'collection');
    await applyProps(target, propsFor(op), 'collection', ['modes', 'variableIds', 'defaultModeId', 'isExtension']);
    return describe(target, 'collection');
  };
  const createVariable = async op => {
    const name = string(op.name, 'name');
    if (!['BOOLEAN', 'FLOAT', 'STRING', 'COLOR'].includes(op.resolvedType)) throw new TypeError('Invalid variable resolvedType');
    const collection = await ctx.entity('collection', id(op.collectionId, 'collectionId'));
    local(collection);
    ctx.trackAffected(collection, 'collection');
    const values = await prepareValues(collection, op.valuesByMode, op.resolvedType), code = prepareCode(op.codeSyntax);
    object(op.props ?? {}, 'props');
    const target = await ctx.write('variable:create', () => ctx.trackCreated(method(ctx.figma.variables, 'createVariable')(name, collection, op.resolvedType), 'variable'));
    return configureVariable(target, {...op, name: undefined}, values, code);
  };
  const updateVariable = async op => {
    const target = await ctx.entity('variable', id(op.id, 'id'));
    local(target);
    const collection = await ctx.entity('collection', target.variableCollectionId);
    const values = await prepareValues(collection, op.valuesByMode, target.resolvedType), code = prepareCode(op.codeSyntax);
    writable(target, propsFor(op), ['variableCollectionId', 'resolvedType', 'valuesByMode', 'codeSyntax']);
    return configureVariable(target, op, values, code);
  };
  const changeMode = async op => {
    const collection = await ctx.entity('collection', id(op.collectionId, 'collectionId'));
    local(collection);
    if (op.action === 'create') {
      const name = string(op.name, 'name');
      method(collection, 'addMode');
      ctx.trackAffected(collection, 'collection');
      const mode = await ctx.write('mode:create', () => {
        const modeId = method(collection, 'addMode')(name);
        return ctx.trackCreated({id: modeId, collectionId: collection.id, name}, 'mode');
      });
      return {kind: 'mode', id: mode.id, collectionId: collection.id, name: mode.name};
    }
    const modeId = id(op.id, 'id');
    if (!collection.modes.some(mode => mode.modeId === modeId)) throw new Error(`Mode ${modeId} does not belong to collection ${collection.id}`);
    if (op.action === 'update') {
      const name = string(op.name, 'name');
      method(collection, 'renameMode');
      ctx.trackAffected(collection, 'collection');
      await ctx.write('mode:rename', () => method(collection, 'renameMode')(modeId, name));
      return {kind: 'mode', id: modeId, collectionId: collection.id, name};
    }
    method(collection, 'removeMode');
    ctx.trackAffected(collection, 'collection');
    await ctx.write('mode:remove', () => method(collection, 'removeMode')(modeId));
    return {kind: 'mode', removedId: modeId, collectionId: collection.id};
  };
  const imageInfo = async image => {
    ctx.remember(image, 'image');
    return {kind: 'image', hash: image.hash, ...await method(image, 'getSizeAsync')()};
  };
  const importImage = async op => {
    keys(op.source, ['base64', 'url'], 'source');
    const hasBytes = Object.hasOwn(op.source, 'base64'), hasURL = Object.hasOwn(op.source, 'url');
    if (hasBytes === hasURL) throw new TypeError('source requires exactly one of base64 or url');
    let image;
    if (hasBytes) {
      const base64 = string(op.source.base64, 'source.base64');
      if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(base64)) throw new TypeError('source.base64 must be standard base64 data');
      const bytes = method(ctx.figma, 'base64Decode')(base64);
      image = await ctx.write('image:import', () => method(ctx.figma, 'createImage')(bytes));
    } else {
      const url = string(op.source.url, 'source.url');
      let parsed;
      try { parsed = new URL(url); } catch { throw new TypeError('source.url must be an absolute HTTP or HTTPS URL'); }
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new TypeError('source.url must use HTTP or HTTPS');
      image = await ctx.write('image:import', () => method(ctx.figma, 'createImageAsync')(url));
    }
    ctx.trackAffected(image, 'image');
    return {...await imageInfo(image), imported: true};
  };
  const filterItems = (items, filter = {}) => {
    keys(filter, ['name', 'styleType', 'resolvedType', 'collectionId', 'remote'], 'filter');
    if (filter.name !== undefined) string(filter.name, 'filter.name', true);
    if (filter.styleType !== undefined && !Object.hasOwn(styleFactories, filter.styleType)) throw new TypeError('Invalid filter.styleType');
    if (filter.resolvedType !== undefined && !['BOOLEAN', 'FLOAT', 'STRING', 'COLOR'].includes(filter.resolvedType)) throw new TypeError('Invalid filter.resolvedType');
    if (filter.collectionId !== undefined) id(filter.collectionId, 'filter.collectionId');
    if (filter.remote !== undefined && typeof filter.remote !== 'boolean') throw new TypeError('filter.remote must be boolean');
    return items.filter(item => Object.entries(filter).every(([key, value]) => {
      if (key === 'name') return String(item.name ?? '').toLowerCase().includes(value.toLowerCase());
      if (key === 'styleType') return item.type === value;
      if (key === 'collectionId') return item.variableCollectionId === value;
      return item[key] === value;
    }));
  };
  const page = (items, query, transform = item => item) => {
    const offset = ctx.integer(query.offset, 0, Number.MAX_SAFE_INTEGER, 'offset');
    const limit = ctx.integer(query.limit, 100, 100, 'limit', 1);
    const selected = items.slice(offset, offset + limit);
    return {items: selected.map(transform), total: items.length, offset, limit, nextOffset: offset + selected.length < items.length ? offset + selected.length : null};
  };
  const idsFor = query => {
    if (query.id !== undefined && query.ids !== undefined) throw new TypeError('Use id or ids, not both');
    const ids = query.id === undefined ? query.ids : [query.id];
    if (ids !== undefined && (!Array.isArray(ids) || ids.some(value => typeof value !== 'string' || !value.trim()))) throw new TypeError('ids must be an array of nonempty IDs');
    return ids;
  };
  const queryStyles = async query => {
    const ids = idsFor(query);
    if (query.styleType !== undefined && !Object.hasOwn(styleLists, query.styleType)) throw new TypeError('Invalid styleType');
    let items;
    if (ids) items = await Promise.all(ids.map(value => ctx.entity('style', value)));
    else {
      const types = query.styleType === undefined ? Object.keys(styleLists) : [query.styleType];
      if (types.some(type => !Object.hasOwn(styleLists, type))) throw new TypeError('Invalid styleType');
      items = (await Promise.all(types.map(type => method(ctx.figma, styleLists[type])()))).flat();
    }
    if (query.styleType !== undefined) items = items.filter(item => item.type === query.styleType);
    return page(filterItems(items, query.filter), query, item => describe(item, 'style', query.fields));
  };
  const queryVariables = async query => {
    const ids = idsFor(query);
    if (query.resolvedType !== undefined && !['BOOLEAN', 'FLOAT', 'STRING', 'COLOR'].includes(query.resolvedType)) throw new TypeError('Invalid resolvedType');
    let items = ids ? await Promise.all(ids.map(value => ctx.entity('variable', value))) : await method(ctx.figma.variables, 'getLocalVariablesAsync')(query.resolvedType);
    if (query.resolvedType !== undefined) items = items.filter(item => item.resolvedType === query.resolvedType);
    if (query.collectionId !== undefined) items = items.filter(item => item.variableCollectionId === query.collectionId);
    return page(filterItems(items, query.filter), query, item => describe(item, 'variable', query.fields));
  };
  const queryCollections = async query => {
    const ids = idsFor(query);
    const items = ids ? await Promise.all(ids.map(value => ctx.entity('collection', value))) : await method(ctx.figma.variables, 'getLocalVariableCollectionsAsync')();
    return page(filterItems(items, query.filter), query, item => describe(item, 'collection', query.fields));
  };
  const queryModes = async query => {
    const collection = await ctx.entity('collection', id(query.collectionId, 'collectionId'));
    const items = collection.modes.map(mode => ({kind: 'mode', id: mode.modeId, collectionId: collection.id, name: mode.name}));
    return page(filterItems(items, query.filter), query);
  };
  const queryImages = async query => {
    if (query.hash !== undefined && query.hashes !== undefined) throw new TypeError('Use hash or hashes, not both');
    const hashes = query.hash === undefined ? query.hashes : [query.hash];
    if (!Array.isArray(hashes) || hashes.some(hash => typeof hash !== 'string' || !hash)) throw new TypeError('images query requires hash or hashes');
    const result = page(hashes, query);
    result.items = await Promise.all(result.items.map(async hash => imageInfo(await ctx.entity('image', hash))));
    return result;
  };
  const queryLibraries = async query => {
    const library = ctx.figma.teamLibrary;
    const items = query.collectionKey === undefined
      ? await method(library, 'getAvailableLibraryVariableCollectionsAsync')()
      : await method(library, 'getVariablesInLibraryCollectionAsync')(id(query.collectionKey, 'collectionKey'));
    return {resourceType: query.collectionKey === undefined ? 'variableCollections' : 'variables', ...page(filterItems(items, query.filter), query, item => ctx.serialize(item))};
  };
  const edit = (kind, action, required, optional, execute, requires = [], targetMethods = []) => ({kind, action, required, optional, execute, requires, targetMethods});
  const query = (kind, required, optional, execute, requires = []) => ({kind, required, optional, execute, requires});
  return {
    edits: [
      edit('style', 'create', ['styleType'], ['name', 'props', 'bindings'], createStyle),
      edit('style', 'update', ['id'], ['name', 'props', 'bindings'], updateStyle),
      edit('style', 'remove', ['id'], [], removeResource, [], ['remove']),
      edit('style', 'import', ['key'], [], importResource, ['importStyleByKeyAsync']),
      edit('collection', 'create', ['name'], ['props'], createCollection, ['variables.createVariableCollection']),
      edit('collection', 'update', ['id'], ['name', 'props'], updateCollection),
      edit('collection', 'remove', ['id'], [], removeResource, [], ['remove']),
      edit('variable', 'create', ['collectionId', 'name', 'resolvedType'], ['props', 'valuesByMode', 'codeSyntax'], createVariable, ['variables.createVariable']),
      edit('variable', 'update', ['id'], ['name', 'props', 'valuesByMode', 'codeSyntax'], updateVariable),
      edit('variable', 'remove', ['id'], [], removeResource, [], ['remove']),
      edit('variable', 'import', ['key'], [], importResource, ['variables.importVariableByKeyAsync']),
      edit('mode', 'create', ['collectionId', 'name'], [], changeMode, [], ['addMode']),
      edit('mode', 'update', ['collectionId', 'id', 'name'], [], changeMode, [], ['renameMode']),
      edit('mode', 'remove', ['collectionId', 'id'], [], changeMode, [], ['removeMode']),
      edit('image', 'import', ['source'], [], importImage)
    ],
    queries: [
      query('styles', [], ['id', 'ids', 'styleType', 'filter', 'fields', 'offset', 'limit'], queryStyles),
      query('variables', [], ['id', 'ids', 'collectionId', 'resolvedType', 'filter', 'fields', 'offset', 'limit'], queryVariables),
      query('collections', [], ['id', 'ids', 'filter', 'fields', 'offset', 'limit'], queryCollections),
      query('modes', ['collectionId'], ['filter', 'offset', 'limit'], queryModes),
      query('images', [], ['hash', 'hashes', 'offset', 'limit'], queryImages, ['getImageByHash']),
      query('libraries', [], ['collectionKey', 'filter', 'offset', 'limit'], queryLibraries)
    ],
    validateApplication,
    apply,
    resolveValue,
    describe
  };
}
