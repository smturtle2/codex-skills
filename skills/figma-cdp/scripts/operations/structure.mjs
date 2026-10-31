/** Native scene-graph operations. The factory is serialized into the browser. */
export function createStructureOperations(ctx) {
  const message = error => String(error?.message ?? error);
  const object = (value, label) => ctx.assertObject(value, label);
  const scene = target => {
    if (!target || ['DOCUMENT', 'PAGE'].includes(target.type) || typeof target.remove !== 'function') {
      throw new TypeError('A scene node is required');
    }
    return target;
  };
  const pageOf = target => {
    for (let current = target; current; current = current.parent) {
      if (current.type === 'PAGE') return current;
    }
    return null;
  };
  const indexValue = (index, parent) => {
    if (index === undefined) return undefined;
    return ctx.integer(index, undefined, ctx.children(parent).length, 'index');
  };
  const parentContainer = parent => {
    if (!parent || parent.removed || parent.type === 'DOCUMENT' || typeof parent.appendChild !== 'function') {
      throw new TypeError('The destination must contain scene nodes');
    }
    return parent;
  };
  const checkParent = (parent, index, type) => {
    parentContainer(parent);
    if (index !== undefined && typeof parent.insertChild !== 'function') {
      throw new TypeError('The destination cannot insert scene nodes');
    }
    indexValue(index, parent);
    if (parent.type === 'COMPONENT_SET' && type !== undefined && type !== 'COMPONENT') {
      throw new Error('A component set can contain only components');
    }
    return parent;
  };
  const parentReady = async (parent, index, type) => {
    parentContainer(parent);
    await ctx.loadPage(parent);
    return checkParent(parent, index, type);
  };
  const checkPreparedPlacement = (target, parent, index) => {
    scene(target);
    checkParent(parent, index, target.type);
    for (let ancestor = parent; ancestor; ancestor = ancestor.parent) {
      if (ancestor.id === target.id) throw new Error('Placement would create a hierarchy cycle');
    }
    return parent;
  };
  const checkPlacement = async (target, parent, index) => {
    scene(target);
    await parentReady(parent, index, target.type);
    return checkPreparedPlacement(target, parent, index);
  };
  const placePrepared = (target, parent, index, label) => ctx.writeSync(label, () => {
    checkPreparedPlacement(target, parent, index);
    const previousParent = target.parent;
    ctx.trackAffected(target);
    if (previousParent) ctx.trackAffected(previousParent);
    ctx.trackAffected(parent);
    if (index === undefined) parent.appendChild(target);
    else parent.insertChild(index, target);
    return target;
  });
  const place = async (target, parent, index, label = 'place') => {
    await checkPlacement(target, parent, index);
    return placePrepared(target, parent, index, label);
  };
  const createPlaced = async (factory, parent, index, {type, createLabel = 'create', placeLabel = 'attach'} = {}) => {
    await parentReady(parent, index, type);
    const target = ctx.writeSync(createLabel, () => {
      const created = ctx.trackCreated(factory());
      if (created.parent) ctx.trackAffected(created.parent);
      return created;
    });
    return placePrepared(target, parent, index, placeLabel);
  };
  const mappingOptions = value => {
    const options = value === undefined ? {} : object(value, 'mapping');
    for (const key of Object.keys(options)) {
      if (!['depth', 'limit'].includes(key)) throw new TypeError(`Unknown mapping option: ${key}`);
    }
    return {
      depth: ctx.integer(options.depth, 20, 50, 'mapping.depth'),
      limit: ctx.integer(options.limit, 500, 2000, 'mapping.limit', 1)
    };
  };
  const correspondence = (source, clone, settings) => {
    const options = mappingOptions(settings);
    const pairs = [], transformed = [], unresolved = [];
    let visited = 0;
    const visit = (from, to, depth) => {
      visited++;
      ctx.remember(from); ctx.remember(to);
      const pair = {sourceId: from.id, cloneId: to.id};
      if (from.type !== to.type) {
        transformed.push({...pair, sourceType: from.type, cloneType: to.type});
        return;
      }
      pairs.push(pair);
      let a, b;
      try { a = ctx.children(from); b = ctx.children(to); }
      catch (error) {
        unresolved.push({...pair, reason: 'children-error', message: message(error)});
        return;
      }
      if (a.length !== b.length) {
        unresolved.push({...pair, reason: 'child-count', sourceChildCount: a.length, cloneChildCount: b.length});
        return;
      }
      if (!a.length) return;
      const stop = (index, reason) => unresolved.push({...pair, reason, nextChildIndex: index,
        nextSourceId: a[index].id, nextCloneId: b[index].id, remainingChildren: a.length - index});
      if (depth === 0) { stop(0, 'depth'); return; }
      for (let index = 0; index < a.length; index++) {
        if (visited >= options.limit) { stop(index, 'limit'); break; }
        visit(a[index], b[index], depth - 1);
      }
    };
    visit(source, clone, options.depth);
    return {pairs, transformed, unresolved, visited, complete: !transformed.length && !unresolved.length};
  };
  const transform = (value, label) => {
    if (!Array.isArray(value) || value.length !== 2 || value.some(row =>
      !Array.isArray(row) || row.length !== 3 || row.some(number => typeof number !== 'number' || !Number.isFinite(number)))) {
      throw new TypeError(`${label} must be a finite 2 by 3 transform`);
    }
    return value.map(row => [...row]);
  };
  const absoluteTransform = target => target.type === 'PAGE' ? [[1, 0, 0], [0, 1, 0]]
    : transform(target.absoluteTransform, 'absoluteTransform');
  const inverse = matrix => {
    const [[a, c, e], [b, d, f]] = matrix;
    const determinant = a * d - b * c;
    if (!Number.isFinite(determinant) || determinant === 0) throw new Error('Destination transform is not invertible');
    return transform([[d / determinant, -c / determinant, (c * f - d * e) / determinant],
      [-b / determinant, a / determinant, (b * e - a * f) / determinant]], 'inverse transform');
  };
  const multiply = (a, b) => transform([
    [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1],
      a[0][0] * b[0][2] + a[0][1] * b[1][2] + a[0][2]],
    [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1],
      a[1][0] * b[0][2] + a[1][1] * b[1][2] + a[1][2]]
  ], 'relative transform');
  const selection = () => {
    try { return ctx.figma.currentPage.selection.map(target => target.id); }
    catch { return null; }
  };
  const viewChange = before => {
    const after = selection();
    return before !== null && after !== null && (before.length !== after.length || before.some((id, index) => id !== after[index]))
      ? {selection: after} : undefined;
  };
  const attachViewChange = (value, before) => {
    const view = viewChange(before);
    return view ? {...value, view} : value;
  };
  const resolveMembers = async (ids, parent, index) => {
    if (!Array.isArray(ids) || !ids.length) throw new TypeError('ids must contain at least one scene node ID');
    ids.forEach(id => ctx.assertId(id, 'ids item'));
    if (new Set(ids).size !== ids.length) throw new TypeError('ids must not contain duplicates');
    const members = [];
    for (const id of ids) members.push(scene(await ctx.node(id)));
    await parentReady(parent, index);
    const parentPage = pageOf(parent);
    const memberIds = new Set(ids);
    for (const member of members) {
      await checkPlacement(member, parent, index);
      if (!parentPage || pageOf(member)?.id !== parentPage.id) {
        throw new Error('Members and destination must be on the same page');
      }
      for (let ancestor = member.parent; ancestor; ancestor = ancestor.parent) {
        if (memberIds.has(ancestor.id)) throw new Error('Members cannot include both an ancestor and its descendant');
      }
    }
    return members;
  };
  const markMembers = (members, parent) => {
    ctx.trackAffected(parent);
    for (const member of members) {
      ctx.trackAffected(member);
      if (member.parent) ctx.trackAffected(member.parent);
    }
  };
  const duplicate = async op => {
    const source = scene(await ctx.node(op.id));
    if (typeof source.clone !== 'function') throw new TypeError('The node cannot be cloned');
    const props = op.props === undefined ? {} : object(op.props, 'props');
    ctx.nodes.validateProps(source, props);
    const mapping = mappingOptions(op.mapping);
    const parent = op.parentId === undefined ? source.parent : await ctx.node(op.parentId);
    const clone = await createPlaced(() => source.clone(), parent, op.index,
      {type: source.type, createLabel: 'clone', placeLabel: 'place clone'});
    const mappingResult = correspondence(source, clone, mapping);
    await ctx.nodes.apply(clone, props);
    return {root: ctx.brief(clone), correspondence: mappingResult};
  };
  const move = async op => {
    const target = scene(await ctx.node(op.id));
    const parent = await ctx.node(op.parentId);
    await checkPlacement(target, parent, op.index);
    const props = op.props === undefined ? {} : object(op.props, 'props');
    ctx.nodes.validateProps(target, props);
    const coordinates = op.coordinates === undefined ? 'local' : op.coordinates;
    if (!['local', 'absolute'].includes(coordinates)) throw new TypeError('coordinates must be local or absolute');
    let original;
    if (coordinates === 'absolute') {
      if (['x', 'y', 'rotation', 'relativeTransform'].some(key => Object.hasOwn(props, key))) {
        throw new TypeError('Absolute preservation cannot be combined with position or rotation overrides');
      }
      const layout = 'layoutMode' in parent && parent.layoutMode !== 'NONE';
      const positioning = props.layoutPositioning ?? target.layoutPositioning;
      if (layout && positioning !== 'ABSOLUTE') {
        throw new Error('Absolute preservation in auto layout requires layoutPositioning: ABSOLUTE');
      }
      if (layout && positioning === 'ABSOLUTE' && !('layoutPositioning' in target)) {
        throw new Error('The node cannot use absolute layout positioning');
      }
      original = absoluteTransform(target);
      inverse(absoluteTransform(parent));
    }
    const before = selection();
    await place(target, parent, op.index, 'move');
    await ctx.nodes.apply(target, props);
    if (original) {
      const relative = multiply(inverse(absoluteTransform(parent)), original);
      await ctx.write('preserve absolute transform', () => { target.relativeTransform = relative; });
    }
    return attachViewChange({root: ctx.brief(target), coordinates}, before);
  };
  const remove = async op => {
    const target = scene(await ctx.node(op.id));
    const id = target.id;
    const before = selection();
    ctx.trackAffected(target);
    if (target.parent) ctx.trackAffected(target.parent);
    await ctx.write('remove', () => target.remove());
    return attachViewChange({removedId: id}, before);
  };
  const group = async op => {
    if (typeof ctx.figma.group !== 'function') throw new Error('Native grouping is unavailable');
    const parent = await ctx.node(op.parentId);
    if (parent.type === 'COMPONENT_SET') throw new Error('A component set cannot contain a group');
    const members = await resolveMembers(op.ids, parent, op.index);
    const props = op.props === undefined ? {} : object(op.props, 'props');
    const before = selection();
    const memberIds = members.map(member => member.id);
    markMembers(members, parent);
    const target = await ctx.write('group', () => ctx.trackCreated(ctx.figma.group(members, parent, op.index)));
    await ctx.nodes.apply(target, props);
    return attachViewChange({root: ctx.brief(target), memberIds}, before);
  };
  const ungroup = async op => {
    if (typeof ctx.figma.ungroup !== 'function') throw new Error('Native ungrouping is unavailable');
    const target = scene(await ctx.node(op.id));
    if (['COMPONENT', 'INSTANCE'].includes(target.type) || !('children' in target) || !target.parent) {
      throw new TypeError('The node cannot be ungrouped');
    }
    const id = target.id;
    const before = selection();
    const members = [...ctx.children(target)];
    markMembers(members, target.parent);
    ctx.trackAffected(target);
    const children = await ctx.write('ungroup', () => ctx.figma.ungroup(target));
    return attachViewChange({removedId: id, children: children.map(child => ctx.brief(child))}, before);
  };
  const boolean = async op => {
    const methods = {UNION: 'union', SUBTRACT: 'subtract', INTERSECT: 'intersect', EXCLUDE: 'exclude'};
    if (!Object.hasOwn(methods, op.operation)) throw new TypeError('operation must be UNION, SUBTRACT, INTERSECT, or EXCLUDE');
    const method = methods[op.operation];
    if (typeof ctx.figma[method] !== 'function') throw new Error(`Native ${op.operation} is unavailable`);
    const parent = await ctx.node(op.parentId);
    if (parent.type === 'COMPONENT_SET') throw new Error('A component set cannot contain a boolean operation');
    const members = await resolveMembers(op.ids, parent, op.index);
    const props = op.props === undefined ? {} : object(op.props, 'props');
    const before = selection();
    const sourceIds = members.map(member => member.id);
    markMembers(members, parent);
    const target = await ctx.write(`boolean ${op.operation}`, () => ctx.trackCreated(ctx.figma[method](members, parent, op.index)));
    await ctx.nodes.apply(target, props);
    return attachViewChange({root: ctx.brief(target), operation: op.operation, sourceIds,
      childIds: ctx.children(target).map(child => child.id)}, before);
  };
  return {
    edits: [
      {kind: 'node', action: 'duplicate', propsKind: 'node', required: ['id'], optional: ['parentId', 'index', 'props', 'mapping'], requires: [], targetMethods: ['clone'], execute: duplicate},
      {kind: 'node', action: 'move', propsKind: 'node', required: ['id', 'parentId'], optional: ['index', 'props', 'coordinates'], requires: [], targetMethods: [], execute: move},
      {kind: 'node', action: 'remove', required: ['id'], optional: [], requires: [], targetMethods: ['remove'], execute: remove},
      {kind: 'node', action: 'group', propsKind: 'node', required: ['ids', 'parentId'], optional: ['index', 'props'], requires: ['group'], targetMethods: [], execute: group},
      {kind: 'node', action: 'ungroup', required: ['id'], optional: [], requires: ['ungroup'], targetMethods: [], execute: ungroup},
      {kind: 'node', action: 'boolean', propsKind: 'node', required: ['ids', 'parentId', 'operation'], optional: ['index', 'props'],
        requires: ['union', 'subtract', 'intersect', 'exclude'], targetMethods: [], execute: boolean}
    ],
    queries: [],
    place,
    createPlaced,
    parentReady,
    checkPlacement,
    correspondence,
    resolveMembers
  };
}
