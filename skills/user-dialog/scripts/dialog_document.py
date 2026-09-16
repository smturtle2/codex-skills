"""Compile document Markdown into portable HTML; no GTK or network access."""

from dataclasses import dataclass
from functools import lru_cache
import html
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlsplit

import bleach
from bleach.css_sanitizer import CSSSanitizer
from bleach._vendor import html5lib
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound
from pygments.style import Style
from pygments.token import Comment, Error, Keyword, Name, Number, Operator, String

from dialog_fonts import document_fonts

ASSETS = Path(__file__).resolve().parent.parent / 'assets' / 'document'
TAGS = {'a', 'abbr', 'b', 'blockquote', 'br', 'code', 'dd', 'del', 'details', 'div',
        'dl', 'dt', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img',
        'input', 'kbd', 'li', 'ol', 'p', 'picture', 'pre', 's', 'samp', 'small',
        'span', 'strong', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'th',
        'thead', 'tr', 'ul'}
ATTRS = {'*': ['id', 'class', 'title', 'align', 'style', 'dir'],
         'a': ['href', 'name'], 'img': ['src', 'alt', 'width', 'height'],
         'ol': ['start', 'reversed'], 'li': ['value'],
         'td': ['colspan', 'rowspan'], 'th': ['colspan', 'rowspan', 'scope'],
         'input': ['type', 'checked', 'disabled'], 'details': ['open'],
         'pre': ['data-code', 'data-language'], 'div': ['data-code', 'data-language']}


@dataclass
class Document:
    body: str
    codes: list[str]
    resources: set[Path]
    math: bool
    mermaid: bool


def code_html(source, language='', caption=None, index=0):
    """One code surface for authored nodes and Markdown fences."""
    try:
        lexer = get_lexer_by_name(language, stripnl=False, ensurenl=False)
        rendered = highlight(source, lexer, HtmlFormatter(nowrap=True))
    except ClassNotFound:
        rendered = html.escape(source)
    return (f'<pre data-code="{index}" data-language="{html.escape(caption or language or "Code", quote=True)}">'
            f'<code>{rendered}</code></pre>')


def compile_code(source, language='', caption=None):
    return Document(code_html(source, language, caption), [source], set(), False, False)


@lru_cache(maxsize=16)
def compile_document(source, base):
    """Use a standard parser and sanitize HTML while retaining document layout."""
    base_uri = Path(base).resolve().as_uri() + '/'
    codes = []
    mermaid = False
    parser = (MarkdownIt('commonmark', {'html': True})
              .enable(['table', 'strikethrough'])
              .use(tasklists_plugin).use(footnote_plugin)
              .use(dollarmath_plugin, allow_labels=False, allow_space=False, allow_digits=False))

    def code(renderer, tokens, index, options, env):
        nonlocal mermaid
        token = tokens[index]
        language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ''
        position = len(codes)
        codes.append(token.content)
        if language.lower() == 'mermaid':
            mermaid = True
            return (f'<div class="diagram" data-code="{position}" data-language="mermaid">'
                    f'<pre class="mermaid">{html.escape(token.content)}</pre></div>\n')
        return code_html(token.content, language, index=position) + '\n'

    parser.add_render_rule('fence', code)
    parser.add_render_rule('code_block', code)
    tokens = parser.parse(source)
    # Stable, human-readable heading IDs; raw HTML anchors are handled below.
    used = set()
    for index, token in enumerate(tokens):
        if token.type == 'heading_open':
            content = tokens[index + 1]
            text = ''.join(t.content for t in content.children or [] if t.type in {'text', 'code_inline'})
            slug = re.sub(r'[^\w\- ]', '', text.lower()).replace(' ', '-') or 'section'
            unique, number = slug, 0
            while unique in used:
                number += 1
                unique = f'{slug}-{number}'
            used.add(unique)
            token.attrSet('id', unique)
    rendered = parser.renderer.render(tokens, parser.options, {})
    cleaned = bleach.clean(rendered, tags=TAGS, attributes=ATTRS,
                           protocols={'http', 'https', 'mailto', 'file', 'data'}, strip=True,
                           css_sanitizer=CSSSanitizer(allowed_css_properties=['text-align', 'width', 'height', 'max-width']))
    tree = html5lib.parseFragment(cleaned, namespaceHTMLElements=False)
    resources = set()
    has_math = False
    for element in tree.iter():
        has_math |= 'math' in element.get('class', '').split()
        if element.tag == 'input':
            element.set('type', 'checkbox')
            element.set('disabled', '')
        for name in ('id', 'name'):
            if name in element.attrib:
                element.set(name, 'doc-' + element.get(name))
        for name in ('src', 'href'):
            value = element.get(name)
            if value is None:
                continue
            if name == 'href' and value.startswith('#'):
                element.set(name, '#doc-' + unquote(value[1:]))
                continue
            resolved = urljoin(base_uri, value)
            parsed = urlsplit(resolved)
            allowed = {'http', 'https', 'file'} | ({'mailto'} if name == 'href' else set())
            data_image = name == 'src' and re.match(r'^data:image/(png|jpeg|gif|webp);base64,', resolved, re.I)
            if parsed.scheme not in allowed and not data_image:
                del element.attrib[name]
                continue
            element.set(name, resolved)
            if name == 'src' and parsed.scheme == 'file' and parsed.netloc in {'', 'localhost'}:
                resources.add(Path(unquote(parsed.path)))
    return Document(html5lib.serialize(tree, quote_attr_values='always', omit_optional_tags=False),
                    codes, resources, has_math, mermaid)


