#!/usr/bin/env python3
"""One command: drum MIDI + metadata -> score.musicxml + score.pdf, with every check run.

    python3 scripts/build_score.py song.mid --metadata metadata.yaml --out-dir build/song

The output directory will contain:
  score.musicxml   editable MusicXML 4.0 (opens directly in MuseScore etc.)
  score.pdf        printable A4 drum score (header text is copyable, the staff is vector)
Any failing step ends with a non-zero exit code and says what to change (MIDI, metadata or drum map).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from score_core import ScoreError, build_score
import midi_to_musicxml
import render_score
import validate_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Drum MIDI + metadata -> MusicXML + PDF (with validation)')
    parser.add_argument('midi', type=Path, help='drum MIDI file (FL Studio FPC export, GM channel 10, etc.)')
    parser.add_argument('--metadata', type=Path, required=True, help='song metadata YAML, see docs/metadata.md')
    parser.add_argument('--out-dir', type=Path, required=True, help='output directory')
    parser.add_argument('--drum-map', help='override the drum map in the metadata: bundled name (gm, fpc-default) or YAML path')
    parser.add_argument('--track', action='append', help='use only tracks whose name contains this text (repeatable)')
    parser.add_argument('--channel', action='append', type=int, help='use only this MIDI channel, 1-16 (repeatable)')
    parser.add_argument('--repeats', choices=['off', 'simile'], default=None,
                        help='override notation.repeats in the metadata: simile (1- and 2-bar repeat signs) or off')
    parser.add_argument('--beam-eighths', choices=['beat', 'half-bar'], default=None,
                        help='override notation.beam_eighths in the metadata: beat or half-bar (4/4 only)')
    parser.add_argument('--no-pdf', action='store_true', help='generate MusicXML only (no TeX environment needed)')
    parser.add_argument('--legend', action=argparse.BooleanOptionalAction, default=None,
                        help='print (--legend) or omit (--no-legend) the instrument legend; default follows the metadata legend, omitted if unset')
    parser.add_argument('--work-dir', type=Path, help='directory to keep PDF intermediates (TeX source, unmerged score pages)')
    parser.add_argument('--xsd', type=Path, default=validate_score.default_xsd(),
                        help='path to the MusicXML 4.0 XSD (or set MUSICXML_XSD); schema validation runs when given')
    args = parser.parse_args(argv)

    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel,
                                 'repeats': args.repeats, 'beam_eighths': args.beam_eighths})
    except ScoreError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    if args.legend is not None:
        score.metadata['legend'] = args.legend
    early_warnings = list(score.warnings)
    for warning in early_warnings:
        print(f'Note: {warning}', file=sys.stderr)
    title = str(score.metadata.get('title') or '').strip()
    print(f'"{title}": {score.summary()}' if title else score.summary())

    out = args.out_dir
    try:
        validate_score.check_xsd(args.xsd)
        if out.exists() and not out.is_dir():
            raise RuntimeError(f'--out-dir points to an existing file, not a directory: {out}')
        out.mkdir(parents=True, exist_ok=True)
        # write next to the targets first; replace score.* only after every check passed
        musicxml, pdf = out / 'score.musicxml', out / 'score.pdf'
        new_xml, new_pdf = out / '.score.musicxml.new', out / '.score.pdf.new'
        midi_to_musicxml.write(score, new_xml)
        print(validate_score.validate_musicxml(score, new_xml, args.xsd))
        if not args.no_pdf:
            if args.work_dir:
                args.work_dir.mkdir(parents=True, exist_ok=True)
                info = render_score.render(score, new_pdf, args.work_dir.resolve())
            else:
                with tempfile.TemporaryDirectory(prefix='drum-score-') as temp:
                    info = render_score.render(score, new_pdf, Path(temp))
            print(validate_score.validate_pdf(score, new_pdf))
            new_pdf.replace(pdf)
            print(f'{pdf}: A4, {info["pages"]} page(s)')
        new_xml.replace(musicxml)
        print(musicxml)
        for warning in score.warnings[len(early_warnings):]:
            print(f'Note: {warning}', file=sys.stderr)
    except (ScoreError, RuntimeError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    except validate_score.ValidationError as exc:
        print(f'Validation failed: {exc}', file=sys.stderr)
        return 1
    finally:
        for leftover in (out / '.score.musicxml.new', out / '.score.pdf.new'):
            if leftover.exists():
                leftover.unlink()
    return 0


if __name__ == '__main__':
    sys.exit(main())
