/* Bounded observations and focused continuation, without caller predicates. */
export function createInspectionOperations(ctx) {
  const defaults = ['name', 'parentId', 'x', 'y', 'width', 'height', 'visible', 'locked', 'opacity', 'layoutMode', 'characters', 'fontName'];
  const forbidden = new Set(['__proto__', 'constructor', 'prototype']);
  const names = fields => {
    const value = fields ?? defaults;
    if (!Array.isArray(value) || value.length > 40 || value.some(name => typeof name !== 'string' || !/^[A-Za-z][A-Za-z0-9]*$/.test(name) || forbidden.has(name) || name === 'children')) throw new TypeError('fields must contain at most 40 direct property names; children uses hierarchy inspection');
    return [...new Set(value)];
  };
  const hierarchy = async input => {
    const fields = names(input.fields), depth = ctx.integer(input.depth, 1, 20, 'depth');
    const limit = ctx.integer(input.limit, 100, 1000, 'limit', 1);
    const ids = input.ids ?? [ctx.figma.currentPage.id];
    if (!Array.isArray(ids) || !ids.length || ids.length > limit) throw new TypeError('ids must be a nonempty array within the node limit');
    let visited = 0;
    const unvisited = [], roots = [];
    const visit = async (target, remaining) => {
      visited++;
      await ctx.loadPage(target);
      const result = ctx.fields(target, fields);
      let children;
      try { children = ctx.children(target); }
      catch (error) { unvisited.push({parentId: target.id, reason: 'children-error', message: String(error.message ?? error)}); return result; }
      if (!children.length) return result;
      result.childCount = children.length;
      const stop = (index, reason) => unvisited.push({parentId: target.id, reason, nextChildIndex: index, nextChildId: children[index].id,
        remainingChildren: children.length - index, continuation: {kind: 'children', id: target.id, offset: index, depth: Math.max(0, remaining - 1), fields, limit}});
      if (!remaining) { stop(0, 'depth'); return result; }
      result.children = [];
      for (let index = 0; index < children.length; index++) {
        if (visited >= limit) { stop(index, 'limit'); break; }
        ctx.remember(children[index]);
        result.children.push(await visit(children[index], remaining - 1));
      }
      return result;
    };
    for (let index = 0; index < ids.length; index++) {
      if (visited >= limit) { unvisited.push({reason: 'roots-limit', ids: ids.slice(index), continuation: {kind: 'nodes', ids: ids.slice(index), depth, limit, fields}}); break; }
      roots.push(await visit(await ctx.node(ids[index]), depth));
    }
    return {roots, visited, depth, limit, truncated: unvisited.length > 0, unvisited};
  };
  const children = async input => {
    const target = await ctx.node(input.id);
    await ctx.loadPage(target);
    const list = ctx.children(target);
    const offset = ctx.integer(input.offset, 0, Number.MAX_SAFE_INTEGER, 'offset');
    const limit = ctx.integer(input.limit, 100, 1000, 'limit', 1);
    const chosen = list.slice(offset, offset + limit).map(child => child.id);
    const result = chosen.length ? await hierarchy({...input, ids: chosen, id: undefined, offset: undefined, depth: input.depth ?? 0, limit})
      : {roots: [], visited: 0, depth: ctx.integer(input.depth, 0, 20, 'depth'), limit, truncated: false, unvisited: []};
    const consumed = result.roots.length, nextOffset = offset + consumed < list.length ? offset + consumed : null;
    return {...result, truncated: result.truncated || nextOffset !== null, parentId: target.id, offset, total: list.length, nextOffset,
      continuation: nextOffset === null ? null : {kind: 'children', id: target.id, offset: nextOffset, fields: names(input.fields), depth: input.depth ?? 0, limit}};
  };
  const property = async input => {
    const kind = input.entityKind ?? 'node', target = await ctx.entity(kind, input.id);
    if (!Array.isArray(input.path) || !input.path.length || input.path.length > 50 || input.path.some(part =>
      !(typeof part === 'string' && part.length && !forbidden.has(part)) && !(Number.isInteger(part) && part >= 0))) throw new TypeError('path must contain property names or nonnegative indices');
    let value = target;
    for (const part of input.path) {
      if (value === null || value === undefined || typeof value === 'function') throw new TypeError('Property path is not readable data');
      await ctx.loadPage(value);
      value = value[part];
    }
    if (typeof value === 'function') throw new TypeError('Inspection cannot call methods');
    const offset = ctx.integer(input.offset, 0, Number.MAX_SAFE_INTEGER, 'offset');
    const string = typeof value === 'string', array = Array.isArray(value);
    const limit = ctx.integer(input.limit, string ? 4000 : 100, string ? 4000 : 100, 'limit', 1);
    let data, total, valueKind;
    if (string) { total = value.length; data = value.slice(offset, offset + limit); valueKind = 'string'; }
    else if (array) {
      total = value.length; valueKind = 'array'; data = [];
      for (let index = offset; index < Math.min(total, offset + limit); index++) data.push(ctx.serialize(value[index], {id: input.id, entityKind: kind, path: [...input.path, index]}));
    } else if (value && typeof value === 'object' && [Object.prototype, null].includes(Object.getPrototypeOf(value))) {
      const keys = Object.keys(value); total = keys.length; valueKind = 'object'; data = Object.create(null);
      for (const key of keys.slice(offset, offset + limit)) data[key] = ctx.serialize(value[key], {id: input.id, entityKind: kind, path: [...input.path, key]});
    } else { total = 1; valueKind = 'scalar'; data = ctx.serialize(value, {id: input.id, entityKind: kind, path: input.path}); }
    const nextOffset = valueKind !== 'scalar' && offset + limit < total ? offset + limit : null;
    return {id: input.id, entityKind: kind, path: input.path, valueKind, offset, total, value: data, nextOffset,
      continuation: nextOffset === null ? null : {kind: 'property', id: input.id, entityKind: kind, path: input.path, offset: nextOffset, limit}};
  };
  const fonts = async input => {
    const available = await ctx.figma.listAvailableFontsAsync(), filter = input.filter ?? {};
    if (typeof filter !== 'string') {
      ctx.assertObject(filter, 'font filter');
      for (const key of Object.keys(filter)) if (!['family', 'style'].includes(key) || typeof filter[key] !== 'string') throw new TypeError('Font filter supports family/style strings');
    }
    const matches = (value, query) => !query || value.toLocaleLowerCase().includes(query.toLocaleLowerCase());
    const selected = available.map(item => item.fontName).filter(font => typeof filter === 'string'
      ? matches(`${font.family} ${font.style}`, filter) : matches(font.family, filter.family) && matches(font.style ?? '', filter.style));
    const offset = ctx.integer(input.offset, 0, Number.MAX_SAFE_INTEGER, 'offset'), limit = ctx.integer(input.limit, 100, 100, 'limit', 1);
    return {fonts: ctx.serialize(selected.slice(offset, offset + limit)), total: selected.length, offset, limit,
      nextOffset: offset + limit < selected.length ? offset + limit : null};
  };
  const pages = input => {
    const items = ctx.figma.root.children;
    const offset = ctx.integer(input.offset, 0, Number.MAX_SAFE_INTEGER, 'offset');
    const limit = ctx.integer(input.limit, 100, 100, 'limit', 1);
    return {items: items.slice(offset, offset + limit).map(page => ctx.fields(ctx.remember(page), ['name'])),
      offset, limit, total: items.length, nextOffset: offset + limit < items.length ? offset + limit : null};
  };
  return {edits: [], queries: [
    {kind: 'nodes', required: [], optional: ['ids', 'fields', 'depth', 'limit'], execute: hierarchy},
    {kind: 'children', required: ['id'], optional: ['offset', 'limit', 'fields', 'depth'], execute: children},
    {kind: 'property', required: ['id', 'path'], optional: ['entityKind', 'offset', 'limit'], execute: property},
    {kind: 'fonts', required: [], optional: ['filter', 'offset', 'limit'], requires: ['listAvailableFontsAsync'], execute: fonts},
    {kind: 'fontAxes', required: ['family'], optional: [], requires: ['getFontFamilyVariationAxes'], execute: input => ctx.serialize(ctx.figma.getFontFamilyVariationAxes(input.family))},
    {kind: 'pages', required: [], optional: ['offset', 'limit'], execute: pages},
    {kind: 'capabilities', required: [], optional: [], execute: () => ctx.catalog()}
  ]};
}
