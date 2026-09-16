"""Bundled typography shared by native controls and Markdown documents."""

import ctypes
import ctypes.util
from functools import lru_cache
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / 'assets' / 'fonts'


@lru_cache(maxsize=1)
def register_fonts():
    """Register fonts in this process, without installing them on the system."""
    from gi.repository import PangoCairo

    font_map = PangoCairo.FontMap.get_default()
    paths = sorted((*FONTS.glob('*.otf'), *FONTS.glob('*.ttf')))
    if hasattr(font_map, 'add_font_file'):
        for path in paths:
            if not font_map.add_font_file(str(path)):
                raise RuntimeError(f'Cannot load bundled font: {path.name}')
        return
    fontconfig = ctypes.CDLL(ctypes.util.find_library('fontconfig'))
    add = fontconfig.FcConfigAppFontAddFile
    add.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    add.restype = ctypes.c_int
    for path in paths:
        if not add(None, str(path).encode()):
            raise RuntimeError(f'Cannot load bundled font: {path.name}')
    font_map.changed()


def document_fonts():
    rules = []
    for family, stem in [('Pretendard', 'Pretendard'), ('D2Coding', 'D2Coding')]:
        for weight, suffix in [(400, 'Regular'), (700, 'Bold')]:
            path = next(FONTS.glob(f'{stem}-{suffix}.*'))
            rules.append(f'@font-face {{ font-family: "{family}"; font-weight: {weight}; '
                         f'src: url("{path.as_uri()}"); }}')
    return '\n'.join(rules)
