#!/usr/bin/env python3
"""Write the notation model (score_core) as editable MusicXML 4.0 (score-partwise).

- One part, Drumset: upper voice 1 (hands, stems up), lower voice 2 (feet, stems down).
- Each MIDI note in use gets one score-instrument / midi-instrument (channel 10),
  so MuseScore etc. still play back the original GM notes after import.
- Noteheads, open/closed hi-hat marks, tuplets, beam levels, grace notes, whole-bar rests, multi-bar rests, measure repeats, rehearsal marks and double barlines are written as standard elements,
  in the element order required by the MusicXML 4.0 XSD (tests validate against the official XSD).
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from score_core import (R, STAFF_LETTERS, Bar, Hit, ScoreError, Transcription, VoiceItem, build_score,
                        item_ratio, note_type, voice_items)
from score_structure import measure_repeat_events, multi_rest_lengths, plan_units

NOTEHEAD = {'normal': ('normal', None), 'x': ('x', None), 'circle-x': ('circle-x', None),
            'diamond': ('diamond', 'no'), 'triangle': ('triangle', None), 'plus': ('cross', None),
            'rhombus': ('diamond', 'yes')}
TECHNICAL = {'open': 'open', 'half-open': 'half-muted', 'closed': 'stopped'}
VOICE = {'hand': 1, 'foot': 2}
SCORE_PART = 'P1'


def display_pitch(letter: str) -> tuple[str, str]:
    """MusiXTeX pitch letter (c = C4) → MusicXML display-step / display-octave."""
    n = STAFF_LETTERS.index(letter) - STAFF_LETTERS.index('c')
    return 'CDEFGAB'[n % 7], str(4 + n // 7)


def sub(parent: ET.Element, tag: str, text: object | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, {k.replace('_', '-'): v for k, v in attrs.items()})
    if text is not None:
        element.text = str(text)
    return element


def instrument_id(note: int) -> str:
    return f'{SCORE_PART}-I{note}'


def write_note(measure: ET.Element, item: VoiceItem, part: str, hit: Hit | None, *, chord: bool = False,
               grace: bool = False, first: bool = True, bar: Bar | None = None,
               grace_beam: str | None = None) -> None:
    """One <note>, children in the order required by the MusicXML 4.0 schema.
    A flam grace is a slashed 8th; the two graces of a drag are beamed 16ths."""
    voice = VOICE[part]
    note = sub(measure, 'note')
    if grace:
        sub(note, 'grace', **({} if grace_beam else {'slash': 'yes'}))
    if chord:
        sub(note, 'chord')
    if hit is None:
        sub(note, 'rest', **({'measure': 'yes'} if item.measure_rest else {}))
    else:
        unpitched = sub(note, 'unpitched')
        step, octave = display_pitch(hit.inst.staff)
        sub(unpitched, 'display-step', step)
        sub(unpitched, 'display-octave', octave)
    if not grace:
        sub(note, 'duration', item.duration)
    if hit is not None:
        sub(note, 'instrument', id=instrument_id(hit.note))
    sub(note, 'voice', voice)
    if grace:
        sub(note, 'type', '16th' if grace_beam else 'eighth')
    elif not item.measure_rest:
        name, dots = note_type(item)
        sub(note, 'type', name)
        for _ in range(dots):
            sub(note, 'dot')
    if item.tuplet and not grace:
        actual, normal = item_ratio(item)
        tm = sub(note, 'time-modification')
        sub(tm, 'actual-notes', actual)
        sub(tm, 'normal-notes', normal)
    if hit is not None:
        sub(note, 'stem', 'up' if voice == 1 else 'down')
        head, filled = NOTEHEAD[hit.inst.head]
        attrs = {}
        if filled:
            attrs['filled'] = filled
        if hit.ghost and not grace:
            attrs['parentheses'] = 'yes'
        sub(note, 'notehead', head, **attrs)
    if first and not grace:
        for level, value in item.beams:
            sub(note, 'beam', value, number=str(level))
    if grace and grace_beam and not chord:
        for level in (1, 2):
            sub(note, 'beam', grace_beam, number=str(level))
    notations = None
    if first and not grace and item.tuplet_edge:
        notations = sub(note, 'notations')
        edges = ['start', 'stop'] if item.tuplet_edge == 'both' else [item.tuplet_edge]
        for edge in edges:
            attrs = {'type': edge, 'number': '1'}
            if edge == 'start':
                attrs.update({'bracket': 'yes' if item.tuplet_bracket else 'no', 'show-number': 'actual'})
            sub(notations, 'tuplet', **attrs)
    if hit is not None and not grace and (hit.inst.mark or hit.accent):
        notations = notations if notations is not None else sub(note, 'notations')
        if hit.accent:
            sub(sub(notations, 'articulations'), 'accent')
        if hit.inst.mark:
            sub(sub(notations, 'technical'), TECHNICAL[hit.inst.mark])


def write_voice(measure: ET.Element, bar: Bar, part: str, *, beam_eighths: str = 'beat') -> None:
    for item in voice_items(bar, part, beam_eighths=beam_eighths):
        if item.is_rest:
            write_note(measure, item, part, None, bar=bar)
            continue
        heads = sorted(item.hits.values(), key=lambda h: (STAFF_LETTERS.index(h.inst.staff), h.note))
        count = max((h.grace for h in heads), default=0)
        for k in range(count):
            graces = [h for h in heads if h.grace > k]
            beam = None if count == 1 else ('begin' if k == 0 else 'end')
            for i, h in enumerate(graces):
                write_note(measure, item, part, h, grace=True, chord=i > 0, bar=bar, grace_beam=beam)
        for i, h in enumerate(heads):
            write_note(measure, item, part, h, chord=i > 0, first=i == 0, bar=bar)


def convert(score: Transcription) -> tuple[ET.Element, int]:
    meta = score.metadata
    root = ET.Element('score-partwise', version='4.0')
    title = str(meta.get('title') or 'Untitled')
    work = sub(root, 'work')
    if meta.get('subtitle'):
        sub(work, 'work-number', meta['subtitle'])  # MuseScore 3 shows work-number as the subtitle
    sub(work, 'work-title', title)
    sub(root, 'movement-title', title)  # MuseScore 3 takes the page title from movement-title
    ident = sub(root, 'identification')
    for kind in ('composer', 'lyricist', 'arranger'):
        if meta.get(kind):
            sub(ident, 'creator', meta[kind], type=kind)
    if meta.get('copyright'):
        sub(ident, 'rights', meta['copyright'])
    sub(sub(ident, 'encoding'), 'software', 'music-score-lab')
    misc = None
    for key in ('artist', 'album', 'vocal', 'transcriber', 'note'):
        if meta.get(key):
            misc = misc if misc is not None else sub(ident, 'miscellaneous')
            sub(misc, 'miscellaneous-field', meta[key], name=key)
    scaling = sub(sub(root, 'defaults'), 'scaling')
    sub(scaling, 'millimeters', '7')
    sub(scaling, 'tenths', '40')
    credit = sub(root, 'credit', page='1')
    sub(credit, 'credit-type', 'title')
    sub(credit, 'credit-words', title, justify='center', valign='top', font_size='20')
    subtitle_key = 'subtitle' if meta.get('subtitle') else 'artist'
    for kind, key, justify in (('subtitle', subtitle_key, 'center'), ('composer', 'composer', 'right'),
                               ('lyricist', 'lyricist', 'left'), ('arranger', 'transcriber', 'left')):
        if meta.get(key):
            c = sub(root, 'credit', page='1')
            sub(c, 'credit-type', kind)
            sub(c, 'credit-words', meta[key], justify=justify, valign='top')

    part_list = sub(root, 'part-list')
    score_part = sub(part_list, 'score-part', id=SCORE_PART)
    sub(score_part, 'part-name', 'Drumset')
    sub(score_part, 'part-abbreviation', 'Dr.')
    used = sorted(score.instruments_used(), key=lambda x: x[0])
    for note, inst in used:
        si = sub(score_part, 'score-instrument', id=instrument_id(note))
        sub(si, 'instrument-name', f'{inst.name} ({note})')
    for note, _inst in used:
        mi = sub(score_part, 'midi-instrument', id=instrument_id(note))
        sub(mi, 'midi-channel', '10')
        sub(mi, 'midi-unpitched', note + 1)  # MusicXML numbers unpitched keys 1–128

    part = sub(root, 'part', id=SCORE_PART)
    units = plan_units(score.bars, repeats=score.settings.repeats,
                       repeat_counters=score.settings.repeat_counters)
    multi = {u.first.index: len(u.bars) for u in units if u.kind == 'multi-rest'}
    rep_events = measure_repeat_events(units)
    engraved_notes = 0
    measure_idx = 0
    active_volta: str | None = None
    for u_idx, unit in enumerate(units):
        last_unit = u_idx == len(units) - 1
        next_double = (u_idx + 1 < len(units) and units[u_idx + 1].double_bar_before)
        for offset, bar in enumerate(unit.bars):
            is_first = offset == 0
            is_last = offset == len(unit.bars) - 1
            attrs = {'number': str(unit.printed_start + offset)}
            if bar.pickup:
                attrs['implicit'] = 'yes'
            measure = sub(part, 'measure', **attrs)
            if measure_idx == 0 or bar.show_meter or bar.index in multi or bar.index in rep_events:
                attributes = sub(measure, 'attributes')
                if measure_idx == 0:
                    sub(attributes, 'divisions', R)
                    key = sub(attributes, 'key')
                    sub(key, 'fifths', 0)
                if measure_idx == 0 or bar.show_meter:
                    time = sub(attributes, 'time')
                    sub(time, 'beats', bar.beats)
                    sub(time, 'beat-type', bar.beat_type)
                if measure_idx == 0:
                    sub(sub(attributes, 'clef'), 'sign', 'percussion')
                    sub(sub(attributes, 'staff-details'), 'staff-lines', '5')
                for kind, count in rep_events.get(bar.index, []):
                    ms = sub(attributes, 'measure-style')
                    if kind == 'stop':
                        sub(ms, 'measure-repeat', type='stop')
                    else:
                        sub(ms, 'measure-repeat', count, type='start', slashes=str(count))
                if bar.index in multi:
                    sub(sub(attributes, 'measure-style'), 'multiple-rest', multi[bar.index])
            if is_first and (unit.repeat_start or unit.volta_start is not None):
                left_bl = sub(measure, 'barline', location='left')
                if unit.repeat_start:
                    sub(left_bl, 'bar-style', 'heavy-light')
                if unit.volta_start is not None:
                    sub(left_bl, 'ending', f'{unit.volta_start}.', number=unit.volta_start, type='start')
                    active_volta = unit.volta_start
                if unit.repeat_start:
                    sub(left_bl, 'repeat', direction='forward')
            if bar.section is not None:
                direction = sub(measure, 'direction', placement='above')
                sub(sub(direction, 'direction-type'), 'rehearsal', bar.section, enclosure='square')
            if bar.tempo is not None:
                direction = sub(measure, 'direction', placement='above')
                metronome = sub(sub(direction, 'direction-type'), 'metronome')
                sub(metronome, 'beat-unit', 'quarter')
                sub(metronome, 'per-minute', f'{bar.tempo:g}')
                sub(direction, 'sound', tempo=f'{bar.tempo:g}')
            write_voice(measure, bar, 'hand', beam_eighths=score.settings.beam_eighths)
            backup = sub(measure, 'backup')
            sub(backup, 'duration', bar.length)
            write_voice(measure, bar, 'foot', beam_eighths=score.settings.beam_eighths)
            engraved_notes += sum(len(hits) for hits in bar.events.values())
            if is_last:
                is_final = last_unit
                if unit.repeat_end is not None or unit.volta_stop is not None or is_final or next_double:
                    right_bl = sub(measure, 'barline', location='right')
                    if unit.repeat_end is not None or is_final:
                        sub(right_bl, 'bar-style', 'light-heavy')
                    elif next_double:
                        sub(right_bl, 'bar-style', 'light-light')
                    if unit.volta_stop is not None:
                        sub(right_bl, 'ending', number=active_volta, type=unit.volta_stop)
                    if unit.repeat_end is not None:
                        sub(right_bl, 'repeat', direction='backward', times=str(unit.repeat_end))
                if unit.volta_stop is not None:
                    active_volta = None
            measure_idx += 1
    ET.indent(root, '  ')
    return root, engraved_notes


def write(score: Transcription, out: Path) -> int:
    root, count = convert(score)
    out.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    with out.open('wb') as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write(b'<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
                 b'"http://www.musicxml.org/dtds/partwise.dtd">\n')
        tree.write(fh, encoding='utf-8', xml_declaration=False)
        fh.write(b'\n')
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Drum MIDI + metadata -> MusicXML 4.0')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', help='bundled map name (gm, fpc-default) or YAML path')
    parser.add_argument('--track', action='append', help='use only tracks whose name contains this text (repeatable)')
    parser.add_argument('--channel', action='append', type=int, help='use only this MIDI channel, 1-16 (repeatable)')
    parser.add_argument('--repeats', choices=['off', 'simile', 'full'], default=None,
                        help='override notation.repeats in the metadata: full (repeat signs + similes), simile, or off')
    parser.add_argument('--beam-eighths', choices=['beat', 'half-bar'], default=None,
                        help='override notation.beam_eighths in the metadata: beat or half-bar (4/4 only)')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel,
                                 'repeats': args.repeats, 'beam_eighths': args.beam_eighths})
        write(score, args.out)
    except ScoreError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    for warning in score.warnings:
        print(f'Note: {warning}', file=sys.stderr)
    print(f'{args.out}: {score.summary()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
