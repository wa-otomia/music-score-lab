#!/usr/bin/env python3
"""把记谱模型（score_core）翻译成 MusiXTeX 源码。

只负责「怎么画」，节奏、时值、横梁层级全部来自 score_core，不在这里重新推断。

- 符头：musixper/musixdia 的符号定义 + MusiXTeX 通用绘制例程组合，例如
  ``\\do@symbol\\@qb0{n}`` 是带横梁的叉形符头。
- 手（上声部）用 0 号横梁、符干朝上；脚（下声部）用 1 号横梁、符干朝下。
- 两个声部都休止的地方才印休止符（居中）；声部各自的完整休止写在 MusicXML 里。
- 空小节印整小节休止，连续空小节合并成多小节休止。
- 输出只含 ASCII；日文标题、署名、图例文字由 render_score.py 用 XeLaTeX 另外排版。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from score_core import (R, STAFF_LETTERS, Bar, Hit, ScoreError, Transcription, VoiceItem, build_score,
                        note_type, voice_items, voice_tuplets, _rests)

SYMBOL = {
    'normal': r'\q@symbol', 'x': r'\do@symbol', 'circle-x': r'\dc@symbol', 'diamond': r'\d@symbol',
    'triangle': r'\t@symbol', 'plus': r'\k@symbol', 'rhombus': r'\r@symbol',
}
MARK_TEXT = {'open': r'$\circ$', 'half-open': r'$\ominus$', 'closed': r'{\tenrm +}'}
BEAM = {'hand': 0, 'foot': 1}

PREAMBLE = r"""\input musixtex
\input musixper
\catcode`\@=11
\nopagenumbers
\special{papersize=210mm,297mm}
\voffset-6mm
\overfullrule=0pt
"""


def shift(letter: str, steps: int) -> str:
    index = max(0, min(len(STAFF_LETTERS) - 1, STAFF_LETTERS.index(letter) + steps))
    return STAFF_LETTERS[index]


def spacing(ticks: int) -> str:
    """Horizontal space for a group lasting ``ticks``: 2 elemskips per 16th, +1 per doubling."""
    width = 2 + math.log2(ticks / (R / 4))
    return rf'\vnotes{max(width, 1.3):.2f}\elemskip'


def rest_macro(item: VoiceItem) -> str:
    name, dots = note_type(item)
    base = {'whole': r'\pause', 'half': r'\hpause', 'quarter': r'\qp', 'eighth': r'\ds', '16th': r'\qs'}[name]
    return base + ('p' if dots else '')


def ordered(hits: dict[int, Hit], part: str) -> list[Hit]:
    """Heads sorted so that the stem carrier is last: highest for hands, lowest for feet."""
    key = lambda h: (STAFF_LETTERS.index(h.inst.staff), h.note)
    return sorted(hits.values(), key=key, reverse=(part == 'foot'))


class VoiceWriter:
    """Emits one voice's chord at a time, tracking the open beam of that voice."""

    def __init__(self, part: str, bar: Bar):
        self.part = part
        self.bar = bar
        self.up = part == 'hand'
        self.beam = BEAM[part]

    def grace(self, item: VoiceItem) -> str:
        heads = [h for h in ordered(item.hits, self.part) if h.grace]
        if not heads:
            return ''
        routine = r'\@grcu' if self.up else r'\@grcl'
        parts = [SYMBOL[h.inst.head] + r'\@zq{' + h.inst.staff + '}' for h in heads[:-1]]
        last = heads[-1]
        parts.append(SYMBOL[last.inst.head] + routine + '{' + last.inst.staff + '}')
        return ''.join(parts)

    def chord(self, item: VoiceItem, spacing_note: bool) -> str:
        heads = ordered(item.hits, self.part)
        carrier = heads[-1]
        name, dots = note_type(item)
        out: list[str] = []
        for h in heads:
            out.append(self.ornaments(h))
        for h in heads[:-1]:
            if dots:
                out.append(r'\pt{' + h.inst.staff + '}')
            out.append(SYMBOL[h.inst.head] + r'\@zq{' + h.inst.staff + '}')
        out.append(self.tuplet_label(item, heads))
        if dots:
            out.append(r'\pt{' + carrier.inst.staff + '}')
        if not spacing_note:
            out.append(r'\advancefalse')
        out.append(self.carrier(item, carrier, name))
        return ''.join(out)

    def ornaments(self, h: Hit) -> str:
        p = h.inst.staff
        out = ''
        if h.ghost:
            out += r'\lpar{' + p + r'}\rpar{' + p + '}'
        if h.inst.mark:
            target = shift(p, 3) if self.up else shift(p, -3)
            out += r'\ccharnote{' + target + '}{' + MARK_TEXT[h.inst.mark] + '}'
        if h.accent and self.up:
            out += r'\usf{' + shift(p, 9) + '}'
        return out

    def tuplet_label(self, item: VoiceItem, heads: list[Hit]) -> str:
        if not item.tuplet_label:
            return ''
        number = item.tuplet
        if item.beams:
            return r'\def\txt{' + str(number) + '}' + (r'\butext' if self.up else r'\bltext') + str(self.beam)
        p = heads[-1].inst.staff
        target = shift(p, 10) if self.up else shift(p, -9)
        return r'\ccharnote{' + target + r'}{\eightit ' + str(number) + '}'

    def carrier(self, item: VoiceItem, h: Hit, name: str) -> str:
        sym, p, n = SYMBOL[h.inst.head], h.inst.staff, str(self.beam)
        u = 'u' if self.up else 'l'
        if not item.beams:
            routine = {'quarter': 'q', 'eighth': 'c', '16th': 'cc', 'half': 'h', 'whole': 'w'}[name]
            if routine in ('h', 'w'):
                raise ScoreError('内部错误：鼓谱音符时值不应超过四分音符')
            if routine == 'q':
                return sym + r'\@q' + u + '{' + p + '}'
            return sym + r'\@' + routine + u + '{' + p + '}'
        levels = dict(item.beams)
        primary, secondary = levels[1], levels.get(2)
        out = ''
        if primary == 'begin':
            ref = self.reference
            if secondary in ('begin', 'forward hook'):
                out += rf'\ibb{u}{n}{{{ref}}}0'
                if secondary == 'forward hook':
                    out += rf'\roff{{\tbb{u}{n}}}'
            else:
                out += rf'\ib{u}{n}{{{ref}}}0'
        else:
            if secondary == 'begin':
                out += rf'\nbb{u}{n}'
            elif secondary in ('end', 'backward hook'):
                out += rf'\tbb{u}{n}'
        if primary == 'end':
            return out + sym + (r'\@tqh' if self.up else r'\@tqb') + n + '{' + p + '}'
        return out + sym + r'\@qb' + n + '{' + p + '}'

    def start_bar_beams(self, items: list[VoiceItem]) -> None:
        """Pick one reference pitch per beamed run: above the highest head for hands,
        below the lowest head for feet, so stems never cut through chord heads."""
        self.refs: dict[int, str] = {}
        run: list[VoiceItem] = []
        for it in items:
            if it.beams and dict(it.beams)[1] == 'begin':
                run = [it]
            elif it.beams:
                run.append(it)
            if it.beams and dict(it.beams)[1] == 'end':
                letters = [h.inst.staff for x in run for h in x.hits.values()]
                pick = max if self.up else min
                ref = pick(letters, key=STAFF_LETTERS.index)
                self.refs[run[0].start] = ref
        self._current = None

    @property
    def reference(self) -> str:
        return self.refs[self._current]


def tempo_mark(bar: Bar) -> str:
    """Metronome mark placed clear of the highest stem in the bar."""
    letters = [h.inst.staff for hits in bar.events.values() for h in hits.values() if h.inst.part == 'hand']
    top = max(letters, key=STAFF_LETTERS.index) if letters else 'm'
    pitch = chr(min(ord('z'), max(ord('q'), ord(top) + 11)))
    return r'\zcharnote{' + pitch + r'}{\metron{\qu}{' + f'{bar.tempo:g}' + '}}'


def silent_spans(bar: Bar, voices: dict[str, list[VoiceItem]]) -> list[tuple[int, int]]:
    covered = sorted((it.start, it.start + it.duration) for items in voices.values()
                     for it in items if not it.is_rest)
    spans, cursor = [], 0
    for a, b in covered:
        if a > cursor:
            spans.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < bar.length:
        spans.append((cursor, bar.length))
    return spans


def bar_is_empty(bar: Bar) -> bool:
    return not bar.events


def bar_groups(bar: Bar) -> tuple[list[str], float]:
    """TeX note groups for one non-empty bar and its estimated width in elemskips."""
    voices = {part: voice_items(bar, part) for part in ('hand', 'foot')}
    writers = {part: VoiceWriter(part, bar) for part in voices}
    for part, items in voices.items():
        writers[part].start_bar_beams(items)
    timeline: dict[int, dict] = {}
    for part, items in voices.items():
        for it in items:
            if not it.is_rest:
                timeline.setdefault(it.start, {})[part] = it
    tuplets = {**voice_tuplets(bar, 'foot'), **voice_tuplets(bar, 'hand')}
    for a, b in silent_spans(bar, voices):
        for rest in _rests(a, b, bar, tuplets):
            timeline.setdefault(rest.start, {})['rest'] = rest
    times = sorted(timeline)
    groups: list[str] = []
    width = 0.0
    for i, t in enumerate(times):
        slot = (times[i + 1] if i + 1 < len(times) else bar.length) - t
        entry = timeline[t]
        body = ''
        if i == 0 and bar.tempo is not None and bar.index > 0:
            body += tempo_mark(bar)
        if 'rest' in entry and not ('hand' in entry or 'foot' in entry):
            body += rest_macro(entry['rest'])
        else:
            graces = ''.join(writers[p].grace(entry[p]) for p in ('foot', 'hand') if p in entry)
            if graces:
                groups.append(r'\notes\multnoteskip\smallvalue\smallnotesize' + graces + r'\en')
                width += 1.6
            for p in ('foot', 'hand'):
                if p in entry:
                    writers[p]._current = _run_start(voices[p], entry[p])
            if 'foot' in entry:
                body += writers['foot'].chord(entry['foot'], spacing_note='hand' not in entry)
            if 'hand' in entry:
                body += writers['hand'].chord(entry['hand'], spacing_note=True)
        groups.append(spacing(slot) + body + r'\en')
        width += 2 + math.log2(slot / (R / 4))
    return groups, width


def _run_start(items: list[VoiceItem], item: VoiceItem) -> int | None:
    start = None
    for it in items:
        if it.beams and dict(it.beams)[1] == 'begin':
            start = it.start
        if it is item:
            return start if it.beams else None
    return None


def convert(score: Transcription, *, header_space: float = 0.0, line_width: float = 74.0,
            max_bars_per_line: int = 4) -> str:
    """Full MusiXTeX document.  ``header_space`` (pt) is left blank above the first system
    for the XeLaTeX title block; ``line_width`` is the elemskip budget per system."""
    bars = score.bars
    first = bars[0]
    lines = [PREAMBLE.rstrip('\n'),
             r'\instrumentnumber{1}', r'\setstaffs1{1}', r'\setclef1{0}', r'\setclefsymbol1{\drumclef}',
             r'\generalmeter{\meterfrac{' + str(first.beats) + '}{4}}', r'\systemnumbers', r'\parindent=0pt']
    if first.pickup:
        lines.append(r'\startbarno=0')
    if header_space > 0:
        lines.append(r'\hbox{}\vskip' + f'{header_space:.1f}' + 'pt')
    lines.append(r'\startpiece')

    # group consecutive empty bars into multi-bar rests
    units: list[list[Bar]] = []
    for bar in bars:
        if (units and bar_is_empty(bar) and bar_is_empty(units[-1][-1]) and not units[-1][-1].pickup
                and not bar.show_meter and bar.tempo is None):
            units[-1].append(bar)
        else:
            units.append([bar])

    line_used = 0.0
    line_bars = 0
    for u, unit in enumerate(units):
        bar = unit[0]
        lines.append(f'% bar {bar.number}' + (f'-{unit[-1].number}' if len(unit) > 1 else '')
                     + (' (pickup)' if bar.pickup else ''))
        if bar_is_empty(bar) and not bar.pickup:
            n = len(unit)
            lines.append(r'\vnotes' + ('7' if n == 1 else '12') + r'\elemskip'
                         + (tempo_mark(bar) if bar.tempo and bar.index else '') + r'\en')
            atnext = r'\centerHpause{' + str(n) + '}' if n > 1 else r'\centerpause'
            lines.append(r'\def\atnextbar{\znotes' + atnext + r'\en}')
            width = 7.0 if n == 1 else 12.0
        elif bar.pickup and bar_is_empty(bar):
            rests = [rest_macro(it) for it in _rests(0, bar.length, bar)]
            lines += [spacing(R * 2) + r + r'\en' for r in rests]
            width = 5.0
        else:
            groups, width = bar_groups(bar)
            lines += groups
        if len(unit) > 1:
            lines.append(r'\global\advance\barno by ' + str(len(unit) - 1))
        line_used += width
        line_bars += 1
        if u == len(units) - 1:
            break
        nxt = units[u + 1][0]
        next_width = estimate_width(nxt)
        if nxt.show_meter:
            lines.append(r'\generalmeter{\meterfrac{' + str(nxt.beats) + '}{4}}')
        if line_bars >= max_bars_per_line or (line_bars >= 1 and line_used + next_width > line_width):
            lines.append(r'\alaligne')
            line_used, line_bars = 0.0, 0
        elif nxt.show_meter:
            lines.append(r'\changecontext')
        else:
            lines.append(r'\bar')
    # a short last system is left ragged instead of being stretched across the page
    ending = r'\setdoubleBAR\raggedstoppiece' if line_used < line_width * 0.6 else r'\endpiece'
    lines += [ending, r'\bye']
    return '\n'.join(lines) + '\n'


def estimate_width(bar: Bar) -> float:
    if bar_is_empty(bar):
        return 7.0
    return bar_groups(bar)[1]


def legend_entries(score: Transcription) -> list[tuple[list[int], 'Instrument']]:
    """Instruments actually used, merged when they look identical on the page
    (e.g. GM 38 and 40 both print as the snare), hands first, high to low."""
    merged: dict[tuple, tuple[list[int], object]] = {}
    for note, inst in score.instruments_used():
        key = (inst.staff, inst.head, inst.mark, inst.part)
        if key in merged:
            merged[key][0].append(note)
        else:
            merged[key] = ([note], inst)
    return sorted(merged.values(), key=lambda e: (e[1].part != 'hand', -STAFF_LETTERS.index(e[1].staff), e[1].head))


def legend_tex(score: Transcription) -> str:
    """One page per legend entry: a short staff with that instrument's notehead.
    render_score.py crops each page and sets the (copyable) labels with XeLaTeX."""
    lines = [PREAMBLE.rstrip('\n'), r'\instrumentnumber{1}', r'\setstaffs1{1}', r'\setclef1{0}',
             r'\setclefsymbol1{\drumclef}', r'\generalmeter{\empty}', r'\parindent=0pt', r'\hsize=24mm']
    for i, (_notes, inst) in enumerate(legend_entries(score)):
        up = inst.part == 'hand'
        mark = ''
        if inst.mark:
            mark = r'\ccharnote{' + shift(inst.staff, 3 if up else -3) + '}{' + MARK_TEXT[inst.mark] + '}'
        head = SYMBOL[inst.head] + (r'\@qu{' if up else r'\@ql{') + inst.staff + '}'
        if i:
            lines.append(r'\vfill\eject')
        lines += [r'\startpiece', r'\vnotes3\elemskip\en', r'\vnotes3\elemskip' + mark + head + r'\en',
                  r'\vnotes1\elemskip\en', r'\zendpiece']
    lines.append(r'\bye')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='鼓 MIDI → MusiXTeX 源码（调试用；出 PDF 请用 build_score.py）')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', help='内置映射名（gm、fpc-default）或 YAML 路径')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        score = build_score(args.midi, args.metadata, args.drum_map)
    except ScoreError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(convert(score), encoding='ascii')
    print(f'{args.out}: {score.summary()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
