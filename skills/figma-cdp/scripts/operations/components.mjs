/** Native component mechanics; this factory is evaluated in the live page. */
export function createComponentOperations(ctx) {
  const requireMethod = (target, method) => {
    if (typeof target[method] !== 'function') throw new TypeError(`Native ${method} is unavailable on this target`);
  };
  const component = target => {
    if (!target || target.type !== 'COMPONENT') throw new TypeError('A COMPONENT node is required');
    return target;
  };
  const definitionOwner = target => {
    if (target.type === 'COMPONENT_SET') return target;
    component(target);
    return target.parent?.type === 'COMPONENT_SET' ? target.parent : target;
  };
  const editableDefinitions = target => {
    const owner = definitionOwner(target);
    if (owner !== target) throw new TypeError(`Component definitions are owned by component set ${owner.id}`);
    return owner;
  };
  const propertiesInput = (properties, definitions = {}, observed = {}) => {
    ctx.assertObject(properties, 'component properties');
    for (const [key, value] of Object.entries(properties)) {
      if (!key) throw new TypeError('Component property keys must be actual nonempty property IDs');
      if ((definitions[key] ?? observed[key])?.type === 'SLOT') throw new TypeError('SLOT content cannot be changed through component properties');
      const alias = value && typeof value === 'object' && value.type === 'VARIABLE_ALIAS' && typeof value.id === 'string';
      if (typeof value !== 'string' && typeof value !== 'boolean' && !alias) {
        throw new TypeError(`Component property ${key} requires a string, boolean, or VariableAlias`);
      }
    }
    return properties;
  };
  const validateConfiguration = async (target, spec = {}) => {
    if (target.type !== 'INSTANCE') throw new TypeError('Instance configuration requires an INSTANCE node');
    ctx.assertObject(spec, 'component configuration');
    for (const key of Object.keys(spec)) if (!['mainComponentId', 'properties'].includes(key)) {
      throw new TypeError(`Unsupported component configuration field: ${key}`);
    }
    const source = spec.mainComponentId === undefined ? null : component(await ctx.node(spec.mainComponentId));
    if (source && typeof target.swapComponent !== 'function') throw new TypeError('Native instance swapping is unavailable');
    let definitions = {}, observed = {};
    if (spec.properties !== undefined) {
      if (typeof target.setProperties !== 'function') throw new TypeError('Native instance properties are unavailable');
      const main = source ?? (typeof target.getMainComponentAsync === 'function'
        ? await target.getMainComponentAsync() : target.mainComponent);
      if (main) definitions = definitionOwner(main).componentPropertyDefinitions;
      if (!source) observed = target.componentProperties;
      propertiesInput(spec.properties, definitions, observed);
    }
    return {source, properties: spec.properties};
  };
  const configure = async (target, spec) => {
    const prepared = await validateConfiguration(target, spec);
    if (prepared.source) await ctx.write('component:swap', () => target.swapComponent(prepared.source));
    if (prepared.properties !== undefined) await ctx.write('component:properties', () => target.setProperties(prepared.properties));
    ctx.trackAffected(target);
    return ctx.brief(target);
  };
  const createInstance = async op => {
    const source = component(await ctx.node(op.componentId));
    const parent = op.parentId === undefined ? ctx.requestPage : await ctx.node(op.parentId);
    if (typeof source.createInstance !== 'function') throw new TypeError('Native instance creation is unavailable');
    if (op.props !== undefined) ctx.assertObject(op.props, 'props');
    const instance = await ctx.structure.createPlaced(() => source.createInstance(), parent, op.index,
      {type: 'INSTANCE', createLabel: 'instance:create', placeLabel: 'instance:attach'});
    await ctx.nodes.configure(instance, op);
    return ctx.brief(instance);
  };
  const define = async op => {
    const target = editableDefinitions(await ctx.node(op.id));
    requireMethod(target, 'addComponentProperty');
    if (typeof op.name !== 'string' || !op.name) throw new TypeError('name must be a nonempty string');
    if (!['BOOLEAN', 'TEXT', 'INSTANCE_SWAP', 'VARIANT', 'SLOT'].includes(op.propertyType)) throw new TypeError('Unsupported component property type');
    if (op.propertyType === 'VARIANT' && target.type !== 'COMPONENT_SET') throw new TypeError('VARIANT definitions require a COMPONENT_SET');
    if (op.options !== undefined) ctx.assertObject(op.options, 'property options');
    const key = await ctx.write('component:define', () => target.addComponentProperty(op.name, op.propertyType, op.defaultValue, op.options));
    ctx.trackAffected(target);
    return {id: target.id, propertyKey: key, definitions: ctx.serialize(target.componentPropertyDefinitions, {id: target.id, path: ['componentPropertyDefinitions']})};
  };
  const updateDefinition = async op => {
    const target = editableDefinitions(await ctx.node(op.id));
    requireMethod(target, 'editComponentProperty');
    ctx.assertId(op.propertyKey, 'propertyKey');
    ctx.assertObject(op.changes, 'definition changes');
    const keys = ['name', 'defaultValue', 'preferredValues', 'description', 'slotSettings'];
    for (const key of Object.keys(op.changes)) if (!keys.includes(key)) throw new TypeError(`Unsupported definition change: ${key}`);
    const key = await ctx.write('component:update-definition', () => target.editComponentProperty(op.propertyKey, op.changes));
    ctx.trackAffected(target);
    return {id: target.id, propertyKey: key, definitions: ctx.serialize(target.componentPropertyDefinitions, {id: target.id, path: ['componentPropertyDefinitions']})};
  };
  const removeDefinition = async op => {
    const target = editableDefinitions(await ctx.node(op.id));
    requireMethod(target, 'deleteComponentProperty');
    ctx.assertId(op.propertyKey, 'propertyKey');
    await ctx.write('component:remove-definition', () => target.deleteComponentProperty(op.propertyKey));
    ctx.trackAffected(target);
    return {id: target.id, removedPropertyKey: op.propertyKey};
  };
  const createSlot = async op => {
    const target = component(await ctx.node(op.id));
    if (typeof target.createSlot !== 'function') throw new TypeError('Native component slots are unavailable');
    if (op.props !== undefined) ctx.assertObject(op.props, 'props');
    const slot = await ctx.write('component:create-slot', () => ctx.trackCreated(target.createSlot()));
    if (op.props) await ctx.nodes.apply(slot, op.props);
    ctx.trackAffected(target);
    return {root: ctx.brief(slot), references: ctx.serialize(slot.componentPropertyReferences, {id: slot.id, path: ['componentPropertyReferences']})};
  };
  const combineVariants = async op => {
    if (!Array.isArray(op.ids) || !op.ids.length || new Set(op.ids).size !== op.ids.length) {
      throw new TypeError('ids must contain distinct component IDs');
    }
    const nodes = await Promise.all(op.ids.map(async id => component(await ctx.node(id))));
    const parent = await ctx.node(op.parentId);
    await ctx.structure.parentReady(parent, op.index);
    const index = op.index === undefined ? undefined : ctx.integer(op.index, undefined, ctx.children(parent).length, 'index');
    if (op.props !== undefined) ctx.assertObject(op.props, 'props');
    for (let ancestor = parent; ancestor; ancestor = ancestor.parent) if (nodes.some(node => node.id === ancestor.id)) {
      throw new TypeError('Combining variants would create a parenting cycle');
    }
    for (const item of nodes) ctx.trackAffected(item);
    const set = await ctx.write('component:combine-variants', () => ctx.trackCreated(ctx.figma.combineAsVariants(nodes, parent, index)));
    if (op.props) await ctx.nodes.apply(set, op.props);
    return {root: ctx.brief(set), memberIds: ctx.children(set).map(node => node.id)};
  };
  const detach = async op => {
    const target = await ctx.node(op.id);
    if (target.type !== 'INSTANCE' || typeof target.detachInstance !== 'function') throw new TypeError('detach requires an INSTANCE');
    const originalId = target.id;
    const instances = [];
    let stableParent = target.parent;
    for (let ancestor = target; ancestor; ancestor = ancestor.parent) if (ancestor.type === 'INSTANCE') {
      instances.push(ancestor.id);
      stableParent = ancestor.parent;
      ctx.trackAffected(ancestor);
    }
    const frame = await ctx.write('component:detach', () => target.detachInstance());
    if (frame.id !== originalId) ctx.trackCreated(frame);
    else ctx.remember(frame);
    return {root: ctx.brief(frame), invalidatedInstanceIds: instances, rediscoverFromId: stableParent?.id ?? null};
  };
  const importComponent = async op => {
    ctx.assertId(op.key, 'component key');
    const imported = await ctx.write('component:import', () => ctx.figma.importComponentByKeyAsync(op.key));
    ctx.remember(imported);
    ctx.trackAffected(imported);
    return {component: ctx.brief(imported), key: imported.key};
  };
  const inspect = async op => {
    const target = await ctx.node(op.id);
    let main = null;
    if (target.type === 'INSTANCE') main = typeof target.getMainComponentAsync === 'function'
      ? await target.getMainComponentAsync() : target.mainComponent;
    const owner = target.type === 'INSTANCE' ? (main ? definitionOwner(main) : null) : definitionOwner(target);
    const result = {node: ctx.brief(target), definitionOwnerId: owner?.id ?? null,
      definitions: owner ? ctx.serialize(owner.componentPropertyDefinitions, {id: owner.id, path: ['componentPropertyDefinitions']}) : null};
    if (target.type === 'INSTANCE') {
      result.mainComponent = main ? ctx.brief(main) : null;
      result.properties = ctx.serialize(target.componentProperties, {id: target.id, path: ['componentProperties']});
    }
    return result;
  };
  return {
    edits: [
      {kind: 'component', action: 'define', required: ['id', 'name', 'propertyType', 'defaultValue'], optional: ['options'], targetMethods: ['addComponentProperty'], requires: [], execute: define},
      {kind: 'component', action: 'updateDefinition', required: ['id', 'propertyKey', 'changes'], optional: [], targetMethods: ['editComponentProperty'], requires: [], execute: updateDefinition},
      {kind: 'component', action: 'removeDefinition', required: ['id', 'propertyKey'], optional: [], targetMethods: ['deleteComponentProperty'], requires: [], execute: removeDefinition},
      {kind: 'component', action: 'createSlot', required: ['id'], optional: ['props'], targetMethods: ['createSlot'], requires: [], execute: createSlot},
      {kind: 'component', action: 'combineVariants', required: ['ids', 'parentId'], optional: ['index', 'props'], targetMethods: [], requires: ['combineAsVariants'], execute: combineVariants},
      {kind: 'component', action: 'detach', required: ['id'], optional: [], targetMethods: ['detachInstance'], requires: [], execute: detach},
      {kind: 'component', action: 'import', required: ['key'], optional: [], targetMethods: [], requires: ['importComponentByKeyAsync'], execute: importComponent}
    ],
    queries: [{kind: 'component', required: ['id'], optional: [], targetMethods: [], requires: [], execute: inspect}],
    createInstance, configure, validateConfiguration
  };
}
