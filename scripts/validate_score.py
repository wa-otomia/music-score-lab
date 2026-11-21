#!/usr/bin/env python3
"""Check that the generated MusicXML and PDF are faithful to the MIDI model.

MusicXML:
- (when an XSD is given) conforms to the MusicXML 4.0 schema;
- bar count, time signatures and pickup match the model; each voice sums to the bar length in every bar;
- every MIDI note is engraved the same number of times as in the model; beam levels match note values.

PDF:
- all fonts are embedded with ToUnicode, and only the Japanese header font remains (score glyphs are outlined);
- the text extractable from each page is **exactly** the header / legend / running head / page number; the staff yields no copyable characters;
- there is a vector score and no bitmaps.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
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
            raise ValidationError(f'MusicXML does not conform to the XSD: {errors}')
    root = ET.parse(path).getroot()
    check(root.tag == 'score-partwise', 'root element must be score-partwise')
    measures = root.findall('part/measure')
    check(len(measures) == len(score.bars), f'bar count {len(measures)} != model {len(score.bars)}')
    divisions = int(root.findtext('part/measure/attributes/divisions'))
    check(divisions == R, f'divisions should be {R}')
    counts: Counter = Counter()
    for bar, measure in zip(score.bars, measures):
        where = f'bar {bar.number}'
        check(measure.get('number') == str(bar.number), f'{where}: number attribute mismatch')
        check((measure.get('implicit') == 'yes') == bar.pickup, f'{where}: pickup implicit flag mismatch')
        beats = measure.findtext('attributes/time/beats')
        if bar.index == 0 or bar.show_meter:
            check(beats == str(bar.beats), f'{where}: time signature should be {bar.beats}/4, got {beats}')
        else:
            check(beats is None, f'{where}: time signature should not be repeated')
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
                check(note.findtext('stem') == ('up' if voice == 1 else 'down'), f'{where}: wrong stem direction in voice {voice}')
            levels = [int(b.get('number')) for b in note.findall('beam')]
            if levels:
                kind = note.findtext('type')
                allowed = BEAM_LEVELS.get(kind, 0)
                check(max(levels) <= allowed, f'{where}: a {kind} note should not have {max(levels)} beam level(s)')
                check(levels == list(range(1, len(levels) + 1)), f'{where}: beam levels are not contiguous {levels}')
        check(spans == Counter({1: bar.length, 2: bar.length}),
              f'{where}: voice durations {dict(spans)}, each should be {bar.length}')
    expected = Counter(n for bar in score.bars for hits in bar.events.values() for n in hits)
    check(counts == expected, f'engraved notes differ from the model: extra {dict(counts - expected)}, missing {dict(expected - counts)}')
    compare_with_model(score, root)
    return f'MusicXML OK: {len(measures)} bar{"" if len(measures) == 1 else "s"}, {sum(counts.values())} note{"" if sum(counts.values()) == 1 else "s"}'


def _canonical(measure: ET.Element) -> list[tuple]:
    """Everything musically relevant in a measure, in document order."""
    out: list[tuple] = []
    for el in measure:
        if el.tag == 'attributes':
            out.append((
                'attributes', el.findtext('time/beats'), el.findtext('time/beat-type'),
                tuple(mr.text for mr in el.findall('measure-style/multiple-rest')),
                tuple((mr.get('type'), mr.get('slashes'), mr.text)
                      for mr in el.findall('measure-style/measure-repeat'))))
        elif el.tag == 'direction':
            reh = el.find('direction-type/rehearsal')
            out.append((
                'direction',
                (reh.get('enclosure'), reh.text) if reh is not None else None,
                el.findtext('direction-type/metronome/per-minute')))
        elif el.tag == 'barline':
            out.append(('barline', el.get('location'), el.findtext('bar-style')))
        elif el.tag == 'backup':
            out.append(('backup', el.findtext('duration')))
        elif el.tag == 'note':
            head = el.find('notehead')
            out.append((
                'note', el.find('grace') is not None, el.find('chord') is not None,
                el.find('rest') is not None, (el.find('rest').get('measure') if el.find('rest') is not None else None),
                el.findtext('duration'), (el.find('instrument').get('id') if el.find('instrument') is not None else None),
                el.findtext('voice'), el.findtext('type'), len(el.findall('dot')),
                el.findtext('time-modification/actual-notes'), el.findtext('time-modification/normal-notes'),
                el.findtext('stem'), head.text if head is not None else None,
                head.get('filled') if head is not None else None, head.get('parentheses') if head is not None else None,
                tuple((b.get('number'), b.text) for b in el.findall('beam')),
                tuple((t.get('type'), t.get('bracket')) for t in el.findall('notations/tuplet')),
                tuple(c.tag for c in el.findall('notations/technical/*')),
                tuple(c.tag for c in el.findall('notations/articulations/*'))))
    return out


def compare_with_model(score: Transcription, root: ET.Element) -> None:
    """The file must match a fresh conversion of the MIDI note for note (catches stale,
    hand-edited or corrupted files: lost graces, changed heads, tuplets, meters, marks)."""
    from midi_to_musicxml import convert
    fresh, _ = convert(score)
    for got, want, bar in zip(root.findall('part/measure'), fresh.findall('part/measure'), score.bars):
        a, b = _canonical(got), _canonical(want)
        if a != b:
            index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            detail = f'file: {a[index] if index < len(a) else "(missing)"}; expected: {b[index] if index < len(b) else "(extra)"}'
            raise ValidationError(f'bar {bar.number} differs from a fresh conversion of the MIDI: {detail}')


def normalize(text: str) -> str:
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', text))


def validate_pdf(score: Transcription, path: Path) -> str:
    import pymupdf
    from render_score import expected_page_text
    from pdf_tounicode import tounicode_text
    with pymupdf.open(path) as doc:
        pages = len(doc)
        check(pages > 0, 'PDF has no pages')
        expected = expected_page_text(score, pages)
        fonts: set[str] = set()
        for index, page in enumerate(doc):
            where = f'page {index + 1}'
            check(abs(page.rect.width - 595.28) < 1 and abs(page.rect.height - 841.89) < 1, f'{where}: not A4')
            check(len(page.get_drawings()) > 0, f'{where}: no vector score')
            check(not page.get_images(full=True), f'{where}: contains a bitmap; the score should be vector')
            for font in page.get_fonts(full=True):
                fonts.add(font[3])
            want = normalize(''.join(expected[index]))
            # with ActualText (Poppler/MuPDF/PDFium) and with ToUnicode only (pdf.js, Preview)
            for label, got in (('ActualText', page.get_text()), ('ToUnicode', tounicode_text(doc, page))):
                got = normalize(got)
                check(got == want, f'{where} ({label}): extractable text differs from expected\n  expected: {want[:200]}\n  actual:   {got[:200]}')
    for name in fonts:
        check('NotoSansCJK' in name, f'score font was not outlined or another font is mixed in: {name}')
    _check_pdffonts(path)
    return f'PDF OK: {pages} page(s), text is copyable and contains only header/legend/running head/page number, fonts {sorted(fonts)}'


def _check_pdffonts(path: Path) -> None:
    """pdffonts (poppler) must report every font embedded, subset and with ToUnicode."""
    import shutil
    import subprocess
    if not shutil.which('pdffonts'):
        return
    rows = subprocess.run(['pdffonts', str(path)], capture_output=True, text=True, check=True).stdout.splitlines()[2:]
    for row in rows:
        cols = row.split()
        check(cols[-5:-2] == ['yes', 'yes', 'yes'], f'font is not fully embedded or lacks ToUnicode: {row}')


def default_xsd() -> Path | None:
    env = os.environ.get('MUSICXML_XSD')
    return Path(env) if env else None


class SetupError(RuntimeError):
    """The check itself cannot run (missing schema, missing file): exit code 2, not 1."""


def check_xsd(xsd: Path | None) -> None:
    if xsd is not None and not xsd.is_file():
        raise SetupError(f'MusicXML XSD not found: {xsd} (check --xsd or the MUSICXML_XSD environment variable)')
    if xsd is not None:
        try:
            from lxml import etree
        except ImportError:
            raise SetupError('XSD validation needs lxml (pip install lxml or apt install python3-lxml)') from None
        try:
            etree.XMLSchema(etree.parse(str(xsd)))
        except (etree.Error, OSError) as exc:
            raise SetupError(f'MusicXML XSD cannot be read or parsed: {xsd} ({exc})') from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Check that MusicXML / PDF are faithful to the MIDI')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map')
    parser.add_argument('--track', action='append')
    parser.add_argument('--channel', action='append', type=int)
    parser.add_argument('--repeats', choices=['off', 'simile'], default=None,
                        help='override notation.repeats in the metadata: simile or off')
    parser.add_argument('--beam-eighths', choices=['beat', 'half-bar'], default=None,
                        help='override notation.beam_eighths in the metadata: beat or half-bar')
    parser.add_argument('--musicxml', type=Path)
    parser.add_argument('--pdf', type=Path)
    parser.add_argument('--xsd', type=Path, default=default_xsd(),
                        help='path to the MusicXML 4.0 musicxml.xsd (or set MUSICXML_XSD)')
    args = parser.parse_args(argv)
    if not args.musicxml and not args.pdf:
        parser.error('specify at least one of --musicxml or --pdf')
    try:
        check_xsd(args.xsd)
        for target in (args.musicxml, args.pdf):
            if target is not None and not target.is_file():
                raise SetupError(f'file not found: {target}')
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel,
                                 'repeats': args.repeats, 'beam_eighths': args.beam_eighths})
        if args.musicxml:
            print(validate_musicxml(score, args.musicxml, args.xsd))
        if args.pdf:
            print(validate_pdf(score, args.pdf))
    except ValidationError as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        return 1
    except (ScoreError, SetupError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
