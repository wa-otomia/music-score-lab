#!/usr/bin/env python3
"""Reproducible Japanese percussion PDF engraving.

MusiXTeX draws the musical notation. XeLaTeX/xeCJK typesets Japanese credits,
then Inkscape outlines *the text only* to vector paths before compositing it
onto the score. Outlines avoid PDF.js/Preview CJK font-subsetting bugs without
rasterizing the notes or distributing any font binaries.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz

from score_core import build_score
from midi_to_musixtex import convert


TEX_ESCAPES = {
    '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
    '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
}


def escape_tex(text: str) -> str:
    return ''.join(TEX_ESCAPES.get(char, char) for char in str(text))


def run(command: list[str], cwd: Path, *, max_log: int = 6000) -> None:
    process = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors='replace')
    if process.returncode != 0:
        raise RuntimeError(f'{command[0]} exited {process.returncode}:\n{process.stdout[-max_log:]}')


def latex_header(meta: dict, pickup_beats: int, font_family: str, *, continuation: bool) -> str:
    title = escape_tex(meta.get('title', 'Untitled'))
    album = escape_tex(meta.get('album', ''))
    vocal = escape_tex(meta.get('vocal', meta.get('artist', '')))
    artist = escape_tex(meta.get('artist', ''))
    transcriber = escape_tex(meta.get('transcriber', ''))
    note = escape_tex(meta.get('note', ''))
    bpm = escape_tex(meta.get('tempo_bpm', 120))

    def textblock(y: int, fontsize: float, content: str, *, bold: bool = False) -> str:
        weight = r'\bfseries ' if bold else ''
        # XeLaTeX: textpos positions objects in absolute top-left page coordinates.
        return (r'\begin{textblock*}{595pt}(0pt,' + str(y) + 'pt)\n'
                + r'\centering {\fontsize{' + str(fontsize) + r'}{' + str(fontsize + 3.0)
                + r'}\selectfont ' + weight + content + r'}' + '\n'
                + r'\end{textblock*}' + '\n')

    if continuation:
        blocks = textblock(13, 8.2, title + r'\quad ' + artist + r'\quad 採譜・アレンジ：' + transcriber)
    else:
        blocks = (textblock(17, 19.5, title, bold=True)
                  + textblock(50, 9.0, '収録アルバム：『' + album + '』  ' + vocal)
                  + textblock(65, 9.0, '作詞・作曲・歌唱：' + artist + r'\quad ドラム採譜・アレンジ：' + transcriber)
                  + textblock(80, 8.6, '備考：' + note)
                  + textblock(97, 8.3, 'BPM ' + bpm + r'\quad '
                              + (str(pickup_beats) + '/4（冒頭のみ）→ 4/4' if pickup_beats else '4/4')
                              + r'\quad 手：上声部／足：下声部'))
    return (r'\documentclass[a4paper,10pt]{article}' + '\n'
            + r'\usepackage{fontspec}' + '\n'
            + r'\usepackage{xeCJK}' + '\n'
            + r'\usepackage[absolute,overlay]{textpos}' + '\n'
            + r'\setmainfont{' + escape_tex(font_family) + '}' + '\n'
            + r'\setCJKmainfont{' + escape_tex(font_family) + '}' + '\n'
            + r'\pagestyle{empty}' + '\n'
            + r'\setlength{\parindent}{0pt}' + '\n'
            + r'\textblockorigin{0pt}{0pt}' + '\n'
            + r'\begin{document}' + '\n'
            + r'\mbox{}' + '\n'
            + blocks
            + r'\end{document}' + '\n')


def make_outlined_header(work: Path, meta: dict, pickup_beats: int,
                         font_family: str, *, continuation: bool) -> Path:
    stem = 'continuation_header' if continuation else 'first_header'
    source = work / f'{stem}.tex'
    source.write_text(latex_header(meta, pickup_beats, font_family,
                                   continuation=continuation), encoding='utf-8')
    run(['xelatex', '-interaction=nonstopmode', '-halt-on-error',
         '-output-directory', str(work), source.name], work)
    outlined = work / f'{stem}_outlined.pdf'
    run(['inkscape', str(work / (stem + '.pdf')), '--export-text-to-path',
         '--export-filename=' + str(outlined)], work)
    # A font-free vector header renders identically in PDF.js, Preview and Poppler.
    with fitz.open(outlined) as verify:
        if len(verify) != 1 or verify[0].get_fonts():
            raise RuntimeError('Header must be a single vector-outlined page with no fonts')
    return outlined


def engrave_pdf(base_pdf: Path, final_pdf: Path, score, work: Path, font_family: str) -> int:
    first = make_outlined_header(work, score.metadata, score.pickup_ticks // score.tpq,
                                font_family, continuation=False)
    rest = make_outlined_header(work, score.metadata, score.pickup_ticks // score.tpq,
                               font_family, continuation=True)
    with fitz.open(base_pdf) as doc, fitz.open(first) as first_doc, fitz.open(rest) as rest_doc:
        for idx, page in enumerate(doc):
            overlay = first_doc if idx == 0 else rest_doc
            page.show_pdf_page(page.rect, overlay, 0, overlay=True)
        meta = score.metadata
        doc.set_metadata({
            'title': str(meta.get('title', '')) + ' | ドラム譜',
            'author': str(meta.get('artist', '')) + ' / ' + str(meta.get('transcriber', '')),
            'subject': str(meta.get('album', '')) + ' | ' + str(meta.get('note', '')),
            'creator': 'MusiXTeX / XeLaTeX + Inkscape vector outlines / PyMuPDF',
            'keywords': 'MusicXML, drum score, Japanese, MIDI',
        })
        final_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(final_pdf, garbage=4, deflate=True, deflate_images=True)
        return len(doc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'configs/japanese-drums.yaml')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--font-family', default='Noto Sans CJK JP',
                        help='Installed font family for Japanese credits; no font file is committed')
    parser.add_argument('--keep-tex', type=Path, default=None,
                        help='Optional path to retain the generated MusiXTeX source')
    args = parser.parse_args()
    for dependency in ('musixtex', 'xelatex', 'inkscape'):
        if not shutil.which(dependency):
            parser.error(f'{dependency} required; install MusiXTeX, XeLaTeX, Inkscape and Japanese fonts')
    score = build_score(args.midi, args.metadata, args.drum_map)
    source = convert(score)
    if args.keep_tex:
        args.keep_tex.parent.mkdir(parents=True, exist_ok=True)
        args.keep_tex.write_text(source, encoding='ascii')
    with tempfile.TemporaryDirectory(prefix='drum-score-') as temp:
        work = Path(temp)
        tex = work / 'score.tex'
        tex.write_text(source, encoding='ascii')
        run(['musixtex', 'score.tex'], work)
        engraved = work / 'score.pdf'
        if not engraved.exists():
            raise RuntimeError('MusiXTeX did not create score.pdf')
        pages = engrave_pdf(engraved, args.out, score, work, args.font_family)
    print(f'{args.out}: {pages} A4 pages, {len(score.bars)} measures, first measure '
          f'{score.pickup_ticks // score.tpq}/4 when present')


if __name__ == '__main__':
    main()
