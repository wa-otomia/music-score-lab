"""End-to-end PDF builds (MusiXTeX + Ghostscript + XeLaTeX).  Two builds, ~10 s each.

Set ``PDFJS_TEXT`` to a pdf.js text-extractor script (``node SCRIPT file.pdf`` printing
``--- page N`` then the page's text items joined by ``|``) to also check pdf.js copy text.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pymupdf
import pytest
import yaml

from conftest import HAVE_PDF_TOOLS, HH, HHO, KICK, SNARE, build, make_midi
import build_score
import render_score
from pdf_tounicode import tounicode_text
from validate_score import normalize, validate_pdf

pytestmark = pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs musixtex, etex, musixflx, dvipdfmx, xelatex, gs')

META = {
    'title': '夜明け - 前…テスト',
    'subtitle': '前編／後編',
    'artist': '作者・名前',
    'album': '試験盤',
    'composer': '作者・名前',
    'lyricist': '作者・名前',
    'vocal': '歌い手',
    'transcriber': '採譜者',
    'arranger': '採譜者',
    'note': '本譜は試験用（『見本』・非売品）- 以上…',
}
# What a reader must copy from page 1, in order (render_score.header_text + legend + page number).
EXPECTED_HEADER = [
    '夜明け - 前…テスト',
    '前編／後編',
    '作者・名前　『試験盤』',
    '作詞・作曲：作者・名前　歌：歌い手',
    'ドラム採譜・編曲：採譜者',
    '備考：本譜は試験用（『見本』・非売品）- 以上…',
    'BPM 128　拍子 4/4　上声部（符尾上）＝手　下声部（符尾下）＝足',
]


def groove(bars):
    hits = []
    for b in range(bars):
        o = 4 * b
        hits += [(o + x / 2, HH) for x in range(8)] + [(o, KICK), (o + 2.5, KICK), (o + 1, SNARE), (o + 3, SNARE)]
        if b % 4 == 3:
            hits += [(o + 3.5, HHO), (o + 3.75, SNARE)]
    return hits


@pytest.fixture(scope='module')
def small_pdf(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('pdf-small')
    score = build(tmp, groove(4), META, sigs=[(0, 4, 4)], tempo=128)
    out = tmp / 'score.pdf'
    work = tmp / 'work'
    work.mkdir()
    info = render_score.render(score, out, work)
    return score, out, info


def test_header_text_model(small_pdf):
    score, _out, _info = small_pdf
    header = render_score.header_text(score)
    assert [header.title] + [t for _, t in header.lines] == EXPECTED_HEADER
    assert header.running == '夜明け - 前…テスト　作者・名前　ドラム譜'


def test_validate_pdf_passes(small_pdf):
    score, out, info = small_pdf
    assert info['pages'] == 1
    assert validate_pdf(score, out).startswith('PDF OK')


def test_tounicode_text_equals_expected_header(small_pdf):
    score, out, _info = small_pdf
    legend = []
    for _notes, inst in render_score.legend_entries(score):
        legend += [inst.abbr, inst.name_ja]
    want = normalize(''.join(EXPECTED_HEADER + ['凡例'] + legend + ['1 / 1']))
    with pymupdf.open(out) as doc:
        got = normalize(tounicode_text(doc, doc[0]))
    assert got == want
    # the characters that Noto Sans CJK shares between code points must come back as typed
    for ch in '-…・／『』':
        assert got.count(ch) == want.count(ch), ch
    for wrong in '‑‐⋯・∕':
        if wrong not in want:
            assert wrong not in got, hex(ord(wrong))


def test_only_noto_cjk_fonts(small_pdf):
    _score, out, _info = small_pdf
    with pymupdf.open(out) as doc:
        fonts = {f[3] for page in doc for f in page.get_fonts(full=True)}
        assert fonts and all('NotoSansCJK' in f for f in fonts), fonts
        for page in doc:
            assert not page.get_images(full=True)
            assert page.get_drawings()


def test_pdf_metadata(small_pdf):
    _score, out, _info = small_pdf
    with pymupdf.open(out) as doc:
        assert doc.metadata['title'] == '夜明け - 前…テスト ドラム譜'
        assert doc.metadata['author'] == '採譜者'


@pytest.mark.skipif(not (os.environ.get('PDFJS_TEXT') and shutil.which('node')),
                    reason='set PDFJS_TEXT to a pdf.js text extractor script')
def test_pdfjs_copy_text(small_pdf):
    score, out, info = small_pdf
    proc = subprocess.run(['node', os.environ['PDFJS_TEXT'], str(out)], capture_output=True, text=True,
                          check=True, timeout=120)
    pages = re.split(r'^--- page \d+\n', proc.stdout, flags=re.M)[1:]
    want = render_score.expected_page_text(score, info['pages'])
    assert [normalize(p.replace('|', '')) for p in pages] == [normalize(''.join(w)) for w in want]


def test_build_score_cli_multipage(tmp_path):
    """The one-command entry point: MusicXML + PDF + both validations, multi-page with footer."""
    midi = make_midi(tmp_path / 'song.mid', [(0, SNARE), (0.5, SNARE)] + [(b + 1, n) for b, n in groove(44)],
                     sigs=[(0, 1, 4), (1, 4, 4)], tempo=140, channel=1, name='FPC 1')
    meta = dict(META, drum_map='fpc-default', pickup_beats=1, source_leading_beats=1, copyright='© テスト・配布可')
    meta_path = tmp_path / 'meta.yaml'
    meta_path.write_text(yaml.safe_dump(meta, allow_unicode=True), encoding='utf-8')
    out = tmp_path / 'out'
    code = build_score.main([str(midi), '--metadata', str(meta_path), '--out-dir', str(out),
                             '--work-dir', str(tmp_path / 'work')])
    assert code == 0
    assert (out / 'score.musicxml').exists()
    with pymupdf.open(out / 'score.pdf') as doc:
        pages = len(doc)
        assert pages >= 2
        second = normalize(tounicode_text(doc, doc[1]))
        first = normalize(tounicode_text(doc, doc[0]))
    assert second == normalize(f'夜明け - 前…テスト　作者・名前　ドラム譜2 / {pages}')
    assert normalize('© テスト・配布可') in first
    assert (tmp_path / 'work' / 'score.tex').exists()

