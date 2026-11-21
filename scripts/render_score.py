#!/usr/bin/env python3
"""Drum MIDI + metadata -> printable PDF.

Pipeline (every step is reproducible; no font files are committed):

1. ``score_core`` reads the MIDI, quantizes and splits bars (same model as the MusicXML output).
2. XeLaTeX first typesets the header block (title, credits, note, legend) to measure its height.
3. MusiXTeX (``musixtex -d``: etex -> musixflx -> etex -> dvipdfmx) engraves the score; the top of page 1 is left blank by
   the header height; each legend notehead is typeset as a tiny staff and cropped.
4. Ghostscript ``-dNoOutputFonts`` turns all glyphs on the staff (notes, rests, bar numbers) into vector paths,
   so copying from the staff no longer yields garbage.
5. XeLaTeX + pdfpages place the vector pages into the final PDF and overlay **real text**: header block, legend text,
   running heads and page numbers. xdvipdfmx embeds a Noto Sans CJK JP subset (CID font + ToUnicode),
   so the text can be selected, copied and searched.

Requires: MusiXTeX (texlive-music), XeLaTeX + xeCJK + pdfpages, Ghostscript, and a locally installed
Noto Sans CJK JP (fonts-noto-cjk).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from score_core import ScoreError, Transcription, build_score
from midi_to_musixtex import convert, legend_entries, legend_tex
from pdf_tounicode import fix_tounicode

PAGE_W, PAGE_H = 595.276, 841.89          # A4 in PostScript points
CONTENT_LEFT, CONTENT_WIDTH = 28.35, 538.6  # MusiXTeX: \hoffset-15.4mm, \hsize190mm
NOTATION_TOP = 60.6                         # top of the first system on a page (\voffset-6mm)
HEADER_TOP = 30.0                           # first-page title block starts here
HEADER_GAP = 12.0                           # space between the title block and the first system
TOOLS = ('musixtex', 'etex', 'musixflx', 'dvipdfmx', 'xelatex', 'gs')

TEX_ESCAPES = {
    '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_',
    '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
}

ROLE_LABELS = {
    'lyricist': '作詞', 'composer': '作曲', 'vocal': '歌', 'arranger': 'ドラム編曲',
    'transcriber': 'ドラム採譜', 'artist': 'アーティスト', 'album': 'アルバム', 'note': '備考',
}


def escape_tex(text: object) -> str:
    """Escape for XeLaTeX; line breaks and runs of whitespace become one space."""
    flat = re.sub(r'[ \t\r\n\f\v]+', ' ', str(text)).strip()  # keep U+3000 ideographic spaces
    return ''.join(TEX_ESCAPES.get(c, c) for c in flat)


def check_glyphs(log: Path) -> None:
    """XeTeX only logs characters the font lacks; they would print as empty boxes."""
    missing = sorted(set(re.findall(r'Missing character: There is no (.+?) \(', log.read_text(errors='replace'))))
    if missing:
        raise RuntimeError(f'The font {FONT} has no glyph for these characters, so the PDF would show boxes: {", ".join(missing)}. '
                           'Use a different spelling in the metadata (e.g. remove emoji).')


def run(command: list[str], cwd: Path, *, max_log: int = 4000) -> str:
    try:
        process = subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, errors='replace', timeout=600)
    except FileNotFoundError:
        raise RuntimeError(f'Command not found: {command[0]}; install the dependencies listed in the README') from None
    if process.returncode != 0:
        raise RuntimeError(f'{" ".join(command)} failed (exit code {process.returncode}):\n{process.stdout[-max_log:]}')
    return process.stdout


def check_tools() -> None:
    missing = [t for t in TOOLS if not shutil.which(t)]
    if missing:
        raise RuntimeError('Missing commands: ' + ', '.join(missing) + '. On Debian/Ubuntu install texlive-music texlive-xetex '
                           'texlive-lang-cjk texlive-latex-recommended ghostscript fonts-noto-cjk')


# --------------------------------------------------------------------------- header text

@dataclass
class HeaderText:
    title: str
    lines: list[tuple[float, str]]   # (font size, plain text) below the title
    running: str                     # continuation-page header
    footer_note: str                 # first-page footer (copyright), may be empty

    def plain_strings(self) -> list[str]:
        """Every string that must be extractable from the PDF, for verification."""
        out = [self.title] + [t for _, t in self.lines]
        if self.footer_note:
            out.append(self.footer_note)
        return out


def merged_roles(meta: dict, roles: list[str], labels: dict[str, str]) -> str:
    """'作詞・作曲：A　歌：B' — roles credited to the same person share one label."""
    groups: list[tuple[list[str], str]] = []
    for role in roles:
        value = str(meta.get(role) or '').strip()
        if not value:
            continue
        for names, existing in groups:
            if existing == value:
                names.append(labels[role])
                break
        else:
            groups.append(([labels[role]], value))
    def label(names: list[str]) -> str:
        # 'ドラム採譜・ドラム編曲' -> 'ドラム採譜・編曲'
        out = names[:1] + [n.removeprefix('ドラム') if names[0].startswith('ドラム') else n for n in names[1:]]
        return '・'.join(out)
    return '　'.join(label(names) + '：' + value for names, value in groups)


def header_text(score: Transcription) -> HeaderText:
    meta = score.metadata
    labels = dict(ROLE_LABELS)
    labels.update({k: str(v) for k, v in (meta.get('credits') or {}).items() if k in ROLE_LABELS})
    title = str(meta.get('title') or 'Untitled')
    lines: list[tuple[float, str]] = []
    if meta.get('subtitle'):
        lines.append((11.0, str(meta['subtitle'])))
    artist_line = '　'.join(x for x in (
        str(meta.get('artist') or ''),
        f'『{meta["album"]}』' if meta.get('album') else '') if x)
    if artist_line:
        lines.append((10.5, artist_line))
    song = merged_roles(meta, ['lyricist', 'composer', 'vocal'], labels)
    if song:
        lines.append((9.0, song))
    drums = merged_roles(meta, ['transcriber', 'arranger'], labels)
    if drums:
        lines.append((9.0, drums))
    if meta.get('note'):
        lines.append((8.5, labels['note'] + '：' + str(meta['note'])))
    lines.append((8.5, f'BPM {score.tempo_bpm:g}'))
    running = '　'.join(x for x in (title, str(meta.get('artist') or ''), 'ドラム譜') if x)
    return HeaderText(title, lines, running, str(meta.get('copyright') or ''))


def expected_page_text(score: Transcription, pages: int) -> list[list[str]]:
    """The only text each page may contain, in content order (used by validate_score.py)."""
    header = header_text(score)
    first = [header.title] + [t for _, t in header.lines]
    if score.metadata.get('legend', False):
        first.append('凡例')
        for _notes, inst in legend_entries(score):
            first += [inst.abbr, inst.name_ja]
    first.append(f'1 / {pages}')
    if header.footer_note:
        first.append(header.footer_note)
    return [first] + [[header.running, f'{i} / {pages}'] for i in range(2, pages + 1)]


def legend_cells(score: Transcription, legend_pdf: str | None) -> str:
    if legend_pdf is None:
        return ''
    entries = legend_entries(score)
    width = max(44.0, min(58.0, (CONTENT_WIDTH - 4) / max(1, len(entries)) - 3))
    cells = []
    for page, (_notes, inst) in enumerate(entries, start=1):
        main, paren, rest = inst.name_ja.partition('（')
        name = r'\FitLine{' + escape_tex(main) + '}' + (r'\par\FitLine{' + escape_tex(paren + rest) + '}' if paren else '')
        cells.append(r'\LegendCell{' + f'{width:.1f}' + '}{' + str(page) + '}{' + escape_tex(inst.abbr) + '}{' + name + '}')
    return (r'\par\vspace{5pt}{\fontsize{7.5}{9}\selectfont 凡例\par}\vspace{1pt}'
            + r'\hspace{3bp}'.join(cells) + r'\par')


def latex_preamble(score: Transcription, header: HeaderText) -> str:
    meta = score.metadata
    header_lines = ''.join('  {\\fontsize{%s}{%s}\\selectfont %s\\par}\n' % (size, size + 4, escape_tex(text))
                           for size, text in header.lines)
    author = ' / '.join(dict.fromkeys(str(meta[k]) for k in ('transcriber', 'arranger') if meta.get(k)))
    subject = ' / '.join(str(meta[k]) for k in ('artist', 'album') if meta.get(k))
    return rf"""\documentclass[10pt]{{article}}
