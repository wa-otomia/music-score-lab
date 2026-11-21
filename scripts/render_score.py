#!/usr/bin/env python3
"""Engrave an A4 drum PDF via MusiXTeX, then typeset Japanese metadata with PyMuPDF.

No font binaries are committed or bundled. System-provided Japanese fonts are
found with fontconfig or supplied explicitly at the command line.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

import fitz
from fontTools.ttLib import TTFont
from fontTools import subset

from score_core import build_score
from midi_to_musixtex import convert


def find_font(pattern):
    try:
        name = subprocess.check_output(['fc-match', '-f', '%{file}\n', pattern], text=True).strip().splitlines()[0]
        if Path(name).exists(): return name
    except (FileNotFoundError, subprocess.CalledProcessError, IndexError):
        pass
    raise RuntimeError('Japanese font not found: install fonts-noto-cjk or use --font-regular / --font-bold')


def subset_font(font_path: str, font_out: Path, glyph_text: str):
    """Create an *ephemeral* subset of an installed font; never bundle fonts."""
    font = TTFont(font_path, fontNumber=0)
    opts = subset.Options()
    opts.name_IDs = [1, 2, 4, 6]
    opts.name_languages = ['*']
    opts.layout_features = ['*']
    ss = subset.Subsetter(options=opts)
    ss.populate(text=glyph_text)
    ss.subset(font)
    font.save(str(font_out))
    font.close()


def glyph_inventory(meta: dict) -> str:
    return ''.join(str(value) for value in meta.values()) + (
        '収録アルバム：『』 （） 作詞・作曲・歌唱： ドラム採譜・アレンジ： '
        '備考： BPM  | 4/4 冒頭拍の弱起 手：上声部／足：下声部 ｜')


def overlay_credits(input_pdf: Path, output_pdf: Path, meta: dict, pickup: int, regular_font: str, bold_font: str):
    doc = fitz.open(input_pdf)
    def center(page, text, y, size, alias, path):
        font = fitz.Font(fontfile=path)
        w = font.text_length(text, fontsize=size)
        page.insert_text(((page.rect.width - w) / 2, y), text, fontsize=size,
                         fontname=alias, fontfile=path, color=(0.10, 0.12, 0.15), overlay=True)
    title = str(meta.get('title', 'Untitled'))
    artist = str(meta.get('artist', ''))
    transcriber = str(meta.get('transcriber', ''))
    center(doc[0], title, 43, 18.8, 'jp-bold', bold_font)
    center(doc[0], '収録アルバム：『' + str(meta.get('album', '')) + '』  ' + str(meta.get('vocal', artist)), 62, 9.2, 'jp-regular', regular_font)
    center(doc[0], '作詞・作曲・歌唱：' + artist + '　　ドラム採譜・アレンジ：' + transcriber, 78, 9.2, 'jp-regular', regular_font)
    center(doc[0], '備考：' + str(meta.get('note', '')), 93, 8.5, 'jp-regular', regular_font)
    center(doc[0], 'BPM ' + str(meta.get('tempo_bpm', 120)) + '  |  4/4  |  冒頭' + str(pickup) + '拍の弱起  |  手：上声部／足：下声部', 107, 8.2, 'jp-regular', regular_font)
    for p in doc[1:]:
        center(p, title + '    ' + artist + '    ｜    ドラム採譜・アレンジ：' + transcriber, 24, 8, 'jp-regular', regular_font)
    doc.set_metadata({'title': title + ' - ドラム譜', 'author': artist + ' / ' + transcriber,
                      'subject': str(meta.get('album', '')) + ' - Drum transcription',
                      'creator': 'MusiXTeX / PyMuPDF; automated from MIDI'})
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_pdf, garbage=4, deflate=True)
    pages = len(doc)
    doc.close()
    return pages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/japanese-drums.yaml')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--font-regular', default=None)
    parser.add_argument('--font-bold', default=None)
    parser.add_argument('--keep-tex', type=Path, default=None, help='Optional path to retain the generated MusiXTeX source')
    args = parser.parse_args()
    if not shutil.which('musixtex'):
        parser.error('musixtex is required. Install TeX Live/MusiXTeX first.')
    score = build_score(args.midi, args.metadata, args.drum_map)
    regular = args.font_regular or find_font('Noto Sans CJK JP:style=Regular')
    bold = args.font_bold or find_font('Noto Sans CJK JP:style=Bold')
    content = convert(score)
    if args.keep_tex:
        args.keep_tex.parent.mkdir(parents=True, exist_ok=True)
        args.keep_tex.write_text(content, encoding='ascii')
    with tempfile.TemporaryDirectory(prefix='drum-engrave-') as tmp:
        work = Path(tmp)
        tex = work / 'score.tex'
        tex.write_text(content, encoding='ascii')
        process = subprocess.run(['musixtex', tex.name], cwd=work, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        pdf = work / 'score.pdf'
        if process.returncode or not pdf.is_file():
            raise RuntimeError('MusiXTeX failed:\n' + process.stdout[-5000:])
        # Avoid embedding ~14 MB CJK collections per weight in every PDF.
        font_text = glyph_inventory(score.metadata)
        regular_subset = work / 'jp-regular-subset.otf'
        bold_subset = work / 'jp-bold-subset.otf'
        subset_font(regular, regular_subset, font_text)
        subset_font(bold, bold_subset, font_text)
        pages = overlay_credits(pdf, args.out, score.metadata,
                                score.pickup_ticks // score.tpq,
                                str(regular_subset), str(bold_subset))
    print(f'{args.out}: {pages} pages, {len(score.bars)} measures')

if __name__ == '__main__': main()
