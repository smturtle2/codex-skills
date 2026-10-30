/* Editor state, independent from document content edits. */
export function createViewOperations(ctx) {
  const state = () => {
    const page = ctx.figma.currentPage, selected = page.selection;
    return {page: ctx.fields(page, ['name']), selection: selected.slice(0, 100).map(ctx.brief), selectionCount: selected.length,
      selectionContinuation: selected.length > 100 ? {kind: 'property', id: page.id, path: ['selection'], offset: 100} : null,
      viewport: ctx.serialize({center: ctx.figma.viewport.center, zoom: ctx.figma.viewport.zoom, bounds: ctx.figma.viewport.bounds})};
  };
  const definition = {required: [], optional: ['pageId', 'selection', 'fit', 'center', 'zoom']};
  const update = async input => {
    ctx.assertObject(input, 'view request');
    for (const key of Object.keys(input)) if (!definition.optional.includes(key)) throw new TypeError(`Unknown view field: ${key}`);
    if (input.fit !== undefined && (input.center !== undefined || input.zoom !== undefined)) throw new TypeError('fit and explicit camera values are alternatives');
    const page = input.pageId === undefined ? ctx.requestPage : await ctx.node(input.pageId);
    if (page.type !== 'PAGE') throw new TypeError('pageId must identify a PAGE');
    await ctx.loadPage(page);
    const resolve = async (ids, label) => {
      if (!Array.isArray(ids) || ids.length > 1000) throw new TypeError(`${label} must be an array of at most 1000 node IDs`);
      const result = [];
      for (const id of ids) {
        const target = await ctx.node(id);
        let owner = target.parent;
        while (owner && owner.type !== 'PAGE') owner = owner.parent;
        if (target.type === 'PAGE' || target.type === 'DOCUMENT' || owner?.id !== page.id) throw new TypeError(`${label} nodes must belong to the requested page`);
        result.push(target);
      }
      return result;
    };
    const selection = input.selection === undefined ? undefined : await resolve(input.selection, 'selection');
    const fit = input.fit === undefined ? undefined : await resolve(input.fit, 'fit');
    if (fit && !fit.length) throw new TypeError('fit needs at least one node');
    if (input.center !== undefined && (!input.center || typeof input.center.x !== 'number' || typeof input.center.y !== 'number' || !Number.isFinite(input.center.x) || !Number.isFinite(input.center.y))) throw new TypeError('center needs finite x/y');
    if (input.zoom !== undefined && (typeof input.zoom !== 'number' || !Number.isFinite(input.zoom) || input.zoom <= 0)) throw new TypeError('zoom must be positive and finite');
    const assertPage = () => {
      const actualPageId = ctx.figma.currentPage.id;
      if (page.removed || actualPageId !== page.id) throw ctx.error('view:page-check', `Expected active page ${page.id}, observed ${actualPageId}`, {
        expectedPageId: page.id, actualPageId
      });
    };
    const write = (label, fn) => {
      assertPage();
      return ctx.writeSync(label, fn);
    };
    if (input.pageId !== undefined && page.id !== ctx.figma.currentPage.id) await ctx.write('view:page', () => ctx.figma.setCurrentPageAsync(page));
    if (selection !== undefined) write('view:selection', () => { page.selection = selection; });
    if (fit) write('view:fit', () => ctx.figma.viewport.scrollAndZoomIntoView(fit));
    if (input.center !== undefined) write('view:center', () => { ctx.figma.viewport.center = input.center; });
    if (input.zoom !== undefined) write('view:zoom', () => { ctx.figma.viewport.zoom = input.zoom; });
    if (Object.keys(input).length) assertPage();
    return state();
  };
  return {definition, state, update, edits: [], queries: [{kind: 'state', required: [], optional: [], execute: state}]};
}