def code_styles(dark):
    colors = (['#9aa2ad', '#c4a7d9', '#9dbb99', '#a4bfd8', '#d3b58c'] if dark else
              ['#6e7781', '#795b8f', '#526f50', '#476b8b', '#8b6840'])
    comment, keyword, string, name, number = colors
    palette = type('DialogCodeStyle', (Style,), {'styles': {
        Comment: comment, Keyword: keyword, String: string, Name.Function: name,
        Name.Class: name, Name.Builtin: name, Number: number, Operator: keyword,
        Error: 'noinherit',
    }})
    theme = 'dark' if dark else 'light'
    return HtmlFormatter(style=palette).get_style_defs(f'[data-theme="{theme}"] .markdown-body')


@lru_cache(maxsize=1)
def styles():
    vendor = ASSETS / 'vendor'
    theme_css = '\n'.join((vendor / 'github-markdown-css' / f'github-markdown-{theme}.css')
                          .read_text().replace('.markdown-body', f'[data-theme="{theme}"] .markdown-body')
                          for theme in ('light', 'dark'))
    return (document_fonts() + '\n' + theme_css + '\n' +
            code_styles(False) + '\n' +
            code_styles(True) + '\n' +
            (ASSETS / 'document.css').read_text())


def compile_segments(sources, base):
    """Keep each node's Markdown scope while sharing a single browser surface."""
    documents = [compile_document(source, base) for source in sources]
    body, codes, resources = [], [], set()
    for index, document in enumerate(documents):
        fragment = re.sub(r'data-code="(\d+)"', lambda m: f'data-code="{int(m[1]) + len(codes)}"', document.body)
        fragment = fragment.replace('id="doc-', f'id="doc-{index}-').replace('href="#doc-', f'href="#doc-{index}-')
        body.append('<section>' + fragment + '</section>')
        codes.extend(document.codes)
        resources.update(document.resources)
    return Document('\n'.join(body), codes, resources,
                    any(doc.math for doc in documents), any(doc.mermaid for doc in documents))


def html_page(document, dark=False, display=None, background=None, token=''):
    display = display or {}
    vendor = ASSETS / 'vendor'
    extensions = ''
    if document.math:
        extensions += f'<link rel="stylesheet" href="{(vendor / "katex" / "katex.min.css").as_uri()}">'
        extensions += f'<script defer src="{(vendor / "katex" / "katex.min.js").as_uri()}"></script>'
    if document.mermaid:
        extensions += f'<script defer src="{(vendor / "mermaid" / "mermaid.min.js").as_uri()}"></script>'
    script = (ASSETS / 'document.js').read_text()
    # Content cannot inject executable scripts, base URLs or host bridge calls.
    return ('<!doctype html><html data-theme="' + ('dark' if dark else 'light') + '" '
            'data-border="' + str(bool(display.get('border'))).lower() + '" '
            'data-copy-code="' + str(bool(display.get('copy_code'))).lower() + '" '
            'data-document="' + html.escape(token, quote=True) + '" '
            'style="--host-background:' + html.escape(background or 'transparent', quote=True) + '"><head>'
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'img-src file: https: http: data:; style-src \'unsafe-inline\' file:; '
            'font-src file:; script-src \'unsafe-inline\' file:; connect-src \'none\'">'
            '<style>' + styles() + '</style>' + extensions + '</head><body>'
            '<article class="markdown-body">' + document.body + '</article>'
            '<script>' + script + '</script></body></html>')
