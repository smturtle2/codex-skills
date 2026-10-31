/** Native text and font mechanics; this factory is evaluated in the live page. */
export function createTextOperations(ctx) {
  const properties = {
    fontName: {method: 'setRangeFontName', layout: true, priority: 1, replacesFont: true},
    fontSize: {method: 'setRangeFontSize', layout: true},
    textCase: {method: 'setRangeTextCase', layout: true},
    textDecoration: {method: 'setRangeTextDecoration', layout: true},
    textDecorationStyle: {method: 'setRangeTextDecorationStyle', layout: true},
    textDecorationOffset: {method: 'setRangeTextDecorationOffset', layout: true},
    textDecorationThickness: {method: 'setRangeTextDecorationThickness', layout: true},
    textDecorationColor: {method: 'setRangeTextDecorationColor', layout: true},
    textDecorationSkipInk: {method: 'setRangeTextDecorationSkipInk', layout: true},
    letterSpacing: {method: 'setRangeLetterSpacing', layout: true},
    lineHeight: {method: 'setRangeLineHeight', layout: true},
    fills: {method: 'setRangeFills'},
    fillStyleId: {method: 'setRangeFillStyleIdAsync', style: 'fill'},
    textStyleId: {method: 'setRangeTextStyleIdAsync', style: 'text', layout: true, priority: 0, replacesFont: true},
    hyperlink: {method: 'setRangeHyperlink'},
    listOptions: {method: 'setRangeListOptions'},
    indentation: {method: 'setRangeIndentation'},
    paragraphIndent: {method: 'setRangeParagraphIndent', layout: true},
    paragraphSpacing: {method: 'setRangeParagraphSpacing', layout: true},
    listSpacing: {method: 'setRangeListSpacing', layout: true},
    openTypeFeatures: {method: 'setRangeOpenTypeFeatures', layout: true},
    textWrapStyle: {method: 'setRangeTextWrapStyle', layout: true}
  };
  const layoutFields = new Set(['characters', 'hangingPunctuation', 'hangingList', 'textAutoResize',
    'leadingTrim', 'textTruncation', 'maxLines', 'width', 'height', 'textAlignHorizontal', 'textAlignVertical',
    ...Object.keys(properties).filter(key => properties[key].layout)]);
  const segmentFields = new Set([...Object.keys(properties), 'fontWeight', 'fontStyle', 'boundVariables', 'textStyleOverrides']);
  const loadedFonts = new Set();
  let availableFonts;
  const textNode = target => {
    if (!target || target.type !== 'TEXT') throw new TypeError('Text operations require a TEXT node');
    return target;
  };
  const fontInput = value => {
    ctx.assertObject(value, 'fontName');
    if (typeof value.family !== 'string' || !value.family ||
        (value.style !== undefined && typeof value.style !== 'string')) {
      throw new TypeError('fontName requires {family, style?}');
    }
    return value;
  };
  const boundary = (characters, index, label) => {
    if (!Number.isInteger(index) || index < 0 || index > characters.length) {
      throw new TypeError(`${label} must be a UTF-16 offset within the text`);
    }
    if (index > 0 && index < characters.length &&
        characters.charCodeAt(index - 1) >= 0xD800 && characters.charCodeAt(index - 1) <= 0xDBFF &&
        characters.charCodeAt(index) >= 0xDC00 && characters.charCodeAt(index) <= 0xDFFF) {
      throw new TypeError(`${label} splits a UTF-16 surrogate pair`);
    }
    return index;
  };
  const range = (target, start = 0, end = target.characters.length) => {
    textNode(target);
    boundary(target.characters, start, 'start');
    boundary(target.characters, end, 'end');
    if (end < start) throw new TypeError('end must be greater than or equal to start');
    return {start, end};
  };
  const load = async fonts => {
    for (const font of fonts) {
      fontInput(font);
      const key = JSON.stringify(font);
      if (!loadedFonts.has(key)) {
        await ctx.step('font:load', () => ctx.figma.loadFontAsync(font));
        loadedFonts.add(key);
      }
    }
  };
  const existingFonts = (target, selected) => {
    const {start, end} = selected ?? {start: 0, end: target.characters.length};
    if (end > start) return target.getRangeAllFontNames(start, end);
    if (target.fontName !== ctx.figma.mixed) return [fontInput(target.fontName)];
    if (target.characters.length) {
      const at = start === target.characters.length ? start - 1 : start;
      const first = at > 0 && target.characters.charCodeAt(at) >= 0xDC00 &&
        target.characters.charCodeAt(at) <= 0xDFFF ? at - 1 : at;
      const next = target.characters.codePointAt(first) > 0xFFFF ? first + 2 : first + 1;
      return target.getRangeAllFontNames(first, next);
    }
    throw new TypeError('An empty text node with mixed fonts requires an explicit fontName');
  };
  const prepareStyle = async (style, props = {}) => {
    if (!style || style.type !== 'TEXT') throw new TypeError('A TEXT style is required');
    ctx.assertObject(props, 'text style properties');
    await load([props.fontName ?? style.fontName]);
  };
  const prepareAll = async target => {
    if (target?.type === 'TEXT') await load(existingFonts(target));
  };
  const prepareBindings = async (target, plan) => {
    const modeTarget = plan.modeTarget ?? target;
    const modes = plan.modes.filter(item => {
      for (let current = target; current && current.id !== modeTarget.id; current = current.parent) {
        if (Object.hasOwn(current.explicitVariableModes ?? {}, item.collection.id)) return false;
      }
      return true;
    });
    if (target?.type !== 'TEXT') {
      if (modes.length) {
        await ctx.loadPage(target);
        for (const child of ctx.children(target)) await prepareBindings(child, {
          entityKind: 'node', styles: [], bindings: [], modes, modeTarget
        });
      }
      return;
    }
    const isStyle = plan.entityKind === 'style';
    const textStyleChange = plan.styles.find(item => item.field === 'text');
    const appliedStyle = textStyleChange?.style;
    const typography = ['fontFamily', 'fontStyle', 'fontWeight'];
    const affectsLayout = field => typography.includes(field) || layoutFields.has(field);
    const bindingChanges = plan.bindings.some(binding => binding.index === undefined && affectsLayout(binding.field));
    if (!bindingChanges && !modes.length && !textStyleChange) return;
    const contexts = [];
    if (appliedStyle) contexts.push({fontName: appliedStyle.fontName, boundVariables: appliedStyle.boundVariables});
    else if (!isStyle && target.characters.length && typeof target.getStyledTextSegments === 'function') {
      for (const segment of target.getStyledTextSegments(['fontName', 'boundVariables', 'textStyleId'])) {
        let styleBindings = {};
        if (segment.textStyleId) styleBindings = (await ctx.entity('style', segment.textStyleId)).boundVariables ?? {};
        contexts.push({fontName: segment.fontName, boundVariables: {...styleBindings, ...(segment.boundVariables ?? {})}});
      }
    } else contexts.push({fontName: target.fontName, boundVariables: target.boundVariables});
    const replacements = new Map(plan.bindings.filter(binding => binding.index === undefined && affectsLayout(binding.field)).map(binding => [binding.field, binding.variable]));
    const boundLayout = contexts.some(context => Object.keys({...target.boundVariables, ...context.boundVariables}).some(affectsLayout));
    if (!bindingChanges && !(modes.length && boundLayout) && !textStyleChange) return;
    const states = [{}];
    for (const item of modes) states.push({...states[states.length - 1], [item.collection.id]: item.modeId});
    const families = new Set(), resolved = new Map();
    const aliasVariables = async value => {
      const aliases = Array.isArray(value) ? value : value ? [value] : [];
      const variables = [];
      for (const alias of aliases) {
        if (!alias || typeof alias !== 'object') continue;
        const variableId = alias.id ?? alias.variableId;
        if (typeof variableId !== 'string' || !variableId) throw new TypeError('Typography binding has no variable identity');
        variables.push(await ctx.entity('variable', variableId));
      }
      return variables;
    };
    const resolve = async (variable, state, field) => {
      const key = `${variable.id}:${JSON.stringify(state)}`;
      if (!resolved.has(key)) resolved.set(key, await ctx.resources.resolveValue(variable, isStyle ? null : target, state, modeTarget));
      const value = resolved.get(key);
      if (field === 'fontWeight') {
        if (value.resolvedType !== 'FLOAT' || typeof value.value !== 'number' || !Number.isFinite(value.value)) throw new TypeError('fontWeight requires a finite FLOAT variable');
      } else if (['fontFamily', 'fontStyle'].includes(field) && (value.resolvedType !== 'STRING' || typeof value.value !== 'string' || !value.value)) {
        throw new TypeError(`${field} requires a nonempty STRING variable`);
      }
      return value.value;
    };
    let preparationRequired = bindingChanges || Boolean(textStyleChange);
    let changingTypography = [...replacements.keys()].some(field => typography.includes(field));
    for (const context of contexts) {
      const bound = appliedStyle ? context.boundVariables ?? {} : {...target.boundVariables, ...context.boundVariables};
      const fields = new Set([...typography, ...Object.keys(bound), ...replacements.keys()].filter(affectsLayout));
      for (const field of fields) {
        const variables = replacements.has(field) ? (replacements.get(field) ? [replacements.get(field)] : [])
          : await aliasVariables(bound[field]);
        if (variables.length && appliedStyle && typography.includes(field)) changingTypography = true;
        for (const variable of variables) {
          const initial = await resolve(variable, states[0], field);
          for (const state of states) {
            const value = await resolve(variable, state, field);
            if (JSON.stringify(value) !== JSON.stringify(initial)) {
              preparationRequired = true;
              if (typography.includes(field)) changingTypography = true;
            }
            if (field === 'fontFamily') families.add(value);
          }
        }
      }
    }
    if (!preparationRequired) return;
    if (appliedStyle) await prepareStyle(appliedStyle);
    else if (isStyle) await prepareStyle(target);
    else await prepareAll(target);
    if (!changingTypography) return;
    for (const context of contexts) { fontInput(context.fontName); families.add(context.fontName.family); }
    // Load actual faces of effective families, including named variable-font faces.
    // Loading every named face also covers family/style bindings applied together.
    availableFonts ??= ctx.figma.listAvailableFontsAsync();
    const available = await availableFonts;
    const fonts = [];
    for (const family of families) {
      const matches = available.map(item => item.fontName).filter(font => font.family === family);
      if (!matches.length) throw new Error(`Font family is unavailable: ${family}`);
      fonts.push(...matches);
    }
    await load(fonts);
  };
  const prepare = async (target, props = {}, selected) => {
    if (!target || target.type !== 'TEXT') return;
    ctx.assertObject(props, 'text properties');
    const keys = Object.keys(props).filter(key => layoutFields.has(key));
    if (!keys.length) return;
    let replacement = false;
    if (typeof props.textStyleId === 'string' && props.textStyleId) {
      const style = await ctx.entity('style', props.textStyleId);
      await prepareBindings(target, {entityKind: 'node', styles: [{field: 'text', style}], bindings: [], modes: []});
      replacement = true;
    }
    if (props.fontName !== undefined) {
      await load([props.fontName]);
      replacement = true;
    }
    const coversWholeText = !selected || (selected.start === 0 && selected.end === target.characters.length);
    const otherLayout = keys.some(key => key !== 'fontName' && key !== 'textStyleId');
    if (!replacement || (otherLayout && !coversWholeText)) await load(existingFonts(target));
  };
  const prepareTree = async target => {
    const visit = async current => {
      await prepareAll(current);
      for (const child of ctx.children(current)) await visit(child);
    };
    await visit(target);
  };
  const prepareProperties = async (target, props, empty = false) => {
    ctx.assertObject(props, 'range properties');
    const plan = [];
    for (const [key, value] of Object.entries(props)) {
      if (!Object.hasOwn(properties, key)) throw new TypeError(`Unsupported text range property: ${key}`);
      const definition = properties[key];
      if (!empty && typeof target[definition.method] !== 'function') throw new TypeError(`Unsupported text range property: ${key}`);
      if (key === 'fontName') fontInput(value);
      let application;
      if (definition.style) {
        application = await ctx.resources.validateApplication(target, {styles: {[definition.style]: value}});
      } else if (empty) {
        try { ctx.nodes.validateProps(target, {[key]: value}); }
        catch (error) { throw new TypeError(`Text property ${key} has no supported empty-result application: ${error.message}`); }
      }
      plan.push({key, value, definition, application});
    }
    return plan.sort((a, b) => (a.definition.priority ?? 2) - (b.definition.priority ?? 2));
  };
  const applyWholeProperty = async (target, item) => {
    if (item.application) await ctx.resources.apply(target, {}, item.application);
    else await ctx.nodes.apply(target, {[item.key]: item.value});
  };
  const applyRange = async (target, start, end, props, prepared) => {
    const plan = prepared ?? await prepareProperties(target, props);
    await prepare(target, props, {start, end});
    for (const item of plan) {
      await ctx.write(`text:${item.key}`, () => target[item.definition.method](start, end, item.value));
    }
  };
  const edit = async op => {
    const target = textNode(await ctx.node(op.id));
    const selected = range(target, op.start, op.end);
    const props = op.props ?? {};
    ctx.assertObject(props, 'range properties');
    if (op.characters !== undefined && typeof op.characters !== 'string') throw new TypeError('characters must be a string');
    if (op.useStyle !== undefined && !['BEFORE', 'AFTER'].includes(op.useStyle)) throw new TypeError('useStyle must be BEFORE or AFTER');
    if (op.characters === undefined && !Object.keys(props).length) throw new TypeError('A text edit requires characters or range properties');
    const replacement = op.characters !== undefined;
    const resultEnd = replacement ? selected.start + op.characters.length : selected.end;
    const empty = resultEnd === selected.start;
    if (empty && Object.keys(props).length && !(selected.start === 0 && selected.end === target.characters.length)) {
      throw new TypeError('Range properties require a nonempty result range');
    }
    // Resolve every writer and style before preparing or changing characters.
    const plan = await prepareProperties(target, props, empty);
    await prepare(target, props, empty ? undefined : selected);
    // A full replacement may repair missing source fonts before character mutation.
    // These writes prepare the source; final formatting still follows insertion/deletion.
    const replacesWholeText = replacement && selected.start === 0 && selected.end === target.characters.length;
    if (replacesWholeText) {
      for (const item of plan) if (item.definition.replacesFont && item.value) await applyWholeProperty(target, item);
    }
    if (replacement) {
      await prepare(target, {characters: op.characters});
      if (op.characters.length) {
        await ctx.write('text:insert', () => target.insertCharacters(selected.start, op.characters, op.useStyle));
      }
      if (selected.end > selected.start) {
        const shift = op.characters.length;
        await ctx.write('text:delete', () => target.deleteCharacters(selected.start + shift, selected.end + shift));
      }
    }
    if (plan.length) {
      if (!empty) await applyRange(target, selected.start, resultEnd, props, plan);
      else for (const item of plan) await applyWholeProperty(target, item);
    }
    ctx.trackAffected(target);
    return {node: ctx.brief(target), range: {start: selected.start, end: resultEnd}, offsets: 'UTF-16'};
  };
  const inspect = async op => {
    const target = textNode(await ctx.node(op.id));
    const requested = range(target, op.start ?? 0, op.end ?? target.characters.length);
    const limit = ctx.integer(op.limit, 1000, 4000, 'text limit', 1);
    const fields = op.fields ?? ['fontName', 'fontSize', 'fills', 'textStyleId', 'fillStyleId'];
    if (!Array.isArray(fields) || fields.length > 40 || fields.some(key => !segmentFields.has(key))) {
      throw new TypeError('fields must contain at most 40 supported styled-text property names');
    }
    let windowEnd = Math.min(requested.end, requested.start + limit);
    if (windowEnd < requested.end && windowEnd > requested.start &&
        target.characters.charCodeAt(windowEnd - 1) >= 0xD800 && target.characters.charCodeAt(windowEnd - 1) <= 0xDBFF &&
        target.characters.charCodeAt(windowEnd) >= 0xDC00 && target.characters.charCodeAt(windowEnd) <= 0xDFFF) windowEnd--;
    if (windowEnd === requested.start && requested.end > requested.start) windowEnd = Math.min(requested.end, requested.start + 2);
    const all = windowEnd > requested.start ? target.getStyledTextSegments([...new Set(fields)], requested.start, windowEnd) : [];
    const segments = all.slice(0, 100);
    const end = segments.length < all.length ? segments[segments.length - 1].end : windowEnd;
    return {id: target.id, offsets: 'UTF-16', start: requested.start, end, requestedEnd: requested.end,
      textLength: target.characters.length, segments: ctx.serialize(segments), complete: end === requested.end,
      nextStart: end < requested.end ? end : null};
  };
  return {
    edits: [{kind: 'node', action: 'text', required: ['id', 'start', 'end'],
      optional: ['characters', 'props', 'useStyle'], requires: ['loadFontAsync'],
      targetMethods: ['insertCharacters', 'deleteCharacters'], execute: edit}],
    queries: [{kind: 'text', required: ['id'], optional: ['start', 'end', 'fields', 'limit'],
      requires: [], targetMethods: ['getStyledTextSegments'], execute: inspect}],
    prepare, prepareStyle, prepareAll, prepareBindings, prepareTree, applyRange, range
  };
}
