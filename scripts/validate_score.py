#!/usr/bin/env python3
"""Check source MIDI, MusicXML voices, pickup and generated PDF metadata."""
import argparse
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import fitz

from score_core import build_score


def validate(midi: Path, metadata: Path, config: Path, musicxml: Path, pdf: Path | None = None):
    score = build_score(midi, metadata, config)
    root = ET.parse(musicxml).getroot()
    assert root.tag == 'score-partwise'
    measures = root.findall('part/measure')
    assert len(measures) == len(score.bars), f'Wrong measure count {len(measures)} != {len(score.bars)}'
    if score.pickup_ticks:
        assert measures[0].findtext('attributes/time/beats') == str(score.pickup_ticks // score.tpq), 'Introductory meter not explicit'
        assert measures[1].findtext('attributes/time/beats') == str(score.metadata.get('beats', 4)), 'Main 4/4 meter not restored'
    total_notes = Counter()
    for index, measure in enumerate(measures):
        spans = Counter()
        for note in measure.findall('note'):
            chord = note.find('chord') is not None
            grace = note.find('grace') is not None
            voice = int(note.findtext('voice'))
            if not (chord or grace):
                spans[voice] += int(note.findtext('duration'))
            if note.find('rest') is None and not grace:
                inst = note.find('instrument')
                assert inst is not None
                pitch = int(inst.attrib['id'][1:])
                total_notes[pitch] += 1
                assert note.findtext('stem') == ('up' if voice == 1 else 'down')
                assert note.findtext('notehead') == ('normal' if score.mapping[pitch]['kind'] == 'normal' else 'x')
            if note.findtext('type') == '16th' and note.find('beam') is not None:
                beaming = [b.attrib.get('number') for b in note.findall('beam')]
                assert beaming == ['1', '2'], f'16th must have two beam levels: {beaming}'
        want = {1: score.pickup_ticks} if index == 0 and score.pickup_ticks else {1: score.bar_ticks, 2: score.bar_ticks}
        assert dict(spans) == want, f'Measure {index}: voice lengths {spans}, expected {want}'
    expected = Counter(p for bar in score.bars for hits in bar.values() for p in hits)
    assert total_notes == expected, f'Pitch events differ: {total_notes - expected}'
    if pdf:
        doc = fitz.open(pdf)
        assert len(doc) > 0
        # Japanese credits are outlined into vector paths, intentionally making
        # their appearance independent of PDF viewers' CJK font handling.
        # PDF processors may strip Info metadata while retaining visible paths.
        # If metadata survives, it must match the score credits.
        if doc.metadata.get('title'):
            assert str(score.metadata['title']) in doc.metadata['title'], 'PDF title metadata mismatch'
        if doc.metadata.get('author'):
            assert str(score.metadata['transcriber']) in doc.metadata['author'], 'PDF transcriber metadata mismatch'
        assert doc[0].get_drawings(), 'Missing vector engraving'
        assert not any('Noto Sans CJK' in f[3] for f in doc[0].get_fonts()), 'Japanese credits must be outlined (not embedded fonts)'
        for p in doc:
            assert p.rect.width > 0 and p.rect.height > 0
        print(f'PDF: {len(doc)} pages, vector engraving and font-independent CJK header verified')
    print(f'OK: {len(measures)} measures, {sum(expected.values())} engraved hits, '
          f'{score.grace_hits} grace events from {score.source_hits} MIDI hits')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/japanese-drums.yaml')
    parser.add_argument('--musicxml', type=Path, required=True)
    parser.add_argument('--pdf', type=Path)
    args = parser.parse_args()
    validate(args.midi, args.metadata, args.drum_map, args.musicxml, args.pdf)

if __name__ == '__main__': main()
