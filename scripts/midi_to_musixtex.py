#!/usr/bin/env python3
"""Translate the notation model (score_core) into MusiXTeX source.

Only responsible for "how to draw"; rhythm, durations and beam levels all come from score_core and are not re-inferred here.

- Noteheads: musixper/musixdia symbol definitions combined with the generic MusiXTeX drawing routines, e.g.
  ``\\do@symbol\\@qb0{n}`` is a beamed cross notehead.
- Hands (upper voice) use beam 0 with stems up; feet (lower voice) use beam 1 with stems down.
- A rest is printed (centred) only where both voices rest; each voice's own full rests are written in the MusicXML.
- Empty bars print a whole-bar rest; consecutive empty bars merge into a multi-bar rest.
- The output is ASCII only; the Japanese title, credits and legend text are typeset separately by render_score.py with XeLaTeX.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from score_core import (R, STAFF_LETTERS, Bar, Hit, ScoreError, Transcription, VoiceItem, build_score,
                        note_type, voice_items, voice_tuplets, _rests)
from score_structure import MeasureUnit, plan_units

DEFAULT_LINE_WIDTH = 104.0

PLAIN_TEX_ESCAPES = {
    '\\': r'$\backslash$',
    '{': r'$\{$',
    '}': r'$\}$',
    '#': r'\#',
    '$': r'\$',
    '%': r'\%',
    '&': r'\&',
    '_': r'\_',
    '^': r'{\eighttt\char94}',
    '~': r'{\eighttt\char126}',
    '<': r'$<$',
    '>': r'$>$',
    '|': r'$\vert$',
    '"': r'{\eighttt\char34}',
}


def escape_tex_ascii(text: str) -> str:
    """Escape printable ASCII for Plain TeX inside MusiXTeX music mode."""
    return ''.join(PLAIN_TEX_ESCAPES.get(c, c) for c in text)

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
% Avoid stray space tokens after \generalmeter{...} newlines inside horizontal music mode.
\let\orig@generalmeter\generalmeter
\def\generalmeter#1{\orig@generalmeter{#1}\ignorespaces}
% Boxed rehearsal mark for section labels (bold, crisp 0.6pt border).
\font\eighttt=cmtt8
\def\rehearsal#1{\vbox{\hrule height.6pt\hbox{\vrule width.6pt\kern2.5pt\vbox{\kern2pt\hbox{\ninebf #1}\kern2pt}\kern2.5pt\vrule width.6pt}\hrule height.6pt}}
% Volta brackets clear high cymbal stems/open marks; bold Nx count sits above closing :| when times > 2.
\def\raisevolta{9\internote}
\def\repeatcount#1#2{\llap{\raise#1\internote\hbox{\eightbf #2}\kern1pt}}
% Simile repeat symbols: numbered 1-bar % and barline-centered 2-bar // (pure vector paths + numeral).
\def\csimile#1{\hbox{\duevolte\raise9.8\internote\hbox to0pt{\hss\eightbf #1\hss}}}
\def\similetwo{\kern-.5\lthick\lrlap{\hbox{%
  \special{pdf: content q 0 g
    -7.9 5.0 m -6.1 5.0 l 3.9 15.0 l 2.1 15.0 l f
    -3.9 5.0 m -2.1 5.0 l 7.9 15.0 l 6.1 15.0 l f
    -4.75 12.45 m -4.75 13.00 -5.20 13.45 -5.75 13.45 c -6.30 13.45 -6.75 13.00 -6.75 12.45 c -6.75 11.90 -6.30 11.45 -5.75 11.45 c -5.20 11.45 -4.75 11.90 -4.75 12.45 c f
    6.75 7.47 m 6.75 8.02 6.30 8.47 5.75 8.47 c 5.20 8.47 4.75 8.02 4.75 7.47 c 4.75 6.92 5.20 6.47 5.75 6.47 c 6.30 6.47 6.75 6.92 6.75 7.47 c f
    Q}%
  \raise9.8\internote\hbox to0pt{\hss\eightbf 2\hss}%
}}\kern.5\lthick}
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
                raise ScoreError('internal error: drum-score note durations must not exceed a quarter note')
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


def _tempo_pitch_steps(bar: Bar) -> int:
    letters = [h.inst.staff for hits in bar.events.values() for h in hits.values() if h.inst.part == 'hand']
    top = max(letters, key=STAFF_LETTERS.index) if letters else 'm'
    return min(ord('z'), max(ord('q'), ord(top) + 11)) - ord('e')


def tempo_mark(bar: Bar) -> str:
    """Metronome mark placed clear of the highest stem in the bar."""
    pitch = chr(ord('e') + _tempo_pitch_steps(bar))
    return r'\zcharnote{' + pitch + r'}{\metron{\qu}{' + f'{bar.tempo:g}' + '}}'


def _hand_clearance_steps(bar: Bar, minimum: int = 14) -> int:
    """Vertical pitch height (in internotes above bottom line 'e') clearing hand ink in ``bar``."""
    hand_hits = [h for hits in bar.events.values() for h in hits.values() if h.inst.part == 'hand']
    if not hand_hits:
        return minimum
    top = max((h.inst.staff for h in hand_hits), key=STAFF_LETTERS.index)
    top_steps = STAFF_LETTERS.index(top) - STAFF_LETTERS.index('e')
    pitch = max(minimum, top_steps + 8)
    if any(h.accent for h in hand_hits) or voice_tuplets(bar, 'hand'):
        pitch = max(pitch, top_steps + 10)
    return pitch


def rehearsal_mark(bar: Bar) -> str:
    """Boxed rehearsal label placed clear of hand stems/marks/accents and any tempo mark."""
    assert bar.section is not None
    pitch = _hand_clearance_steps(bar, minimum=14)
    if bar.tempo is not None and bar.index > 0:
        pitch = max(pitch, _tempo_pitch_steps(bar) + 8)
    return r'\zcharnote{' + str(pitch) + r'}{\rehearsal{' + escape_tex_ascii(bar.section) + '}}'


def repeat_count_mark(unit: MeasureUnit) -> str:
    """Bold ``Nx`` label placed above a closing ``:|`` repeat barline when ``times > 2``."""
    assert unit.repeat_end is not None and unit.repeat_end > 2
    pitch = _hand_clearance_steps(unit.last, minimum=15)
    return r'\repeatcount{' + str(pitch) + '}{' + str(unit.repeat_end) + 'x}'


def bar_is_empty(bar: Bar) -> bool:
    return not bar.events


def bar_groups(bar: Bar, *, beam_eighths: str = 'beat') -> tuple[list[str], float]:
    """TeX note groups for one non-empty bar and its estimated width in elemskips."""
    voices = {part: voice_items(bar, part, beam_eighths=beam_eighths) for part in ('hand', 'foot')}
    writers = {part: VoiceWriter(part, bar) for part in voices}
    for part, items in voices.items():
        writers[part].start_bar_beams(items)
    timeline: dict[int, dict] = {}
    for part, items in voices.items():
        for it in items:
            if not it.is_rest:
                timeline.setdefault(it.start, {})[part] = it
    # Every voice fills every beat: each voice's rests are printed (hands above, feet
    # below).  Two rests of the same length at the same moment share one centred rest.
    rests: dict[int, dict[str, VoiceItem]] = {}
    for part, items in voices.items():
        for it in items:
            if it.is_rest:
                rests.setdefault(it.start, {})[part] = it
                if it.tuplet_label:
                    timeline.setdefault(it.start, {})[f'{part}-label'] = it
    for t, pair in rests.items():
        hand, foot = pair.get('hand'), pair.get('foot')
        if hand and foot and (hand.duration, hand.tuplet) == (foot.duration, foot.tuplet):
            timeline.setdefault(t, {})['rest'] = hand
        else:
            for part, it in pair.items():
                if it.measure_rest:
                    continue  # placed in the middle of the bar below
                timeline.setdefault(t, {})[f'{part}-rest'] = it
    for part, items in voices.items():
        if len(items) == 1 and items[0].measure_rest and not (rests.get(0, {}).keys() >= {'hand', 'foot'}):
            # one voice silent for the whole bar: its whole rest goes near the middle
            middle = min(timeline, key=lambda x: (abs(x - bar.length / 2), x)) if timeline else 0
            timeline.setdefault(middle, {})[f'{part}-rest'] = items[0]
    times = sorted(timeline)
    collisions: list[int] = []
    groups: list[str] = []
    width = 0.0
    for i, t in enumerate(times):
        slot = (times[i + 1] if i + 1 < len(times) else bar.length) - t
        entry = timeline[t]
        body = ''
        if i == 0 and bar.section is not None:
            body += rehearsal_mark(bar)
        if i == 0 and bar.tempo is not None and bar.index > 0:
            body += tempo_mark(bar)
        for part, pitch in (('hand', 'q'), ('foot', 'a')):
            if f'{part}-label' in entry:  # tuplet number of a group whose middle is a rest
                body += r'\ccharnote{' + pitch + r'}{\eightit ' + str(entry[f'{part}-label'].tuplet) + '}'
        for part in ('hand', 'foot'):
            if f'{part}-rest' in entry:
                body += voice_rest(entry[f'{part}-rest'], part)
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


# Rest glyphs and the pitch letter they are hung at, per voice.  MusiXTeX's own centred
# rests correspond to: whole 'k' (hangs from the 4th line), half 'i' (sits on the middle
# line), shorter rests 'e'.  Hand rests go two staff spaces higher, foot rests lower.
REST_GLYPH = {'whole': 61, 'half': 60, 'quarter': 62, 'eighth': 63, '16th': 64}
REST_PITCH = {'hand': {'whole': 'm', 'half': 'm', 'other': 'i'},
              'foot': {'whole': 'g', 'half': 'e', 'other': 'a'}}


def voice_rest(item: VoiceItem, part: str) -> str:
    name, dots = note_type(item)
    pitch = REST_PITCH[part].get(name, REST_PITCH[part]['other'])
    dot = r'\kern.2\qn@width\raise.7\internote\hbox{\musixchar0}' if dots else ''
    return r'\zcharnote{' + pitch + r'}{\musixchar' + str(REST_GLYPH[name]) + dot + '}'


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


def plan_systems(units: list[MeasureUnit], widths: list[float], *,
                 line_width: float = DEFAULT_LINE_WIDTH,
                 max_bars_per_line: int = 4) -> list[list[int]]:
    """Choose phrase-aligned system breaks via dynamic programming.

    Logical bar span counts 2 for ``simile-2`` (which is atomic and never split) and 1 for
    ``bar``, ``simile-1``, and ``multi-rest``.  When the piece starts with a pickup bar,
    system 1 may hold the pickup plus up to ``max_bars_per_line`` logical bars (when width
    fits within ``1.08 * line_width``) so bars 1-4 stay together on the opening line.
    """
    n = len(units)
    if n == 0:
        return []
    spans = [2 if u.kind == 'simile-2' else 1 for u in units]
    pref_w = [0.0] * (n + 1)
    pref_s = [0] * (n + 1)
    for k in range(n):
        pref_w[k + 1] = pref_w[k] + widths[k]
        pref_s[k + 1] = pref_s[k] + spans[k]

    has_pickup = units[0].first.pickup
    anchors: list[int] = []
    anchor = 1
    for u in units:
        if u.first.section is not None:
            anchor = u.first.number
        anchors.append(anchor)

    inf = float('inf')
    dp = [inf] * (n + 1)
    nxt = [-1] * (n + 1)
    dp[n] = 0.0

    for i in range(n - 1, -1, -1):
        first_pickup = i == 0 and has_pickup
        for j in range(i + 1, n + 1):
            total_span = pref_s[j] - pref_s[i]
            eff_span = total_span - (1 if first_pickup else 0)
            w = pref_w[j] - pref_w[i]
            is_last = j == n

            if j > i + 1:
                if first_pickup:
                    if eff_span > max_bars_per_line:
                        break
                    cap = 1.08 * line_width if total_span > max_bars_per_line else 1.12 * line_width
                    if w > cap:
                        break
                else:
                    max_span = max_bars_per_line + (1 if is_last else 0)
                    if eff_span > max_span:
                        break
                    if w > 1.12 * line_width:
                        break

            cost = 12.0  # per-line cost
            if first_pickup and j == 1:
                cost += 120.0
            elif eff_span == max_bars_per_line:
                cost += 0.0
            elif is_last and eff_span == max_bars_per_line + 1:
                cost += 16.0
            elif eff_span == 2:
                cost += 14.0
            elif eff_span == 3:
                cost += 22.0
            elif eff_span == 1:
                cost += 65.0
            else:
                cost += 10.0 * abs(max_bars_per_line - eff_span)

            last_bar = units[j - 1].last
            if not last_bar.pickup and (last_bar.number - anchors[j - 1] + 1) % 4 == 0:
                cost -= 12.0

            # Reward breaking at section/repeat boundaries (never isolating pickup bar 0)
            boundary_reward = 0.0
            if j < n and not last_bar.pickup:
                if units[j].first.section is not None:
                    boundary_reward = max(boundary_reward, 28.0)
                if units[j].repeat_start:
                    boundary_reward = max(boundary_reward, 18.0)
                if units[j - 1].volta_stop == 'discontinue':
                    boundary_reward = max(boundary_reward, 20.0)
                elif units[j - 1].repeat_end is not None and units[j - 1].volta_stop is None:
                    boundary_reward = max(boundary_reward, 20.0)
            cost -= boundary_reward

            # Avoid splitting a volta bracket or splitting a short 1./2. volta pair across lines
            if j < n:
                if units[j - 1].volta_start is not None and units[j - 1].volta_stop is None:
                    cost += 24.0
                elif units[j - 1].volta_stop == 'stop' and units[j].volta_start == '2':
                    cost += 18.0

            if i > 0 and units[i].kind in ('simile-1', 'simile-2'):
                cost += 4.0

            if w > line_width:
                excess = (w - line_width) / line_width
                cost += 40.0 * excess + 250.0 * excess * excess
            elif not is_last and eff_span < max_bars_per_line and w < 0.55 * line_width:
                deficit = (0.55 * line_width - w) / line_width
                cost += 30.0 * deficit * deficit

            total = cost + dp[j]
            if total < dp[i]:
                dp[i] = total
                nxt[i] = j

    systems: list[list[int]] = []
    cur = 0
    while cur < n:
        end = nxt[cur]
        systems.append(list(range(cur, end)))
        cur = end
    return systems


def convert_with_layout(score: Transcription, *, header_space: float = 0.0,
                        line_width: float = DEFAULT_LINE_WIDTH,
                        max_bars_per_line: int = 4,
                        no_simile_bars: set[int] | frozenset[int] = frozenset()
                        ) -> tuple[str, list[list[MeasureUnit]]]:
    """Full MusiXTeX document plus the exact list of ``MeasureUnit`` objects per system.

    ``header_space`` (pt) is left blank above the first system for the XeLaTeX title block;
    ``line_width`` is the elemskip budget per system; ``no_simile_bars`` lists 0-based bar
    indices that must be engraved in full (e.g. the first bar of a new PDF page).
    """
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

    units = plan_units(bars, repeats=score.settings.repeats,
                       repeat_counters=score.settings.repeat_counters,
                       no_simile_bars=no_simile_bars)

    # Raise volta brackets slightly higher if any volta bar in the score has accents/tuplets/high cymbals.
    volta_bars: list[Bar] = []
    in_volta = False
    for u in units:
        if u.volta_start is not None:
            in_volta = True
        if in_volta:
            volta_bars.extend(u.bars)
        if u.volta_stop is not None:
            in_volta = False
    if volta_bars:
        needed = max(_hand_clearance_steps(b, minimum=16) for b in volta_bars)
        if needed > 17:
            lines.insert(lines.index(r'\startpiece'), r'\def\raisevolta{' + str(needed - 7) + r'\internote}')

    # render every unit first, then plan systems from the estimated widths
    rendered: list[tuple[list[str], float]] = []
    for unit in units:
        bar = unit.first
        rep_count = repeat_count_mark(unit) if (unit.repeat_end is not None and unit.repeat_end > 2) else ''
        if unit.kind == 'multi-rest':
            n = len(unit.bars)
            marks = ((rehearsal_mark(bar) if bar.section is not None else '')
                     + (tempo_mark(bar) if bar.tempo and bar.index else ''))
            body = [f'% bar {bar.number}-{unit.last.number}',
                    r'\vnotes12\elemskip' + marks + r'\en',
                    r'\def\atnextbar{\znotes\centerHpause{' + str(n) + '}' + rep_count + r'\en}%',
                    r'\global\advance\barno by ' + str(n - 1)]
            width = 13.0
        elif unit.kind == 'simile-1':
            glyph = r'\csimile{' + str(unit.counter) + '}' if unit.counter is not None else r'\hbox{\duevolte}'
            body = [f'% bar {bar.number} (simile)',
                    r'\vnotes7\elemskip\en',
                    r'\def\atnextbar{\znotes\centerbar{' + glyph + '}' + rep_count + r'\en}%']
            width = 7.0
        elif unit.kind == 'simile-2':
            body = [f'% bar {bar.number}-{unit.last.number} (simile-2)',
                    r'\vnotes7\elemskip\en',
                    r'\def\atnextbar{\znotes\similetwo\en}%',
                    r'\bar',
                    r'\vnotes7\elemskip\en']
            if rep_count:
                body.append(r'\def\atnextbar{\znotes' + rep_count + r'\en}%')
            width = 15.5
        else:
            body = [f'% bar {bar.number}' + (' (pickup)' if bar.pickup else '')]
            if bar_is_empty(bar) and not bar.pickup:
                marks = ((rehearsal_mark(bar) if bar.section is not None else '')
                         + (tempo_mark(bar) if bar.tempo and bar.index else ''))
                body.append(r'\vnotes7\elemskip' + marks + r'\en')
                if rep_count:
                    body.append(r'\def\atnextbar{\znotes\centerpause' + rep_count + r'\en}%')
                else:
                    body.append(r'\def\atnextbar{\znotes\centerpause\en}')
                width = 8.0
            elif bar.pickup and bar_is_empty(bar):
                body += [spacing(R * 2) + rest_macro(it) + r'\en' for it in _rests(0, bar.length, bar)]
                width = 5.0
            else:
                groups, width = bar_groups(bar, beam_eighths=score.settings.beam_eighths)
                body += groups
                if rep_count:
                    body.append(r'\def\atnextbar{\znotes' + rep_count + r'\en}%')
                for t in getattr(bar, 'collisions', []):
                    note = (f'Bar {bar.number}, beat {t // R + 1}: the hand and foot noteheads are adjacent and both beamed, so they cannot be offset '
                            'and may overlap; adjust the position in note_map')
                    if note not in score.warnings:
                        score.warnings.append(note)
        meter = 3.0 if bar.show_meter and bar.index else 0.0  # a time-signature change takes room too
        rep_w = (2.5 if unit.repeat_start else 0.0) + (2.5 if unit.repeat_end is not None else 0.0)
        rendered.append((body, width + 1.5 + meter + rep_w))  # + bar line, clearance, and repeat barlines

    widths = [w for _body, w in rendered]
    systems = plan_systems(units, widths, line_width=line_width, max_bars_per_line=max_bars_per_line)

    if units and units[0].repeat_start:
        lines.append(r'\zleftrepeat')

    starts = {s_[0] for s_ in systems}
    for u, (body, _width) in enumerate(rendered):
        lines += body
        unit = units[u]
        if u == len(rendered) - 1:
            if unit.volta_stop == 'stop':
                lines.append(r'\setendvoltabox')
            elif unit.volta_stop == 'discontinue':
                lines.append(r'\setendvolta')
            break
        nxt_unit = units[u + 1]
        nxt = nxt_unit.first
        rep_end = unit.repeat_end is not None
        rep_start = nxt_unit.repeat_start
        dbl = nxt_unit.double_bar_before
        if unit.volta_stop == 'stop':
            lines.append(r'\setendvoltabox')
        elif unit.volta_stop == 'discontinue':
            lines.append(r'\setendvolta')
        if nxt_unit.volta_start is not None:
            lines.append(r'\Setvolta{' + nxt_unit.volta_start + r'}%')
        if nxt.show_meter:
            lines.append(r'\generalmeter{\meterfrac{' + str(nxt.beats) + '}{4}}')
        if u + 1 in starts:
            if rep_end:
                lines.append(r'\setrightrepeat')
            elif dbl:
                lines.append(r'\setdoublebar')
            lines.append(r'\alaligne')
            if rep_start:
                lines.append(r'\zleftrepeat')
        elif nxt.show_meter:
            if rep_end:
                lines.append(r'\setrightrepeat')
                lines.append(r'\changecontext')
            elif dbl:
                lines.append(r'\Changecontext')
            else:
                lines.append(r'\changecontext')
            if rep_start:
                lines.append(r'\zleftrepeat')
        else:
            if rep_end and rep_start:
                lines.append(r'\leftrightrepeat')
            elif rep_end:
                lines.append(r'\rightrepeat')
            elif rep_start:
                lines.append(r'\leftrepeat')
            elif dbl:
                lines.append(r'\doublebar')
            else:
                lines.append(r'\bar')
    final_end = r'\setrightrepeat\endpiece' if (units and units[-1].repeat_end is not None) else r'\setdoubleBAR\endpiece'
    lines += [final_end, r'\bye']
    system_units = [[units[u] for u in s_] for s_ in systems]
    return '\n'.join(lines) + '\n', system_units


def convert(score: Transcription, *, header_space: float = 0.0,
            line_width: float = DEFAULT_LINE_WIDTH,
            max_bars_per_line: int = 4,
            no_simile_bars: set[int] | frozenset[int] = frozenset()) -> str:
    """Full MusiXTeX document.  ``header_space`` (pt) is left blank above the first system
    for the XeLaTeX title block; ``line_width`` is the elemskip budget per system."""
    tex, _systems = convert_with_layout(score, header_space=header_space, line_width=line_width,
                                        max_bars_per_line=max_bars_per_line,
                                        no_simile_bars=no_simile_bars)
    return tex


def estimate_width(bar: Bar, *, beam_eighths: str = 'beat') -> float:
    if bar_is_empty(bar):
        return 7.0
    return bar_groups(bar, beam_eighths=beam_eighths)[1]


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
    parser = argparse.ArgumentParser(description='Drum MIDI -> MusiXTeX source (for debugging; use build_score.py to make a PDF)')
    parser.add_argument('midi', type=Path)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--drum-map', help='bundled map name (gm, fpc-default) or YAML path')
    parser.add_argument('--repeats', choices=['off', 'simile', 'full'], default=None,
                        help='repeat notation: simile (default), full (with |: ... :| and voltas), or off; overrides metadata')
    parser.add_argument('--beam-eighths', choices=['beat', 'half-bar'], default=None,
                        help='eighth-note beaming in 4/4: beat (default) or half-bar; overrides metadata')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'repeats': args.repeats, 'beam_eighths': args.beam_eighths})
    except ScoreError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(convert(score), encoding='ascii')
    print(f'{args.out}: {score.summary()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
