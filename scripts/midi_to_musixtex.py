#!/usr/bin/env python3
"""Generate MusiXTeX source from FL Studio / GM percussion MIDI.

Uses real note and beaming primitives (not vector drawing). Includes the corrected
sixteenth-note terminal beaming command for crossed cymbal noteheads.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from score_core import build_score, voice_durations, hand_beams, chunks

# MusiXTeX/musixper special percussion notehead, with terminal beamed note.
CUSTOM_MACROS = [r'\catcode`\@=11', r'\def\dotqh#1{\do@symbol\@tqh{#1}}', r'\catcode`\@=12']


def open_hat_mark(note_pos: str) -> str:
    """Center the 'open' ring a few staff steps above its x-shaped head.

    In particular, do not anchor all rings at the absolute staff position `r`:
    an open cymbal must track the notehead's actual staff position.
    """
    marker_pos = chr(ord(note_pos) + 3)
    return r'\ccharnote{' + marker_pos + r'}{$\circ$}'



def note_pedal(char, kind, length, tpq, zero=False):
    value = length * 4 // tpq
    macro = {1: 'ccl', 2: 'cl', 3: 'cl', 4: 'ql'}[value]
    macro = ('' if kind == 'normal' else 'do') + macro
    if zero and kind == 'normal': macro = 'z' + macro
    result = '\\' + macro + '{' + char + '}'
    if value == 3: result += r'\pt{' + char + '}'
    return result


def note_hand(char, kind, length, tpq, beaming=None):
    circled = open_hat_mark(char) if kind == 'open' else ''
    if beaming:
        phase, strength = beaming
        start = '\\' + ('ibbu' if strength == 2 else 'ibu') + '0' + char + '0' if phase == 'start' else ''
        if phase == 'end':
            # Correct termination preserves the second beam of a 16th-note pair.
            close = r'\tbbu0' if strength == 2 else ''
            terminal = '\\' + ('dotqh' if kind != 'normal' else 'tqh') + '0{' + char + '}'
            return circled + close + terminal
        head = '\\' + ('doqb' if kind != 'normal' else 'qb') + '0{' + char + '}'
        return circled + start + head
    value = length * 4 // tpq
    macro = {1: 'ccu', 2: 'cu', 3: 'cu', 4: 'qu'}[value]
    result = circled + '\\' + ('' if kind == 'normal' else 'do') + macro + '{' + char + '}'
    if value == 3: result += r'\pt{' + char + '}'
    return result


def chord(t, notes, durations, beams, score):
    m = score.mapping
    feet = [pitch for pitch in notes if m[pitch]['part'] == 'foot']
    hands = [pitch for pitch in notes if m[pitch]['part'] == 'hand']
    result = []
    for pitch in sorted(hands):
        if notes[pitch]['grace']:
            result.append(r'\grcu{' + m[pitch]['staff_pos'] + '}')
    if feet:
        carrier = 36 if 36 in feet else feet[0]
        for pitch in [p for p in feet if p != carrier]:
            cfg = m[pitch]
            result.append('\\' + ('dozq' if cfg['kind'] != 'normal' else 'zq') + '{' + cfg['staff_pos'] + '}')
        cfg = m[carrier]
        length = durations[(t, 'foot')]
        if hands:
            if cfg['kind'] == 'normal':
                macro = {1:'zccl', 2:'zcl', 3:'zcl', 4:'zql'}[length * 4 // score.tpq]
                result.append('\\' + macro + '{' + cfg['staff_pos'] + '}')
                if length == score.tpq * 3 // 4:
                    result.append(r'\pt{' + cfg['staff_pos'] + '}')
            else:
                result.append(r'\advancefalse' + note_pedal(cfg['staff_pos'], cfg['kind'], length, score.tpq))
        else:
            result.append(note_pedal(cfg['staff_pos'], cfg['kind'], length, score.tpq))
    if hands:
        carrier = max(hands, key=lambda pitch: ord(m[pitch]['staff_pos']))
        for pitch in sorted((p for p in hands if p != carrier), key=lambda pitch: ord(m[pitch]['staff_pos'])):
            cfg = m[pitch]
            if cfg['kind'] == 'open': result.append(open_hat_mark(cfg['staff_pos']))
            result.append('\\' + ('dozq' if cfg['kind'] != 'normal' else 'zq') + '{' + cfg['staff_pos'] + '}')
        cfg = m[carrier]
        result.append(note_hand(cfg['staff_pos'], cfg['kind'], durations[(t,'hand')], score.tpq, beams.get(t)))
    return ''.join(result)


def notated_rest(dur, tpq):
    kind = dur * 4 // tpq
    # Only the half (2 beats), quarter, dotted eighth, eighth, sixteenth rests are emitted.
    return {8: r'\NOTes\hpause\en', 4: r'\NOtes\qp\en',
            3: r'\Notesp\dsp\en', 2: r'\Notes\ds\en', 1: r'\notes\qs\en'}[kind]


def bar_tex(events, score):
    if not events: return [r'\NOtes\centerPAuse\en']
    durations = voice_durations(events, score)
    beams = hand_beams(events, score)
    result = []
    times = sorted(events)
    now = 0
    names = {1: 'notes', 2: 'Notes', 3: 'Notesp', 4: 'NOtes'}
    for i, tick in enumerate(times):
        if tick > now:
            result += [notated_rest(n, score.tpq) for n in chunks(tick - now, score.tpq)]
            now = tick
        end = times[i + 1] if i + 1 < len(times) else score.bar_ticks
        slot = min(end - tick, score.tpq)
        key = slot * 4 // score.tpq
        if key not in names or slot * 4 != key * score.tpq:
            raise ValueError(f'Unsupported duration: {slot} ticks')
        result.append('\\' + names[key] + chord(tick, events[tick], durations, beams, score) + r'\en')
        now += slot
    if now < score.bar_ticks:
        result += [notated_rest(n, score.tpq) for n in chunks(score.bar_ticks - now, score.tpq)]
    return result


def convert(score):
    intro_beats = score.pickup_ticks // score.tpq if score.pickup_ticks else score.metadata.get('beats', 4)
    initial_meter = f'\\generalmeter{{\\meterfrac{intro_beats}4}}'
    lines = [r'\input musixtex', r'\input musixper', *CUSTOM_MACROS,
             r'\instrumentnumber{1}', r'\setstaffs1{1}', initial_meter,
             r'\setclef1{0}', r'\setclefsymbol1{\drumclef}', r'\systemnumbers',
             r'\parindent=0pt', r'\centerline{\tenrm ~}', r'\smallskip',
             r'\centerline{\tenrm ~}', r'\smallskip', r'\centerline{\tenrm ~}',
             r'\bigskip', r'\startpiece']
    stats = []
    start = 0
    for i, bar in enumerate(score.bars):
        pickup = i == 0 and score.pickup_ticks
        lines.append('% ' + ('pickup' if pickup else f'bar {i}'))
        if pickup:
            lines += [notated_rest(n, score.tpq) for n in chunks(score.pickup_ticks, score.tpq)]
        else:
            lines += bar_tex(bar, score)
        stats.append(len(bar))
        if i == len(score.bars) - 1: break
        if pickup:
            # This is a shortened introductory measure, followed by a
            # clearly printed 4/4 meter on the first complete measure.
            lines.append(r'\generalmeter{\meterfrac44}\changecontext')
            continue
        number = i - start + 1
        density = sum(stats[start:i+1])
        if (number >= 2 and density >= 25) or number >= 3:
            lines.append(r'\alaligne')
            start = i + 1
        else:
            lines.append(r'\bar')
    lines += [r'\endpiece', r'\bye']
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/japanese-drums.yaml')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    score = build_score(args.midi, args.metadata, args.drum_map)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(convert(score), encoding='ascii')
    print(f'{args.out}: {len(score.bars)} measures, {score.source_hits} original hits')

if __name__ == '__main__': main()
