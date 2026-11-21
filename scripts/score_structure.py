"""Shared structural planning for drum scores (used by both MusicXML and MusiXTeX writers).

Turns the linear sequence of quantized ``Bar`` objects from ``score_core`` into an ordered list
of indivisible ``MeasureUnit`` items:

- ``bar``: one normally engraved measure (including pickup bars and isolated empty bars)
- ``multi-rest``: two or more consecutive empty non-pickup bars (broken by meter/tempo/section changes)
- ``simile-1``: one-bar repeat (``%``) matching the immediately preceding non-empty bar
- ``simile-2``: two-bar repeat (``//``) matching the immediately preceding two-bar pattern ``A | B``

Both output formats translate these units directly so MusicXML and PDF always agree.
"""
from __future__ import annotations

from dataclasses import dataclass

from score_core import Bar

REPEAT_MODES = ('off', 'simile')


@dataclass(frozen=True)
class MeasureUnit:
    """One structural unit in the engraved score."""
    kind: str                     # 'bar' | 'multi-rest' | 'simile-1' | 'simile-2'
    bars: tuple[Bar, ...]
    counter: int | None = None    # 2, 3, 4... for runs of >=2 consecutive simile-1 bars

    @property
    def first(self) -> Bar:
        return self.bars[0]

    @property
    def last(self) -> Bar:
        return self.bars[-1]


def bar_signature(bar: Bar) -> tuple:
    """Visual/musical identity of a bar for repeat detection.

    Matches on staff position, notehead, open/closed mark, voice, grace count, ghost and accent
    so instruments that engrave identically (e.g. GM 38 and 40 both printing as snare) compare
    equal while any distinct symbol, articulation, meter or tuplet difference prevents matching.
    """
    events = tuple(
        (tick, tuple(sorted(
            (h.inst.staff, h.inst.head, h.inst.mark or '', h.inst.part, h.grace, h.ghost, h.accent)
            for h in hits.values()
        )))
        for tick, hits in sorted(bar.events.items())
    )
    return (bar.beats, bar.beat_type, tuple(sorted(bar.triplet_beats.items())), events)


def _can_repeat_bar(bar: Bar, no_simile_bars: set[int] | frozenset[int]) -> bool:
    return (bool(bar.events) and not bar.pickup and not bar.show_meter
            and bar.tempo is None and bar.section is None
            and bar.index not in no_simile_bars)


def has_double_bar_before(bars: list[Bar], index: int) -> bool:
    """True when a double barline precedes ``bars[index]`` (section start, except at
    the start of the score or immediately after a pickup bar)."""
    return (0 < index < len(bars)
            and bars[index].section is not None
            and not bars[index - 1].pickup)