\usepackage[paperwidth={PAGE_W}bp,paperheight={PAGE_H}bp,margin=0pt]{{geometry}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\usepackage{{graphicx}}
\usepackage{{pdfpages}}
\usepackage[unicode,hidelinks]{{hyperref}}
\XeTeXgenerateactualtext=1
\xeCJKsetup{{CJKecglue={{}},CJKspace=true}}  % no automatic gap between kanji and Latin: copy text exactly as written
\setmainfont{{{FONT}}}[BoldFont={{{FONT} Bold}},Mapping=none,Ligatures={{NoCommon,NoRequired,NoContextual}}]
\setCJKmainfont{{{FONT}}}[BoldFont={{{FONT} Bold}},Mapping=none,Ligatures={{NoCommon,NoRequired,NoContextual}}]
\hypersetup{{pdftitle={{{escape_tex(header.title)} ドラム譜}},pdfauthor={{{escape_tex(author)}}},
  pdfsubject={{{escape_tex(subject)}}},pdfkeywords={{drum score, ドラム譜, MusicXML}},
  pdfcreator={{music-score-lab (MusiXTeX + Ghostscript + XeLaTeX)}}}}
\pagestyle{{empty}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\unitlength}}{{1bp}}
\newcommand\LegendCell[4]{{\parbox[t]{{#1bp}}{{\centering
  \includegraphics[page=#2,height=26bp]{{legend-cells.pdf}}\par\vspace{{1bp}}
  {{\fontsize{{6.5}}{{8}}\selectfont #3\par #4\par}}}}}}
\newsavebox\FitBox
\newcommand\FitLine[1]{{\sbox\FitBox{{#1}}\ifdim\wd\FitBox>\dimexpr\linewidth-3bp\relax
  \resizebox{{\dimexpr\linewidth-3bp\relax}}{{!}}{{#1}}\else#1\fi}}
\newcommand\FitBlock[1]{{\makebox[{CONTENT_WIDTH}bp]{{\sbox\FitBox{{#1}}\ifdim\wd\FitBox>{CONTENT_WIDTH}bp\resizebox{{{CONTENT_WIDTH}bp}}{{!}}{{#1}}\else#1\fi}}}}
\newsavebox\HeaderBox
\newcommand\MakeHeader{{\sbox\HeaderBox{{\begin{{minipage}}[b]{{{CONTENT_WIDTH}bp}}\centering
  {{\fontsize{{20}}{{25}}\selectfont\bfseries {escape_tex(header.title)}\par}}\vspace{{3pt}}
{header_lines}  LEGEND
\end{{minipage}}}}}}
"""


FONT = 'Noto Sans CJK JP'


def header_source(score: Transcription, header: HeaderText, legend: bool) -> str:
    return latex_preamble(score, header).replace('LEGEND', legend_cells(score, 'legend-cells.pdf' if legend else None))


def measure_header(work: Path, score: Transcription, header: HeaderText, legend: bool) -> float:
    source = header_source(score, header, legend) + r"""\begin{document}
\MakeHeader
\newwrite\out\immediate\openout\out=header-height.txt
\immediate\write\out{\the\dimexpr\ht\HeaderBox+\dp\HeaderBox\relax}
\immediate\closeout\out
\mbox{}
\end{document}
"""
    (work / 'header.tex').write_text(source, encoding='utf-8')
    run(['xelatex', '-interaction=nonstopmode', '-halt-on-error', 'header.tex'], work)
    check_glyphs(work / 'header.log')
    text = (work / 'header-height.txt').read_text().strip()
    return float(text.removesuffix('pt')) * 72 / 72.27  # TeX pt -> PDF bp


def compose(work: Path, score: Transcription, header: HeaderText, legend: bool, pages: int, out: Path) -> None:
    head_y = PAGE_H - HEADER_TOP
    footer = rf'\put(0,22){{\makebox[{PAGE_W}bp]{{\fontsize{{8}}{{9}}\selectfont\thepage\ / {pages}}}}}'
    first = (rf'\put({CONTENT_LEFT},{head_y:.2f}){{\raisebox{{-\height}}{{\usebox\HeaderBox}}}}' + footer
             + (rf'\put({CONTENT_LEFT},36){{\FitBlock{{\fontsize{{7}}{{8}}\selectfont {escape_tex(header.footer_note)}}}}}'
                if header.footer_note else ''))
    running = (rf'\put({CONTENT_LEFT},{PAGE_H - 34:.2f}){{\FitBlock{{\fontsize{{8}}{{9}}\selectfont '
               rf'{escape_tex(header.running)}}}}}' + footer)
    body = rf"""\begin{{document}}
\MakeHeader
\includepdf[pages=1,picturecommand*={{{first}}}]{{notes.pdf}}
"""
    if pages > 1:
        body += rf"\includepdf[pages=2-,picturecommand={{{running}}}]{{notes.pdf}}" + '\n'
    body += r'\end{document}' + '\n'
    (work / 'compose.tex').write_text(header_source(score, header, legend) + body, encoding='utf-8')
    run(['xelatex', '-interaction=nonstopmode', '-halt-on-error', 'compose.tex'], work)
    check_glyphs(work / 'compose.log')
    fix_tounicode(work / 'compose.pdf')
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work / 'compose.pdf', out)


def outline(src: Path, dst: Path, work: Path) -> None:
    run(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-sDEVICE=pdfwrite', '-dNoOutputFonts',
         '-dAutoRotatePages=/None', f'-sOutputFile={dst}', str(src)], work)


def musixtex(work: Path, name: str, source: str) -> Path:
    (work / f'{name}.tex').write_text(source, encoding='ascii')
    run(['musixtex', '-d', '-i', f'{name}.tex'], work)
    pdf = work / f'{name}.pdf'
    if not pdf.exists():
        raise RuntimeError(f'MusiXTeX did not produce {pdf.name}; see {work / (name + ".log")}')
    return pdf


def crop_legend(src: Path, dst: Path) -> None:
    """Crop every legend page to the same band measured from its top staff line, so the
    staves line up across cells whatever sits above or below them."""
    with pymupdf.open(src) as doc:
        boxes = []
        for page in doc:
            rects = [d['rect'] for d in page.get_drawings()]
            staff = [r for r in rects if r.width > 40 and r.height < 1.5]
            top = min(r.y0 for r in staff) if staff else min(r.y0 for r in rects)
            boxes.append((min(r.x0 for r in rects), max(r.x1 for r in rects), top,
                          top - min(r.y0 for r in rects), max(r.y1 for r in rects) - top))
        above = max(b[3] for b in boxes) + 1
        below = max(b[4] for b in boxes) + 1
        for page, (x0, x1, top, _a, _b) in zip(doc, boxes):
            page.set_cropbox(pymupdf.Rect(x0 - 1, top - above, x1 + 1, top + below))
        doc.save(dst)


def render(score: Transcription, out: Path, work: Path, *, keep_tex: Path | None = None) -> dict:
    check_tools()
    header = header_text(score)
    legend = bool(score.metadata.get('legend', False))
    if legend:
        raw = musixtex(work, 'legend', legend_tex(score))
        outline(raw, work / 'legend-outlined.pdf', work)
        crop_legend(work / 'legend-outlined.pdf', work / 'legend-cells.pdf')
    height = measure_header(work, score, header, legend)
    space = max(0.0, HEADER_TOP + height + HEADER_GAP - NOTATION_TOP)
    source = convert(score, header_space=space)
    if keep_tex:
        keep_tex.parent.mkdir(parents=True, exist_ok=True)
        keep_tex.write_text(source, encoding='ascii')
    engraved = musixtex(work, 'score', source)
    log = (work / 'score.log').read_text(errors='replace') if (work / 'score.log').exists() else ''
    overfull = [float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
    if overfull and max(overfull) > 4:
        score.warnings.append(f'{len(overfull)} staff line(s) slightly exceed the text width (by up to {max(overfull):.1f}pt); please check visually')
    outline(engraved, work / 'notes.pdf', work)
    with pymupdf.open(work / 'notes.pdf') as doc:
        pages = len(doc)
    compose(work, score, header, legend, pages, out)
    return {'pages': pages, 'header_height': height, 'header_strings': header.plain_strings()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Drum MIDI + metadata -> PDF drum score')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', help='bundled map name (gm, fpc-default) or YAML path')
    parser.add_argument('--track', action='append', help='use only tracks whose name contains this text (repeatable)')
    parser.add_argument('--channel', action='append', type=int, help='use only this MIDI channel, 1-16 (repeatable)')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--legend', action=argparse.BooleanOptionalAction, default=None,
                        help='print (--legend) or omit (--no-legend) the instrument legend; default follows the metadata legend, omitted if unset')
    parser.add_argument('--keep-tex', type=Path, help='also save the generated MusiXTeX source (for debugging)')
    parser.add_argument('--work-dir', type=Path, help='directory to keep intermediate files (default: a temp dir deleted afterwards)')
    args = parser.parse_args(argv)
    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel})
        if args.legend is not None:
            score.metadata['legend'] = args.legend
        if args.work_dir:
            args.work_dir.mkdir(parents=True, exist_ok=True)
            info = render(score, args.out, args.work_dir.resolve(), keep_tex=args.keep_tex)
        else:
            with tempfile.TemporaryDirectory(prefix='drum-score-') as temp:
                info = render(score, args.out, Path(temp), keep_tex=args.keep_tex)
    except (ScoreError, RuntimeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    for warning in score.warnings:
        print(f'Note: {warning}', file=sys.stderr)
    print(f'{args.out}: A4, {info["pages"]} page(s); {score.summary()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
