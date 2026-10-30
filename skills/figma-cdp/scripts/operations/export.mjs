/* Native artifact export bypasses observation serialization limits. */
export function createExportOperations(ctx) {
  const formats = {PNG: ['image/png', 'binary'], JPG: ['image/jpeg', 'binary'], SVG: ['image/svg+xml', 'binary'],
    PDF: ['application/pdf', 'binary'], SVG_STRING: ['image/svg+xml', 'text'], JSON_REST_V1: ['application/json', 'json']};
  const definition = {required: ['id'], optional: ['settings'], formats: Object.keys(formats)};
  const exportNode = async input => {
    ctx.assertObject(input, 'export request');
    for (const key of Object.keys(input)) if (![...definition.required, ...definition.optional].includes(key)) throw new TypeError(`Unknown export field: ${key}`);
    const target = await ctx.node(input.id), settings = input.settings ?? {format: 'PNG'};
    ctx.assertObject(settings, 'export settings');
    const entry = formats[settings.format];
    if (!entry || typeof target.exportAsync !== 'function') throw new TypeError('Unsupported export format or target');
    await ctx.loadPage(target);
    const value = await target.exportAsync(settings), [mimeType, kind] = entry;
    if (kind === 'binary') return {kind, mimeType, base64: ctx.figma.base64Encode(value)};
    if (kind === 'text') return {kind, mimeType, text: value};
    return {kind, mimeType, data: value};
  };
  return {definition, export: exportNode, edits: [], queries: []};
}