def plan_units(bars: list[Bar], *, repeats: str = 'simile', repeat_counters: bool = True,
               no_simile_bars: set[int] | frozenset[int] = frozenset()) -> list[MeasureUnit]:
    """Group bars into multi-bar rests and (when enabled) 1-bar / 2-bar simile repeats.

    ``no_simile_bars`` lists 0-based ``bar.index`` values that must be engraved in full (for
    example, the first bar on a new PDF page so the reader never sees ``%`` or ``//`` after a
    page turn).
    """
    if repeats not in REPEAT_MODES:
        raise ValueError(f'Unknown repeats mode {repeats!r}; expected one of {", ".join(REPEAT_MODES)}')

    sigs = [bar_signature(b) for b in bars]
    units: list[MeasureUnit] = []
    i = 0
    n = len(bars)

    while i < n:
        bar = bars[i]
        # 1. Empty bars: pickup stays a single bar; >=2 consecutive empty full bars merge.
        if not bar.events:
            if bar.pickup:
                units.append(MeasureUnit('bar', (bar,)))
                i += 1
                continue
            j = i
            while (j + 1 < n and not bars[j + 1].events and not bars[j + 1].pickup
                   and not bars[j + 1].show_meter and bars[j + 1].tempo is None
                   and bars[j + 1].section is None):
                j += 1
            if j > i:
                units.append(MeasureUnit('multi-rest', tuple(bars[i:j + 1])))
            else:
                units.append(MeasureUnit('bar', (bar,)))
            i = j + 1
            continue

        # 2. Repeats disabled: emit every non-empty bar directly.
        if repeats == 'off':
            units.append(MeasureUnit('bar', (bar,)))
            i += 1
            continue

        # 3. 1-bar simile (%): bar matches the immediately preceding non-empty, non-pickup bar
        #    (which must itself be a plain bar or a previous simile-1, never a simile-2).
        if (i >= 1 and _can_repeat_bar(bar, no_simile_bars)
                and units and units[-1].kind in ('bar', 'simile-1')
                and bool(bars[i - 1].events) and not bars[i - 1].pickup
                and sigs[i] == sigs[i - 1]):
            units.append(MeasureUnit('simile-1', (bar,)))
            i += 1
            continue

        # 4. 2-bar simile (//): bars[i..i+1] (A != B) match the immediately preceding 2-bar pair,
        #    where the template is either two plain non-empty bars or a preceding simile-2.
        if (i >= 2 and i + 1 < n
                and _can_repeat_bar(bars[i], no_simile_bars)
                and _can_repeat_bar(bars[i + 1], no_simile_bars)
                and sigs[i] != sigs[i + 1]
                and sigs[i] == sigs[i - 2] and sigs[i + 1] == sigs[i - 1]):
            prev_ok = (
                (bool(units) and units[-1].kind == 'simile-2'
                 and units[-1].bars[0] is bars[i - 2] and units[-1].bars[1] is bars[i - 1])
                or (len(units) >= 2 and units[-2].kind == 'bar' and units[-1].kind == 'bar'
                    and units[-2].bars[0] is bars[i - 2] and units[-1].bars[0] is bars[i - 1]
                    and bool(bars[i - 2].events) and not bars[i - 2].pickup
                    and _can_repeat_bar(bars[i - 1], no_simile_bars))
            )
            if prev_ok:
                units.append(MeasureUnit('simile-2', (bars[i], bars[i + 1])))
                i += 2
                continue

        units.append(MeasureUnit('bar', (bar,)))
        i += 1

    # Assign repeat-run counters (2, 3, 4...) to runs of >=2 consecutive simile-1 bars.
    # A single isolated % (2 bars total: A | %) stays unnumbered; 2-bar // always prints "2"
    # as part of the symbol itself and does not carry a run counter.
    if repeat_counters:
        u = 0
        while u < len(units):
            if units[u].kind == 'simile-1':
                v = u
                while v < len(units) and units[v].kind == 'simile-1':
                    v += 1
                if v - u >= 2:
                    for offset in range(v - u):
                        orig = units[u + offset]
                        units[u + offset] = MeasureUnit(orig.kind, orig.bars, counter=offset + 2)
                u = v
            else:
                u += 1

    return units


def multi_rest_lengths(bars: list[Bar]) -> dict[int, int]:
    """Index of the first bar of each run of >=2 empty bars -> run length."""
    return {unit.first.index: len(unit.bars)
            for unit in plan_units(bars, repeats='off')
            if unit.kind == 'multi-rest'}


def measure_repeat_events(units: list[MeasureUnit]) -> dict[int, list[tuple[str, int | None]]]:
    """Map 0-based bar index -> ordered MusicXML <measure-repeat> transitions.

    Each entry is ``('start', 1)``, ``('start', 2)``, or ``('stop', None)`` to be emitted inside
    ``<attributes><measure-style>`` on that measure.  No trailing ``stop`` is emitted past the
    last measure of the score.
    """
    events: dict[int, list[tuple[str, int | None]]] = {}
    active: int | None = None
    for unit in units:
        want = 1 if unit.kind == 'simile-1' else 2 if unit.kind == 'simile-2' else None
        if want != active:
            idx = unit.first.index
            if active is not None:
                events.setdefault(idx, []).append(('stop', None))
            if want is not None:
                events.setdefault(idx, []).append(('start', want))
            active = want
    return events
