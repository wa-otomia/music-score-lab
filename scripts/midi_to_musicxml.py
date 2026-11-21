#!/usr/bin/env python3
"""把记谱模型（score_core）写成可编辑的 MusicXML 4.0（score-partwise）。

- 一个声部 Drumset：上声部 voice 1（手，符干朝上），下声部 voice 2（脚，符干朝下）。
- 每个用到的 MIDI 音符对应一个 score-instrument / midi-instrument（通道 10），
  MuseScore 等软件导入后仍能按原 GM 音符回放。
- 符头、开/闭镲记号、三连音、横梁层级、装饰音、整小节休止与多小节休止都写成标准元素，
  输出符合 MusicXML 4.0 XSD 的元素顺序（tests 会用官方 XSD 校验）。
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from score_core import (R, STAFF_LETTERS, Bar, Hit, ScoreError, Transcription, VoiceItem, build_score,
                        item_ratio, note_type, voice_items)

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
               grace: bool = False, first: bool = True, bar: Bar | None = None) -> None:
    """One <note>, children in the order required by the MusicXML 4.0 schema."""
    voice = VOICE[part]
    note = sub(measure, 'note')
    if grace:
        sub(note, 'grace', slash='yes')
    if chord:
        sub(note, 'chord')
    if hit is None:
        rest = sub(note, 'rest', **({'measure': 'yes'} if item.measure_rest else {}))
        del rest
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
        sub(note, 'type', 'eighth')
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
    notations = None
    if first and not grace and item.tuplet_edge:
        notations = sub(note, 'notations')
        edges = ['start', 'stop'] if item.tuplet_edge == 'both' else [item.tuplet_edge]
        for edge in edges:
            attrs = {'type': edge, 'number': '1'}
            if edge == 'start':
                attrs.update({'bracket': 'no' if item.beams else 'yes', 'show-number': 'actual'})
            sub(notations, 'tuplet', **attrs)
    if hit is not None and not grace and (hit.inst.mark or hit.accent):
        notations = notations if notations is not None else sub(note, 'notations')
        if hit.accent:
            sub(sub(notations, 'articulations'), 'accent')
        if hit.inst.mark:
            sub(sub(notations, 'technical'), TECHNICAL[hit.inst.mark])


def write_voice(measure: ET.Element, bar: Bar, part: str) -> None:
    for item in voice_items(bar, part):
        if item.is_rest:
            write_note(measure, item, part, None, bar=bar)
            continue
        heads = sorted(item.hits.values(), key=lambda h: (STAFF_LETTERS.index(h.inst.staff), h.note))
        graces = [h for h in heads if h.grace]
        for i, h in enumerate(graces):
            write_note(measure, item, part, h, grace=True, chord=i > 0, bar=bar)
        for i, h in enumerate(heads):
            write_note(measure, item, part, h, chord=i > 0, first=i == 0, bar=bar)


def multi_rest_lengths(bars: list[Bar]) -> dict[int, int]:
    """Index of the first bar of each run of ≥2 empty bars → run length (same rule as the PDF)."""
    runs: dict[int, int] = {}
    i = 0
    while i < len(bars):
        j = i
        if not bars[i].events and not bars[i].pickup:
            while (j + 1 < len(bars) and not bars[j + 1].events and not bars[j + 1].show_meter
                   and bars[j + 1].tempo is None):
                j += 1
        if j > i:
            runs[i] = j - i + 1
        i = j + 1
    return runs


def convert(score: Transcription) -> tuple[ET.Element, int]:
    meta = score.metadata
    root = ET.Element('score-partwise', version='4.0')
    title = str(meta.get('title') or 'Untitled')
    sub(sub(root, 'work'), 'work-title', title)
    if meta.get('subtitle'):
        sub(root, 'movement-title', meta['subtitle'])
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
    for kind, key in (('composer', 'artist'), ('arranger', 'transcriber')):
        if meta.get(key):
            c = sub(root, 'credit', page='1')
            sub(c, 'credit-type', kind)
            sub(c, 'credit-words', meta[key], justify='right' if kind == 'composer' else 'left', valign='top')

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
    multi = multi_rest_lengths(score.bars)
    for i, bar in enumerate(score.bars):
        attrs = {'number': str(bar.number)}
        if bar.pickup:
            attrs['implicit'] = 'yes'
        measure = sub(part, 'measure', **attrs)
        if i == 0 or bar.show_meter or i in multi:
            attributes = sub(measure, 'attributes')
            if i == 0:
                sub(attributes, 'divisions', R)
                key = sub(attributes, 'key')
                sub(key, 'fifths', 0)
            if i == 0 or bar.show_meter:
                time = sub(attributes, 'time')
                sub(time, 'beats', bar.beats)
                sub(time, 'beat-type', bar.beat_type)
            if i == 0:
                sub(sub(attributes, 'clef'), 'sign', 'percussion')
                sub(sub(attributes, 'staff-details'), 'staff-lines', '5')
            if i in multi:
                sub(sub(attributes, 'measure-style'), 'multiple-rest', multi[i])
        if bar.tempo is not None:
            direction = sub(measure, 'direction', placement='above')
            metronome = sub(sub(direction, 'direction-type'), 'metronome')
            sub(metronome, 'beat-unit', 'quarter')
            sub(metronome, 'per-minute', f'{bar.tempo:g}')
            sub(direction, 'sound', tempo=f'{bar.tempo:g}')
        write_voice(measure, bar, 'hand')
        backup = sub(measure, 'backup')
        sub(backup, 'duration', bar.length)
        write_voice(measure, bar, 'foot')
    if score.bars:
        last = part.findall('measure')[-1]
        barline = sub(last, 'barline', location='right')
        sub(barline, 'bar-style', 'light-heavy')
    ET.indent(root, '  ')
    return root, score.engraved_hits


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
    parser = argparse.ArgumentParser(description='鼓 MIDI + 元数据 → MusicXML 4.0')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', help='内置映射名（gm、fpc-default）或 YAML 路径')
    parser.add_argument('--track', action='append', help='只用名称包含该文字的轨道（可重复）')
    parser.add_argument('--channel', action='append', type=int, help='只用该 MIDI 通道 1–16（可重复）')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel})
        write(score, args.out)
    except ScoreError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2
    for warning in score.warnings:
        print(f'提示：{warning}', file=sys.stderr)
    print(f'{args.out}: {score.summary()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
