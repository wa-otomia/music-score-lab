#!/usr/bin/env python3
"""校验生成的 MusicXML 与 PDF 是否忠实于 MIDI 模型。

MusicXML：
- （提供 XSD 时）符合 MusicXML 4.0 schema；
- 小节数、拍号、弱起与模型一致；每个声部每小节的时值总和等于小节长度；
- 每个 MIDI 音符的记谱次数与模型一致；带横梁的音符层级与其时值相符。

PDF：
- 所有字体都已嵌入、带 ToUnicode，且只有标题用的日文字体（谱面字形已转为路径）；
- 每页能提取的文字**恰好**是标题区 / 图例 / 页眉 / 页码，谱面不产生任何可复制字符；
- 有矢量谱面，没有位图。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from score_core import R, ScoreError, Transcription, build_score, voice_items

BEAM_LEVELS = {'eighth': 1, '16th': 2, '32nd': 3}


class ValidationError(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_musicxml(score: Transcription, path: Path, xsd: Path | None = None) -> str:
    if xsd is not None:
        from lxml import etree
        schema = etree.XMLSchema(etree.parse(str(xsd)))
        doc = etree.parse(str(path))
        if not schema.validate(doc):
            errors = '; '.join(f'line {e.line}: {e.message}' for e in list(schema.error_log)[:5])
            raise ValidationError(f'MusicXML 不符合 XSD：{errors}')
    root = ET.parse(path).getroot()
    check(root.tag == 'score-partwise', '根元素必须是 score-partwise')
    measures = root.findall('part/measure')
    check(len(measures) == len(score.bars), f'小节数 {len(measures)} ≠ 模型 {len(score.bars)}')
    divisions = int(root.findtext('part/measure/attributes/divisions'))
    check(divisions == R, f'divisions 应为 {R}')
    counts: Counter = Counter()
    for bar, measure in zip(score.bars, measures):
        where = f'第 {bar.number} 小节'
        check(measure.get('number') == str(bar.number), f'{where}: number 属性不符')
        check((measure.get('implicit') == 'yes') == bar.pickup, f'{where}: 弱起 implicit 标记不符')
        beats = measure.findtext('attributes/time/beats')
        if bar.index == 0 or bar.show_meter:
            check(beats == str(bar.beats), f'{where}: 拍号应为 {bar.beats}/4，得到 {beats}')
        else:
            check(beats is None, f'{where}: 不应重复拍号')
        spans: Counter = Counter()
        for note in measure.findall('note'):
            grace = note.find('grace') is not None
            chord = note.find('chord') is not None
            voice = int(note.findtext('voice'))
            if not grace and not chord:
                spans[voice] += int(note.findtext('duration'))
            if note.find('rest') is None and not grace:
                inst = note.find('instrument').get('id')
                counts[int(inst.rsplit('I', 1)[1])] += 1
                check(note.findtext('stem') == ('up' if voice == 1 else 'down'), f'{where}: 声部 {voice} 符干方向错误')
            levels = [int(b.get('number')) for b in note.findall('beam')]
            if levels:
                kind = note.findtext('type')
                allowed = BEAM_LEVELS.get(kind, 0)
                check(max(levels) <= allowed, f'{where}: {kind} 音符不应有 {max(levels)} 层横梁')
                check(levels == list(range(1, len(levels) + 1)), f'{where}: 横梁层级不连续 {levels}')
        check(spans == Counter({1: bar.length, 2: bar.length}),
              f'{where}: 声部时值 {dict(spans)}，应各为 {bar.length}')
    expected = Counter(n for bar in score.bars for hits in bar.events.values() for n in hits)
    check(counts == expected, f'记谱音符与模型不一致：多 {dict(counts - expected)}，少 {dict(expected - counts)}')
    return f'MusicXML OK：{len(measures)} 小节，{sum(counts.values())} 个音'


def normalize(text: str) -> str:
    return re.sub(r'\s+', '', text)


def validate_pdf(score: Transcription, path: Path) -> str:
    import pymupdf
    from render_score import expected_page_text
    from pdf_tounicode import tounicode_text
    with pymupdf.open(path) as doc:
        pages = len(doc)
        check(pages > 0, 'PDF 没有页面')
        expected = expected_page_text(score, pages)
        fonts: set[str] = set()
        for index, page in enumerate(doc):
            where = f'第 {index + 1} 页'
            check(abs(page.rect.width - 595.28) < 1 and abs(page.rect.height - 841.89) < 1, f'{where}: 不是 A4')
            check(len(page.get_drawings()) > 0, f'{where}: 没有矢量谱面')
            check(not page.get_images(full=True), f'{where}: 含位图，谱面应为矢量')
            for font in page.get_fonts(full=True):
                fonts.add(font[3])
            want = normalize(''.join(expected[index]))
            # with ActualText (Poppler/MuPDF/PDFium) and with ToUnicode only (pdf.js, Preview)
            for label, got in (('ActualText', page.get_text()), ('ToUnicode', tounicode_text(doc, page))):
                got = normalize(got)
                check(got == want, f'{where}（{label}）: 可提取文字与预期不符\n  预期：{want[:200]}\n  实际：{got[:200]}')
    for name in fonts:
        check('NotoSansCJK' in name, f'谱面字体未转为路径或混入了其他字体：{name}')
    _check_pdffonts(path)
    return f'PDF OK：{pages} 页，文字可复制且只含标题/图例/页眉/页码，字体 {sorted(fonts)}'


def _check_pdffonts(path: Path) -> None:
    """pdffonts (poppler) must report every font embedded, subset and with ToUnicode."""
    import shutil
    import subprocess
    if not shutil.which('pdffonts'):
        return
    rows = subprocess.run(['pdffonts', str(path)], capture_output=True, text=True, check=True).stdout.splitlines()[2:]
    for row in rows:
        cols = row.split()
        check(cols[-5:-2] == ['yes', 'yes', 'yes'], f'字体未完整嵌入或缺少 ToUnicode：{row}')


def default_xsd() -> Path | None:
    env = os.environ.get('MUSICXML_XSD')
    return Path(env) if env and Path(env).exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='校验 MusicXML / PDF 是否忠实于 MIDI')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map')
    parser.add_argument('--track', action='append')
    parser.add_argument('--channel', action='append', type=int)
    parser.add_argument('--musicxml', type=Path)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--xsd', type=Path, default=default_xsd(),
                        help='MusicXML 4.0 musicxml.xsd 路径（也可设环境变量 MUSICXML_XSD）')
    args = parser.parse_args(argv)
    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel})
        if args.musicxml:
            print(validate_musicxml(score, args.musicxml, args.xsd))
        if args.pdf:
            print(validate_pdf(score, args.pdf))
    except (ScoreError, ValidationError) as exc:
        print(f'校验失败：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
