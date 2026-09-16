(() => {
  const article = document.querySelector('article');
  const firstImages = Array.from(article.querySelectorAll('img')).filter(image => image.getBoundingClientRect().top < 900);
  const imageReady = Promise.allSettled(firstImages.map(async image => {
    if (image.complete) return;
    const original = image.getAttribute('style');
    // Reserve an unknown image's slot if its source remains slow or fails.
    if (!image.getAttribute('height')) {
      image.style.aspectRatio = '2 / 1';
      image.style.objectFit = 'contain';
      image.style.maxHeight = '320px';
      if (!image.getAttribute('width')) image.style.width = '100%';
    }
    try {
      await image.decode();
      if (!image.dataset.deferred) {
        if (original === null) image.removeAttribute('style');
        else image.setAttribute('style', original);
      }
    } catch (_) { /* Preserve the reserved slot for an unavailable image. */ }
  }));
  const copyIcon = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/></svg>';
  const post = message => window.webkit.messageHandlers.document.postMessage(JSON.stringify({...message, document:document.documentElement.dataset.document}));
  let queued = false;
  const measure = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      post({type: 'size', height: Math.ceil(article.getBoundingClientRect().height), width: innerWidth});
    });
  };
  new ResizeObserver(measure).observe(article);
  addEventListener('resize', measure);
  document.addEventListener('selectionchange', () => post({type: 'selection', selected: !getSelection().isCollapsed}));
  article.querySelectorAll('[data-code]').forEach(pre => {
    const surface = document.createElement('div');
    surface.className = 'code-surface';
    pre.replaceWith(surface);
    const header = document.createElement('div');
    header.className = 'code-header';
    surface.append(header, pre);
    const caption = document.createElement('span');
    caption.className = 'code-caption';
    caption.textContent = pre.dataset.language || 'Code';
    header.append(caption);
    if (document.documentElement.dataset.copyCode !== 'true') return;
    const button = document.createElement('button');
    button.className = 'copy-code'; button.type = 'button'; button.title = 'Copy code';
    button.setAttribute('aria-label', 'Copy code');
    button.innerHTML = copyIcon;
    button.addEventListener('click', () => post({type:'copy', index:Number(pre.dataset.code)}));
    header.append(button);
  });
  window.documentCopied = index => {
    const button = article.querySelector(`[data-code="${index}"]`)?.closest('.code-surface')?.querySelector('.copy-code');
    if (!button) return;
    button.textContent = '✓';
    setTimeout(() => { button.innerHTML = copyIcon; }, 1500);
  };
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link) return;
    event.preventDefault();
    const href = link.getAttribute('href');
    if (href.startsWith('#')) {
      const target = document.getElementById(decodeURIComponent(href.slice(1)));
      if (target) post({type:'anchor', top:target.getBoundingClientRect().top + scrollY});
    } else post({type:'link', uri:href});
  });
  // WebView has no vertical scroller: wheel input belongs to the GTK host.
  document.addEventListener('wheel', event => {
    if (event.ctrlKey) return;
    let node = event.target;
    while (node && node !== article) {
      if (Math.abs(event.deltaX) > Math.abs(event.deltaY) && node.scrollWidth > node.clientWidth) return;
      node = node.parentElement;
    }
    event.preventDefault();
    post({type:'scroll', delta:event.deltaY * (event.deltaMode === 1 ? 20 : event.deltaMode === 2 ? innerHeight : 1)});
  }, {passive:false});
  document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || event.target.closest('button, summary, input')) return;
    const distance = {ArrowDown:40, ArrowUp:-40, PageDown:600, PageUp:-600, Home:-1e9, End:1e9, ' ':600}[event.key];
    if (distance !== undefined) { event.preventDefault(); post({type:'scroll', delta:distance}); }
  });
  const diagrams = Array.from(article.querySelectorAll('.mermaid'), node => ({node, source:node.textContent}));
  let rendering = false;
  const renderDiagrams = async () => {
    if (!window.mermaid || !diagrams.length || rendering) return;
    rendering = true;
    mermaid.initialize({startOnLoad:false, securityLevel:'strict', theme:document.documentElement.dataset.theme === 'dark' ? 'dark' : 'default'});
    for (const {node, source} of diagrams) { node.removeAttribute('data-processed'); node.textContent = source; }
    try { await mermaid.run({nodes:diagrams.map(item => item.node)}); }
    catch (error) { post({type:'extension-error', message:String(error)}); }
    finally { rendering = false; measure(); }
  };
  window.documentTheme = (dark, font, background) => {
    const theme = dark ? 'dark' : 'light';
    const changed = document.documentElement.dataset.theme !== theme;
    document.documentElement.dataset.theme = theme;
    if (background) document.documentElement.style.setProperty('--host-background', background);
    if (font) article.style.setProperty('--fontStack-monospace', JSON.stringify(font) + ', monospace');
    if (changed) renderDiagrams();
    measure();
  };
  addEventListener('DOMContentLoaded', async () => {
    if (window.katex) article.querySelectorAll('.math').forEach(node => {
      katex.render(node.textContent, node, {displayMode:node.classList.contains('block'), throwOnError:false, trust:false});
    });
    await renderDiagrams();
    await document.fonts.ready;
    await Promise.race([imageReady, new Promise(resolve => setTimeout(() => {
      firstImages.filter(image => !image.complete).forEach(image => { image.dataset.deferred = 'true'; });
      resolve();
    }, 2000))]);
    measure();
    requestAnimationFrame(() => requestAnimationFrame(() => post({type:'ready'})));
  });
})();
