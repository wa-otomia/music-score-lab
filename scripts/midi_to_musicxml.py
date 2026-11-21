#!/usr/bin/env python3
"""Write an editable MusicXML drum score from an FPC/GM MIDI file."""
from __future__ import annotations
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from score_core import build_score, voice_durations, hand_beams, chunks

NAMES = 'cdefghijklmnopq'
NOTE_NAMES = ['C', 'D', 'E', 'F', 'G', 'A', 'B']


def pitch_from_staff(pos: str) -> tuple[str, str]:
    n = NAMES.index(pos)
    return NOTE_NAMES[n % 7], str(4 + n // 7)


def write_note(parent, dur, score, voice, pitch=None, chord=False, grace=False, rest=False, beam=None):
    note = ET.SubElement(parent, 'note')
    if chord:
        ET.SubElement(note, 'chord')
    if grace:
        ET.SubElement(note, 'grace', slash='yes')
    if rest:
        ET.SubElement(note, 'rest')
    else:
        unpitched = ET.SubElement(note, 'unpitched')
        step, octave = pitch_from_staff(score.mapping[pitch]['staff_pos'])
        ET.SubElement(unpitched, 'display-step').text = step
        ET.SubElement(unpitched, 'display-octave').text = octave
        ET.SubElement(note, 'instrument', id=f'I{pitch}')
    if not grace:
        ET.SubElement(note, 'duration').text = str(dur)
    ET.SubElement(note, 'voice').text = str(voice)
    if grace:
        name, dotted = '16th', False
    elif dur == score.tpq * 4:
        name, dotted = 'whole', False
    elif dur == score.tpq * 2:
        name, dotted = 'half', False
    elif dur == score.tpq:
        name, dotted = 'quarter', False
    elif dur == score.tpq * 3 // 4:
        name, dotted = 'eighth', True
    elif dur == score.tpq // 2:
        name, dotted = 'eighth', False
    else:
        name, dotted = '16th', False
    ET.SubElement(note, 'type').text = name
    if dotted: ET.SubElement(note, 'dot')
    if not rest:
        ET.SubElement(note, 'stem').text = 'up' if voice == 1 else 'down'
        ET.SubElement(note, 'notehead').text = 'x' if score.mapping[pitch]['kind'] != 'normal' else 'normal'
        if score.mapping[pitch]['kind'] == 'open':
            ET.SubElement(ET.SubElement(ET.SubElement(note, 'notations'), 'technical'), 'open-string')
        if beam:
            phase, strength = beam
            beamname = {'start': 'begin', 'mid': 'continue', 'end': 'end'}[phase]
            for idx in range(1, strength + 1):
                ET.SubElement(note, 'beam', number=str(idx)).text = beamname
    return note


def convert(score):
    meta = score.metadata
    root = ET.Element('score-partwise', version='4.0')
    ET.SubElement(ET.SubElement(root, 'work'), 'work-title').text = str(meta['title'])
    ET.SubElement(root, 'movement-title').text = str(meta['title'])
    identity = ET.SubElement(root, 'identification')
    for kind, key in [('composer', 'composer'), ('lyricist', 'lyricist'), ('arranger', 'arranger')]:
        if meta.get(key):
            ET.SubElement(identity, 'creator', type=kind).text = str(meta[key])
    ET.SubElement(ET.SubElement(identity, 'miscellaneous'), 'miscellaneous-field', name='source').text = (
        str(meta.get('album', '')) + ' / ' + str(meta.get('vocal', '')) + ' / ' + str(meta.get('note', '')))
    scaling = ET.SubElement(ET.SubElement(root, 'defaults'), 'scaling')
    ET.SubElement(scaling, 'millimeters').text = '7'
    ET.SubElement(scaling, 'tenths').text = '40'
    sp = ET.SubElement(ET.SubElement(root, 'part-list'), 'score-part', id='P1')
    ET.SubElement(sp, 'part-name').text = 'Drumset'
    ET.SubElement(sp, 'part-abbreviation').text = 'Dr.'
    for midi, cfg in sorted(score.mapping.items()):
        iid = f'I{midi}'
        ET.SubElement(ET.SubElement(sp, 'score-instrument', id=iid), 'instrument-name').text = cfg['name']
        inst = ET.SubElement(sp, 'midi-instrument', id=iid)
        ET.SubElement(inst, 'midi-channel').text = '10'
        ET.SubElement(inst, 'midi-unpitched').text = str(midi)
    part = ET.SubElement(root, 'part', id='P1')
    total_notes = 0
    for i, events in enumerate(score.bars):
        is_pickup = i == 0 and score.pickup_ticks > 0
        m = ET.SubElement(part, 'measure', number=str(i + (0 if not score.pickup_ticks else 0)), implicit='yes' if is_pickup else 'no')
        if i == 0:
            attrs = ET.SubElement(m, 'attributes')
            ET.SubElement(attrs, 'divisions').text = str(score.tpq)
            tm = ET.SubElement(attrs, 'time')
            ET.SubElement(tm, 'beats').text = str(score.pickup_ticks // score.tpq if is_pickup else meta.get('beats', 4))
            ET.SubElement(tm, 'beat-type').text = str(meta.get('beat_type', 4))
            ET.SubElement(ET.SubElement(m, 'clef'), 'sign').text = 'percussion'
            ET.SubElement(ET.SubElement(m, 'staff-details'), 'staff-lines').text = '5'
            direction = ET.SubElement(m, 'direction', placement='above')
            metronome = ET.SubElement(ET.SubElement(direction, 'direction-type'), 'metronome')
            ET.SubElement(metronome, 'beat-unit').text = 'quarter'
            ET.SubElement(metronome, 'per-minute').text = str(meta.get('tempo_bpm', 120))
            ET.SubElement(direction, 'sound', tempo=str(meta.get('tempo_bpm', 120)))
        if is_pickup:
            write_note(m, score.pickup_ticks, score, 1, rest=True)
            continue
        if i == 1 and score.pickup_ticks:
            # Transition from the shortened introductory meter to the
            # complete meter; this must be explicit in the MusicXML too.
            attrs = ET.SubElement(m, 'attributes')
            tm = ET.SubElement(attrs, 'time')
            ET.SubElement(tm, 'beats').text = str(meta.get('beats', 4))
            ET.SubElement(tm, 'beat-type').text = str(meta.get('beat_type', 4))
        durations = voice_durations(events, score)
        beams = hand_beams(events, score)
        for voice, part_name in ((1, 'hand'), (2, 'foot')):
            if voice == 2:
                ET.SubElement(ET.SubElement(m, 'backup'), 'duration').text = str(score.bar_ticks)
            times = sorted(t for t, ns in events.items()
                           if any(score.mapping[p]['part'] == part_name for p in ns))
            if not times:
                write_note(m, score.bar_ticks, score, voice, rest=True)
                continue
            current = 0
            for t in times:
                if t > current:
                    for d in chunks(t - current, score.tpq):
                        write_note(m, d, score, voice, rest=True)
                dur = durations[(t, part_name)]
                pitches = sorted((p for p in events[t] if score.mapping[p]['part'] == part_name),
                                 key=lambda p: score.mapping[p]['staff_pos'])
                for p in pitches:
                    if events[t][p]['grace']:
                        write_note(m, score.tpq // 4, score, voice, p, grace=True)
                for idx, p in enumerate(pitches):
                    write_note(m, dur, score, voice, p, chord=idx > 0, beam=beams.get(t) if voice == 1 else None)
                    total_notes += 1
                current = t + dur
            if current < score.bar_ticks:
                for d in chunks(score.bar_ticks - current, score.tpq):
                    write_note(m, d, score, voice, rest=True)
    ET.indent(root, '  ')
    return root, total_notes


def main():
    p = argparse.ArgumentParser()
    p.add_argument('midi', type=Path)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--drum-map', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/japanese-drums.yaml')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    score = build_score(a.midi, a.metadata, a.drum_map)
    xml, count = convert(score)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(xml).write(a.out, encoding='utf-8', xml_declaration=True)
    print(f'{a.out}: {count} notes, {len(score.bars)} measures, {score.grace_hits} graces')

if __name__ == '__main__': main()
