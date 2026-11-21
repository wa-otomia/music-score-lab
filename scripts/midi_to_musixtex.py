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
    'triangle': r'\tl@symbol', 'plus': r'\k@symbol', 'rhombus': r'\y@symbol',
}
MARK_TEXT = {'open': r'$\circ$', 'half-open': r'$\ominus$', 'closed': r'{\tenrm +}'}
BEAM = {'hand': 0, 'foot': 1}
CROSS_HEADS = ('x', 'circle-x')

PREAMBLE = r"""\input musixtex
\input musixper
\catcode`\@=11
\nopagenumbers
\special{papersize=210mm,297mm}
\voffset-6mm
\overfullrule=0pt
\def\tl@symbol{\def\q@u{\lower.5\internote\hbox{\musixchar116}}}
\def\vrest#1#2{\zcharnote{#1}{\musixchar#2}}
% Cross noteheads: the stem starts at the tip of the arm (upper right for up stems,
% lower left for down stems) instead of at the centre of the X.
\def\x@adj{.9\internote}
\def\xupst@m{\global\advance\st@bot\x@adj\upst@m}
\def\xdownst@m{\global\advance\st@top-\x@adj\downst@m}
\def\xbeamst@m{\global\advance\st@bot\x@adj\global\advance\st@top-\x@adj\beamst@m}
\def\xup@flag{\global\advance\st@bot\x@adj\up@flag}
\def\xdown@flag{\global\advance\st@top-\x@adj\down@flag}
\def\@xqu{\let\st@m\xupst@m\g@q}
\def\@xql{\let\st@m\xdownst@m\g@q}
\def\@xqb#1{\s@l@ctbeam#1\relax\let\st@m\xbeamst@m\g@q}
\def\@xtqh#1{\s@l@ctbeam#1\relax\C@tb\t@bbu\qn@width\let\st@m\xbeamst@m\g@q}
\def\@xtqb#1{\s@l@ctbeam#1\relax\C@tb\t@bbl\lthick\let\st@m\xbeamst@m\g@q}
\def\@xcu{\n@vii\@xl\let\st@m\xup@flag\g@q}
\def\@xccu{\n@vii\@xli\let\st@m\xup@flag\g@q}
\def\@xcl{\n@vii\@xlv\let\st@m\xdown@flag\g@q}
\def\@xccl{\n@vii46\let\st@m\xdown@flag\g@q}
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
        """Small notes before the stroke: one slashed 8th for a flam, two beamed 16ths for a
        drag (on a spare beam number, 2 for hands / 3 for feet)."""
        heads = [h for h in ordered(item.hits, self.part) if h.grace]
        if not heads:
            return ''
        count = max(h.grace for h in heads)
        if count == 1:
            routine = r'\@grcu' if self.up else r'\@grcl'
            parts = [SYMBOL[h.inst.head] + r'\@zq{' + h.inst.staff + '}' for h in heads[:-1]]
            last = heads[-1]
            parts.append(SYMBOL[last.inst.head] + routine + '{' + last.inst.staff + '}')
            return ''.join(parts)
        n, u = ('2', 'u') if self.up else ('3', 'l')
        pick = max if self.up else min
        ref = pick((h.inst.staff for h in heads), key=STAFF_LETTERS.index)
        out = rf'\ibb{u}{n}{{{ref}}}0'
        for k, end in ((0, False), (1, True)):
            these = [h for h in heads if h.grace > k]
            for h in these[:-1]:
                out += SYMBOL[h.inst.head] + r'\@zq{' + h.inst.staff + '}'
            last = these[-1]
            routine = (r'\@tqh' if self.up else r'\@tqb') if end else r'\@qb'
            out += SYMBOL[last.inst.head] + routine + n + '{' + last.inst.staff + '}'
        return out

    def chord(self, item: VoiceItem, spacing_note: bool) -> str:
        heads, shifted = self.layout(item)
        carrier = heads[-1]
        name, dots = note_type(item)
        out: list[str] = []
        for h in heads:
            out.append(self.aside(self.ornaments(h), h.note in shifted))
        # with a head moved right of an up stem, every dot goes right of that column
        dot_aside = self.up and bool(shifted)
        for h in heads[:-1]:
            if dots:
                out.append(self.aside(r'\pt{' + h.inst.staff + '}', dot_aside))
            # the far head of a second sits on the other side of the stem
            routine = (r'\@rq' if self.up else r'\@lq') if h.note in shifted else r'\@zq'
            out.append(SYMBOL[h.inst.head] + routine + '{' + h.inst.staff + '}')
        extra = self.tuplet_label(item, heads)  # beam text must follow the beam start
        if self.up and any(h.accent for h in heads):
            # one accent per chord, clear of the stem or beam
            top = max((h.inst.staff for h in heads), key=STAFF_LETTERS.index)
            extra += r'\busf' + str(self.beam) if item.beams else r'\usf{' + shift(top, 9) + '}'
        if dots:
            out.append(self.aside(r'\pt{' + carrier.inst.staff + '}', dot_aside))
        out.append(self.carrier(item, carrier, name, extra, '' if spacing_note else r'\advancefalse'))
        return ''.join(out)

    def aside(self, tex: str, moved: bool) -> str:
        """Shift ornaments of a head that sits on the far side of the stem along with it."""
        if not tex or not moved:
            return tex
        return (r'\roffset{1}{' if self.up else r'\loffset{1}{') + tex + '}'

    def layout(self, item: VoiceItem) -> tuple[list[Hit], set[int]]:
        """Heads with the stem carrier last, and the notes whose head is moved to the other
        side of the stem because they are a second away from a neighbour.  Walk from the
        stem's base (bottom for up stems, top for down stems); a head a step from an
        unshifted neighbour is shifted.  The carrier is the head at the stem's base."""
        index = STAFF_LETTERS.index
        walk = sorted(item.hits.values(), key=lambda h: (index(h.inst.staff), h.note), reverse=not self.up)
        shifted: set[int] = set()
        for prev, h in zip(walk, walk[1:]):
            if abs(index(h.inst.staff) - index(prev.inst.staff)) == 1 and prev.note not in shifted:
                shifted.add(h.note)
        carrier = walk[0]
        return [h for h in walk[1:]] + [carrier], shifted

    def ornaments(self, h: Hit) -> str:
        p = h.inst.staff
        out = ''
        if h.ghost:
            out += r'\lpar{' + p + r'}\rpar{' + p + '}'
        if h.inst.mark:
            # above the head, on the side away from a down stem's beam
            out += r'\ccharnote{' + shift(p, 3 if self.up else 2) + '}{' + MARK_TEXT[h.inst.mark] + '}'
        return out

    def tuplet_label(self, item: VoiceItem, heads: list[Hit]) -> str:
        if not item.tuplet_label:
            return ''
        number = item.tuplet
        if item.beams and not item.tuplet_bracket:
            return r'\def\txt{' + str(number) + '}' + (r'\butext' if self.up else r'\bltext') + str(self.beam)
        pick = max if self.up else min
        p = pick((h.inst.staff for h in heads), key=STAFF_LETTERS.index)
        target = shift(p, 10) if self.up else shift(p, -9)
        return r'\ccharnote{' + target + r'}{\eightit ' + str(number) + '}'

    def carrier(self, item: VoiceItem, h: Hit, name: str, accent: str = '', prefix: str = '') -> str:
        """Beam commands, then ``accent`` and ``prefix`` (e.g. \\advancefalse), then the note."""
        sym = accent + prefix + SYMBOL[h.inst.head]
        p, n = h.inst.staff, str(self.beam)
        at = r'\@x' if h.inst.head in CROSS_HEADS else '\\@'  # cross heads: stem from the arm tip
        u = 'u' if self.up else 'l'
        if not item.beams:
            routine = {'quarter': 'q', 'eighth': 'c', '16th': 'cc', 'half': 'h', 'whole': 'w'}[name]
            if routine in ('h', 'w'):
                raise ScoreError('内部错误：鼓谱音符时值不应超过四分音符')
            if routine == 'q':
                return sym + at + 'q' + u + '{' + p + '}'
            return sym + at + routine + u + '{' + p + '}'
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
            return out + sym + at + ('tqh' if self.up else 'tqb') + n + '{' + p + '}'
        return out + sym + at + 'qb' + n + '{' + p + '}'

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
    hand_t, foot_t = voice_tuplets(bar, 'hand'), voice_tuplets(bar, 'foot')
    tuplets = {**foot_t, **hand_t}
    # beats where one voice is in tuplets and the other plays straight: rests per voice only
    def plays(part: str, beat: int) -> bool:
        return any(beat * R <= t < (beat + 1) * R and any(h.inst.part == part for h in hs.values())
                   for t, hs in bar.events.items())
    mixed = {b for b in bar.triplet_beats if (b in hand_t) != (b in foot_t) and plays('hand', b) and plays('foot', b)}
    silent = [(a, b) for a, b in silent_spans(bar, voices) if not any(x * R <= a < (x + 1) * R for x in mixed)]
    for a, b in silent:
        for rest in _rests(a, b, bar, tuplets):
            timeline.setdefault(rest.start, {})['rest'] = rest
    # A rest inside a tuplet group is printed for its own voice (raised for hands, lowered
    # for feet) even while the other voice plays, so the tuplet visibly adds up.
    for part, items in voices.items():
        for it in items:
            if it.is_rest and it.tuplet_label:
                timeline.setdefault(it.start, {})[f'{part}-label'] = it
            in_mixed = (it.start // R) in mixed and it.duration < R
            if it.is_rest and (it.tuplet or in_mixed) and not any(a <= it.start < b for a, b in silent):
                timeline.setdefault(it.start, {})[f'{part}-rest'] = it
    times = sorted(timeline)
    collisions: list[int] = []
    groups: list[str] = []
    width = 0.0
    for i, t in enumerate(times):
        slot = (times[i + 1] if i + 1 < len(times) else bar.length) - t
        entry = timeline[t]
        body = ''
        if i == 0 and bar.tempo is not None and bar.index > 0:
            body += tempo_mark(bar)
        for part, pitch in (('hand', 'q'), ('foot', 'a')):
            if f'{part}-label' in entry:  # tuplet number of a group whose middle is a rest
                body += r'\ccharnote{' + pitch + r'}{\eightit ' + str(entry[f'{part}-label'].tuplet) + '}'
        for part, pitch in (('hand', 'i'), ('foot', 'a')):
            if f'{part}-rest' in entry:
                glyph = {'eighth': 63, '16th': 64, 'quarter': 62}[note_type(entry[f'{part}-rest'])[0]]
                body += r'\vrest{' + pitch + '}{' + str(glyph) + '}'
        if 'rest' in entry and not ('hand' in entry or 'foot' in entry):
            body += rest_macro(entry['rest'])
        elif not ('hand' in entry or 'foot' in entry):
            body += r'\sk'  # only a voice rest or label here: advance without a spacing note
        else:
            graces = ''.join(writers[p].grace(entry[p]) for p in ('foot', 'hand') if p in entry)
            if graces:
                size = r'\tinyvalue\tinynotesize' if r'\@tq' in graces else r'\smallvalue\smallnotesize'  # drag: beamed pair
                groups.append(r'\notes\multnoteskip' + size + graces + r'\en')
                width += 1.6 * (1 + graces.count(r'\@tq'))
            for p in ('foot', 'hand'):
                if p in entry:
                    writers[p]._current = _run_start(voices[p], entry[p])
            foot_tex = writers['foot'].chord(entry['foot'], spacing_note='hand' not in entry) if 'foot' in entry else ''
            hand_tex = writers['hand'].chord(entry['hand'], spacing_note=True) if 'hand' in entry else ''
            if foot_tex and hand_tex and voices_touch(entry['hand'], entry['foot']):
                # hand and foot heads a second apart (or on one spot): move one voice aside
                if not entry['hand'].beams:
                    hand_tex = r'\roffset{1}{' + hand_tex + '}'
                elif not entry['foot'].beams:
                    foot_tex = r'\loffset{1}{' + foot_tex + '}'
                else:
                    collisions.append(t)
            body += foot_tex + hand_tex
        groups.append(spacing(slot) + body + r'\en')
        width += 2 + math.log2(slot / (R / 4))
    bar.collisions = collisions
    return groups, width


def voices_touch(hand: VoiceItem, foot: VoiceItem) -> bool:
    index = STAFF_LETTERS.index
    low_hand = min(index(h.inst.staff) for h in hand.hits.values())
    high_foot = max(index(h.inst.staff) for h in foot.hits.values())
    return low_hand - high_foot <= 1


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

    # render every unit first, then plan systems from the estimated widths
    rendered: list[tuple[list[str], float]] = []
    for unit in units:
        bar = unit[0]
        body = [f'% bar {bar.number}' + (f'-{unit[-1].number}' if len(unit) > 1 else '')
                + (' (pickup)' if bar.pickup else '')]
        if bar_is_empty(bar) and not bar.pickup:
            n = len(unit)
            body.append(r'\vnotes' + ('7' if n == 1 else '12') + r'\elemskip'
                        + (tempo_mark(bar) if bar.tempo and bar.index else '') + r'\en')
            atnext = r'\centerHpause{' + str(n) + '}' if n > 1 else r'\centerpause'
            body.append(r'\def\atnextbar{\znotes' + atnext + r'\en}')
            width = 8.0 if n == 1 else 13.0
        elif bar.pickup and bar_is_empty(bar):
            body += [spacing(R * 2) + rest_macro(it) + r'\en' for it in _rests(0, bar.length, bar)]
            width = 5.0
        else:
            groups, width = bar_groups(bar)
            body += groups
            for t in getattr(bar, 'collisions', []):
                note = (f'第 {bar.number} 小节第 {t // R + 1} 拍：手脚两个声部的符头相邻且都带横梁，无法错开，'
                        '可能重叠；可在 note_map 中调整位置')
                if note not in score.warnings:
                    score.warnings.append(note)
        if len(unit) > 1:
            body.append(r'\global\advance\barno by ' + str(len(unit) - 1))
        meter = 3.0 if bar.show_meter and bar.index else 0.0  # a time-signature change takes room too
        rendered.append((body, width + 1.5 + meter))  # + bar line and clearance

    systems: list[list[int]] = [[]]
    used = 0.0
    for u, (_body, width) in enumerate(rendered):
        if systems[-1] and (len(systems[-1]) >= max_bars_per_line or used + width > line_width):
            systems.append([])
            used = 0.0
        systems[-1].append(u)
        used += width
    if len(systems) > 1:
        last = sum(rendered[u][1] for u in systems[-1])
        prev = sum(rendered[u][1] for u in systems[-2])
        if (last < line_width * 0.45 and prev + last <= line_width * 1.15
                and len(systems[-2]) + len(systems[-1]) <= max_bars_per_line + 1):
            tail = systems.pop()  # avoid a lonely, stretched last system
            systems[-1] += tail

    starts = {s_[0] for s_ in systems}
    for u, (body, _width) in enumerate(rendered):
        lines += body
        if u == len(rendered) - 1:
            break
        nxt = units[u + 1][0]
        if nxt.show_meter:
            lines.append(r'\generalmeter{\meterfrac{' + str(nxt.beats) + '}{4}}')
        if u + 1 in starts:
            lines.append(r'\alaligne')
        elif nxt.show_meter:
            lines.append(r'\changecontext')
        else:
            lines.append(r'\bar')
    lines += [r'\setdoubleBAR\endpiece', r'\bye']
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
            mark = r'\ccharnote{' + shift(inst.staff, 3 if up else 2) + '}{' + MARK_TEXT[inst.mark] + '}'
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
