/* Native node properties and owned creation/update compounds. */
export function createNodeOperations(ctx) {
  const factories = {FRAME: 'createFrame', RECTANGLE: 'createRectangle', ELLIPSE: 'createEllipse',
    TEXT: 'createText', LINE: 'createLine', VECTOR: 'createVector', COMPONENT: 'createComponent',
    POLYGON: 'createPolygon', STAR: 'createStar', SECTION: 'createSection', PAGE: 'createPage', SLICE: 'createSlice'};
  const protectedFields = new Set(['id', 'type', 'parent', 'children', 'removed', '__proto__', 'constructor', 'prototype']);
  const managed = {reactions: 'reactions', componentProperties: 'component.properties', mainComponent: 'component.mainComponentId',
    boundVariables: 'bindings', explicitVariableModes: 'modes', fillStyleId: 'styles.fill', strokeStyleId: 'styles.stroke',
    effectStyleId: 'styles.effect', gridStyleId: 'styles.grid', textStyleId: 'styles.text'};
  const validateBasicProps = props => {
    if (!props || typeof props !== 'object' || Array.isArray(props) || ![Object.prototype, null].includes(Object.getPrototypeOf(props))) throw new TypeError('props must be a plain object');
    for (const [key, value] of Object.entries(props)) {
      if (protectedFields.has(key)) throw new TypeError(`Cannot assign ${key}; use the corresponding edit operation`);
      if (managed[key]) throw new TypeError(`Use the ${managed[key]} edit field for ${key}`);
      if (['width', 'height'].includes(key) && (typeof value !== 'number' || !Number.isFinite(value) || value < 0)) throw new TypeError(`${key} must be a finite nonnegative number`);
      if (key === 'fontName' && (!value || typeof value.family !== 'string' || !value.family || (value.style !== undefined && typeof value.style !== 'string'))) throw new TypeError('fontName requires {family, style?}');
    }
    return props;
  };
  const validateProps = (target, props = {}) => {
    validateBasicProps(props);
    for (const key of Object.keys(props)) {
      if (['width', 'height'].includes(key)) {
        if (typeof target.resize !== 'function') throw new TypeError(`${key} requires a resizable node`);
        continue;
      }
      if (!(key in target) || typeof target[key] === 'function') throw new TypeError(`Unsupported property: ${key}`);
      let owner = target, descriptor;
      while (owner && !descriptor) { descriptor = Object.getOwnPropertyDescriptor(owner, key); owner = Object.getPrototypeOf(owner); }
      if (descriptor && (('writable' in descriptor && !descriptor.writable) || (!('writable' in descriptor) && !descriptor.set))) throw new TypeError(`Read-only property: ${key}`);
      if (key === 'fontName' && target.type !== 'TEXT') throw new TypeError('fontName requires a TEXT node');
    }
    return props;
  };
  const apply = async (target, props = {}) => {
    validateProps(target, props);
    await ctx.text.prepare(target, props);
    for (const key of ['layoutMode', 'fontName']) if (Object.hasOwn(props, key)) await ctx.write(`property:${key}`, () => { target[key] = props[key]; });
    if (Object.hasOwn(props, 'width') || Object.hasOwn(props, 'height')) await ctx.write('resize', () => target.resize(props.width ?? target.width, props.height ?? target.height));
    for (const [key, value] of Object.entries(props)) if (!['layoutMode', 'fontName', 'width', 'height'].includes(key)) await ctx.write(`property:${key}`, () => { target[key] = value; });
    if (Object.keys(props).length) ctx.trackAffected(target);
    return target;
  };
  const configure = async (target, op) => {
    validateProps(target, op.props ?? {});
    if (op.reactions !== undefined && (!Array.isArray(op.reactions) || typeof target.setReactionsAsync !== 'function')) throw new TypeError('reactions requires a supported node and an array of native Reaction data');
    const application = await ctx.resources.validateApplication(target, op);
    if (op.component !== undefined) await ctx.components.validateConfiguration(target, op.component);
    await apply(target, op.props ?? {});
    await ctx.resources.apply(target, op, application);
    if (op.component !== undefined) await ctx.components.configure(target, op.component);
    if (op.reactions !== undefined) {
      await ctx.write('reactions', () => target.setReactionsAsync(op.reactions));
      ctx.trackAffected(target);
    }
    return target;
  };
  const extra = ['props', 'styles', 'bindings', 'modes', 'component', 'reactions'];
  const create = async op => {
    validateBasicProps(op.props ?? {});
    if (op.type === 'INSTANCE') return ctx.components.createInstance(op);
    const factory = factories[op.type];
    if (!factory || typeof ctx.figma[factory] !== 'function') throw new TypeError(`Unsupported or unavailable node type: ${op.type}`);
    const parent = op.type === 'PAGE' ? ctx.figma.root : op.parentId === undefined ? ctx.requestPage : await ctx.node(op.parentId);
    if (op.type === 'PAGE' && op.parentId !== undefined && op.parentId !== ctx.figma.root.id) throw new TypeError('PAGE belongs to the document root');
    if (typeof parent.appendChild !== 'function') throw new TypeError('Parent cannot contain nodes');
    let target;
    if (op.type === 'PAGE') {
      if (op.index !== undefined) ctx.integer(op.index, undefined, ctx.children(parent).length, 'index');
      target = await ctx.write('create', () => ctx.trackCreated(ctx.figma[factory]()));
      validateProps(target, op.props ?? {});
      if (op.index !== undefined) await ctx.write('page:order', () => parent.insertChild(op.index, target));
    } else target = await ctx.structure.createPlaced(() => ctx.figma[factory](), parent, op.index, {type: op.type});
    await configure(target, op);
    return ctx.brief(target);
  };
  const update = async op => {
    const target = await ctx.node(op.id);
    await configure(target, op);
    return ctx.brief(target);
  };
  const scale = async op => {
    const target = await ctx.node(op.id);
    if (typeof target.rescale !== 'function' || typeof op.factor !== 'number' || !Number.isFinite(op.factor) || op.factor < 0.01) throw new TypeError('scale requires a rescalable node and factor >= 0.01');
    await ctx.text.prepareTree(target);
    await ctx.write('scale', () => target.rescale(op.factor));
    ctx.trackAffected(target);
    return ctx.brief(target);
  };
  return {validateBasicProps, validateProps, apply, configure, edits: [
    {kind: 'node', action: 'create', required: ['type'], optional: ['parentId', 'index', 'componentId', ...extra], nodeTypes: [...Object.keys(factories), 'INSTANCE'], execute: create},
    {kind: 'node', action: 'update', required: ['id'], optional: extra, execute: update},
    {kind: 'node', action: 'scale', required: ['id', 'factor'], optional: [], targetMethods: ['rescale'], execute: scale}
  ], queries: []};
}
