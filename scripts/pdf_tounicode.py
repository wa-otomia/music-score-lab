"""让只读 ToUnicode 的阅读器（Firefox/pdf.js 等）也能复制出正确字符。

Noto Sans CJK 里有不少字形被多个码位共用（例如 ``-`` 与 U+2011、``…`` 与 U+22EF），
xdvipdfmx 生成 ToUnicode 时只能为每个字形挑一个码位，常常挑到不常用的那个。
XeLaTeX 打开 ``\\XeTeXgenerateactualtext`` 后，每段文字都包在
``/Span <</ActualText …>> BDC … TJ … EMC`` 里，记录了排版时真正的字符。
这里逐段把「字形代码 ↔ 实际字符」配对，用文档自己的事实改写各字体的 ToUnicode。
只改动文档里真正出现过、且一一对应的字形；其余映射保持 xdvipdfmx 原样。
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

SPAN = re.compile(rb'/Span\s*<<\s*/ActualText\s*(<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\)])*\))\s*>>\s*BDC(.*?)EMC', re.S)
FONT = re.compile(rb'/(\S+)\s+[\d.]+\s+Tf')
HEX = re.compile(rb'<([0-9A-Fa-f\s]*)>')


def _decode_actual(token: bytes) -> str:
    if token.startswith(b'<'):
        return _decode_bytes(bytes.fromhex(re.sub(rb'\s', b'', token[1:-1]).decode()))
    return _decode_bytes(_unescape_literal(token[1:-1]))


def _decode_bytes(raw: bytes) -> str:
    return raw[2:].decode('utf-16-be') if raw[:2] == b'\xfe\xff' else raw.decode('latin-1')


def _unescape_literal(body: bytes) -> bytes:
    """PDF literal string escapes: \\n \\r \\t \\b \\f \\( \\) \\\\ \\ddd and line continuations."""
    out = bytearray()
    i = 0
    simple = {ord('n'): 10, ord('r'): 13, ord('t'): 9, ord('b'): 8, ord('f'): 12}
    while i < len(body):
        c = body[i]
        if c != 0x5C or i + 1 == len(body):
            out.append(c)
            i += 1
            continue
        nxt = body[i + 1]
        if nxt in simple:
            out.append(simple[nxt])
            i += 2
        elif 0x30 <= nxt <= 0x37:
            j = i + 1
            while j < len(body) and j < i + 4 and 0x30 <= body[j] <= 0x37:
                j += 1
            out.append(int(body[i + 1:j], 8) & 0xFF)
            i = j
        elif nxt in (10, 13):
            i += 2 + (nxt == 13 and i + 2 < len(body) and body[i + 2] == 10)
        else:
            out.append(nxt)
            i += 2
    return bytes(out)


def _parse_cmap(data: bytes) -> dict[int, str]:
    text = data.decode('latin-1')
    out: dict[int, str] = {}
    for block in re.findall(r'beginbfchar(.*?)endbfchar', text, re.S):
        for src, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            out[int(src, 16)] = bytes.fromhex(dst).decode('utf-16-be')
    for block in re.findall(r'beginbfrange(.*?)endbfrange', text, re.S):
        for lo, hi, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]+>|\[[^\]]*\])', block):
            lo_i, hi_i = int(lo, 16), int(hi, 16)
            if dst.startswith('['):
                for k, item in enumerate(re.findall(r'<([0-9A-Fa-f]+)>', dst)):
                    out[lo_i + k] = bytes.fromhex(item).decode('utf-16-be')
            else:
                base = bytes.fromhex(dst[1:-1]).decode('utf-16-be')
                for k in range(hi_i - lo_i + 1):
                    out[lo_i + k] = base[:-1] + chr(ord(base[-1]) + k)
    return out


def _write_cmap(mapping: dict[int, str]) -> bytes:
    lines = ['/CIDInit /ProcSet findresource begin', '12 dict begin', 'begincmap',
             '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
             '/CMapName /Adobe-Identity-UCS def', '/CMapType 2 def',
             '1 begincodespacerange', '<0000> <FFFF>', 'endcodespacerange']
    items = sorted(mapping.items())
    for start in range(0, len(items), 100):
        chunk = items[start:start + 100]
        lines.append(f'{len(chunk)} beginbfchar')
        lines += [f'<{code:04X}> <{text.encode("utf-16-be").hex().upper()}>' for code, text in chunk]
        lines.append('endbfchar')
    lines += ['endcmap', 'CMapName currentdict /CMap defineresource pop', 'end', 'end']
    return '\n'.join(lines).encode('ascii')


def observed_codes(doc: pymupdf.Document) -> dict[int, dict[int, str]]:
    """font xref → {glyph code → character} as recorded by ActualText spans."""
    result: dict[int, dict[int, str]] = {}
    for page in doc:
        names = {f[4]: f[0] for f in page.get_fonts(full=True)}  # resource name → font xref
        content = page.read_contents()
        for actual, body in SPAN.findall(content):
            fonts = FONT.findall(body)
            if len(set(fonts)) != 1:
                continue
            xref = names.get(fonts[0].decode('latin-1'))
            if xref is None:
                continue
            codes_hex = b''.join(h.replace(b' ', b'').replace(b'\n', b'') for h in HEX.findall(body.split(b'Tf', 1)[1]))
            codes = [int(codes_hex[i:i + 4], 16) for i in range(0, len(codes_hex), 4)]
            text = _decode_actual(actual)
            if len(codes) != len(text):
                continue  # ligature or other many-to-one run: leave as is
            for code, char in zip(codes, text):
                result.setdefault(xref, {})[code] = char
    return result


def fix_tounicode(path: Path) -> int:
    """Rewrite ToUnicode maps in place; returns how many entries changed."""
    changed = 0
    with pymupdf.open(path) as doc:
        for xref, observed in observed_codes(doc).items():
            kind, ref = doc.xref_get_key(xref, 'ToUnicode')
            if kind != 'xref':
                continue
            cmap_xref = int(ref.split()[0])
            mapping = _parse_cmap(doc.xref_stream(cmap_xref))
            for code, char in observed.items():
                if mapping.get(code) != char:
                    mapping[code] = char
                    changed += 1
            doc.update_stream(cmap_xref, _write_cmap(mapping))
        doc.save(str(path) + '.tmp', garbage=3, deflate=True)
    Path(str(path) + '.tmp').replace(path)
    return changed


TEXT_BLOCK = re.compile(rb'BT(.*?)ET', re.S)


def tounicode_text(doc: pymupdf.Document, page: pymupdf.Page) -> str:
    """Page text decoded **only** through the fonts' ToUnicode maps, ignoring ActualText —
    what pdf.js (Firefox) and macOS Preview copy.  Assumes 2-byte Identity-H codes, as
    xdvipdfmx writes them."""
    maps: dict[str, dict[int, str]] = {}
    for xref, _ext, _type, _base, name, *_rest in page.get_fonts(full=True):
        kind, ref = doc.xref_get_key(xref, 'ToUnicode')
        maps[name] = _parse_cmap(doc.xref_stream(int(ref.split()[0]))) if kind == 'xref' else {}
    out = []
    for block in TEXT_BLOCK.findall(page.read_contents()):
        fonts = FONT.findall(block)
        if not fonts:
            continue
        mapping = maps.get(fonts[-1].decode('latin-1'), {})
        hexes = b''.join(re.sub(rb'\s', b'', h) for h in HEX.findall(block.split(b'Tf', 1)[1]))
        for i in range(0, len(hexes), 4):
            out.append(mapping.get(int(hexes[i:i + 4], 16), '\ufffd'))
    return ''.join(out)
