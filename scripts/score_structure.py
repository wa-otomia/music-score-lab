"""Shared structural planning for drum scores (used by both MusicXML and MusiXTeX writers).

Turns the linear sequence of quantized ``Bar`` objects from ``score_core`` into an ordered list
of indivisible ``MeasureUnit`` items:

- ``bar``: one normally engraved measure (including pickup bars and isolated empty bars)
- ``multi-rest``: two or more consecutive empty non-pickup bars (broken by meter/tempo/section changes)
- ``simile-1``: one-bar repeat (``%``) matching the immediately preceding non-empty bar
- ``simile-2``: two-bar repeat (``//``) matching the immediately preceding two-bar pattern ``A | B``

When ``repeats='full'``, phrase-aligned repeated sections are folded into ``|: ... :|`` repeat
blocks and 1st/2nd ending voltas before running multi-rest and simile grouping within each
structural segment.

Both output formats translate these units directly so MusicXML and PDF always agree.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from score_core import Bar

REPEAT_MODES = ('off', 'simile', 'full')
REPEAT_BODY_LENGTHS = (4, 8, 16)
VOLTA_ENDING_LENGTHS = (1, 2)


@dataclass(frozen=True)
class MeasureUnit:
    """One structural unit in the engraved score."""
    kind: str                      # 'bar' | 'multi-rest' | 'simile-1' | 'simile-2'
    bars: tuple[Bar, ...]
    counter: int | None = None     # 2, 3, 4... for runs of >=2 consecutive simile-1 bars
    repeat_start: bool = False     # |: on left of unit.first
    repeat_end: int | None = None  # :| (total plays >= 2) on right of unit.last
    volta_start: str | None = None # '1' or '2' starting on unit.first
    volta_stop: str | None = None  # 'stop' (end of 1st ending) | 'discontinue' (end of 2nd ending) on unit.last
    double_bar_before: bool = False
    printed_start: int = 0         # sequential engraved bar number (0 for pickup, then 1, 2, ...)

    @property
    def first(self) -> Bar:
        return self.bars[0]

    @property
    def last(self) -> Bar:
        return self.bars[-1]


@dataclass(frozen=True)
class RepeatBlock:
    """One folded repeat or 1st/2nd ending volta spanning ``bars[start:end]``."""
    kind: str           # 'plain' | 'volta'
    start: int          # 0-based index in ``bars``
    end: int            # exclusive 0-based index in ``bars``
    body_len: int       # L in (4, 8, 16)
    times: int          # >= 2 for 'plain'; 2 for 'volta'
    ending_len: int = 0 # 0 for 'plain'; e in (1, 2) for 'volta'

    @property
    def saved_bars(self) -> int:
        if self.kind == 'plain':
            return (self.times - 1) * self.body_len
        return self.body_len - self.ending_len


@dataclass(frozen=True)
class _BarMark:
    bar: Bar
    repeat_start: bool = False
    repeat_end: int | None = None
    volta_start: str | None = None
    volta_stop: str | None = None


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


def strict_bar_signature(bar: Bar) -> tuple:
    """Exact bar identity including MIDI note numbers (for lossless repeat folding)."""
    events = tuple(
        (tick, tuple(sorted(
            (h.note, h.inst.staff, h.inst.head, h.inst.mark or '', h.inst.part,
             h.grace, h.ghost, h.accent)
            for h in hits.values()
        )))
        for tick, hits in sorted(bar.events.items())
    )
    return (bar.beats, bar.beat_type, tuple(sorted(bar.triplet_beats.items())), events)


def _can_repeat_bar(bar: Bar, no_simile_bars: set[int] | frozenset[int]) -> bool:
    return (bool(bar.events) and not bar.pickup and not bar.show_meter
            and bar.tempo is None and bar.section is None
            and bar.index not in no_simile_bars)


def _is_plain_interior(bar: Bar) -> bool:
    return not bar.pickup and not bar.show_meter and bar.tempo is None and bar.section is None


def has_double_bar_before(bars: list[Bar], index: int) -> bool:
    """True when a double barline precedes ``bars[index]`` (section start, except at
    the start of the score or immediately after a pickup bar)."""
    return (0 < index < len(bars)
            and bars[index].section is not None
            and not bars[index - 1].pickup)


def select_repeat_blocks(bars: list[Bar]) -> list[RepeatBlock]:
    """Select non-overlapping phrase-aligned repeat and 1st/2nd volta blocks via DP.

    Maximizes ``(total_bars_saved, -num_blocks)`` (breaking equal-score ties in favor of
    folding earlier blocks first).
    """
    n = len(bars)
    if n == 0:
        return []

    vis_sigs = [bar_signature(b) for b in bars]
    strict_sigs = [strict_bar_signature(b) for b in bars]

    first_non_pickup = 1 if bars[0].pickup else 0
    anchor = first_non_pickup
    latest_anchor: list[int] = [anchor] * n
    for idx, b in enumerate(bars):
        if not b.pickup and (idx == first_non_pickup or b.section is not None or b.show_meter):
            anchor = idx
        latest_anchor[idx] = anchor

    cands_at: list[list[RepeatBlock]] = [[] for _ in range(n)]
    for i in range(n):
        if bars[i].pickup or (i - latest_anchor[i]) % 4 != 0:
            continue

        # a. Plain repeats: |: body (L) :| x times
        for length in REPEAT_BODY_LENGTHS:
            if i + 2 * length > n:
                continue
            body = bars[i:i + length]
            if not any(b.events for b in body):
                continue
            if len({vis_sigs[j] for j in range(i, i + length)}) < 2:
                continue
            if not all(_is_plain_interior(b) for b in bars[i + 1:i + length]):
                continue
            k = 1
            while i + (k + 1) * length <= n:
                pass_start = i + k * length
                if not all(_is_plain_interior(b) for b in bars[pass_start:pass_start + length]):
                    break
                if not all(strict_sigs[pass_start + d] == strict_sigs[i + d] for d in range(length)):
                    break
                cands_at[i].append(RepeatBlock('plain', i, pass_start + length, length, k + 1))
                k += 1

        # b. 1st / 2nd ending voltas: |: shared (L-e) | [1. end1 (e) :| [2. end2 (e)
        for length in REPEAT_BODY_LENGTHS:
            if i + 2 * length > n:
                continue
            if not all(_is_plain_interior(b) for b in bars[i + 1:i + 2 * length]):
                continue
            for ending_len in VOLTA_ENDING_LENGTHS:
                shared = length - ending_len
                if shared < 3:
                    continue
                if not any(b.events for b in bars[i:i + shared]):
                    continue
                if not all(strict_sigs[i + length + d] == strict_sigs[i + d] for d in range(shared)):
                    continue
                if strict_sigs[i + shared] == strict_sigs[i + length + shared]:
                    continue
                cands_at[i].append(RepeatBlock('volta', i, i + 2 * length, length, 2, ending_len))

    dp: list[tuple[int, int]] = [(0, 0)] * (n + 1)
    choice: list[RepeatBlock | None] = [None] * n
    for i in range(n - 1, -1, -1):
        best = dp[i + 1]
        best_block: RepeatBlock | None = None
        for blk in cands_at[i]:
            nxt = dp[blk.end]
            score = (blk.saved_bars + nxt[0], -1 + nxt[1])
            if score > best or (score == best and best_block is None):
                best = score
                best_block = blk
        dp[i] = best
        choice[i] = best_block

    selected: list[RepeatBlock] = []
    i = 0
    while i < n:
        blk = choice[i]
        if blk is not None:
            selected.append(blk)
            i = blk.end
        else:
            i += 1
    return selected


def _build_marked_bars(bars: list[Bar], blocks: list[RepeatBlock]) -> list[_BarMark]:
    by_start = {blk.start: blk for blk in blocks}
    marked: list[_BarMark] = []
    i = 0
    n = len(bars)
    while i < n:
        blk = by_start.get(i)
        if blk is None:
            marked.append(_BarMark(bars[i]))
            i += 1
            continue
        if blk.kind == 'plain':
            for d in range(blk.body_len):
                marked.append(_BarMark(
                    bars[i + d],
                    repeat_start=(d == 0),
                    repeat_end=(blk.times if d == blk.body_len - 1 else None),
                ))
        else:
            shared = blk.body_len - blk.ending_len
            for d in range(shared):
                marked.append(_BarMark(bars[i + d], repeat_start=(d == 0)))
            for d in range(blk.ending_len):
                marked.append(_BarMark(
                    bars[i + shared + d],
                    volta_start=('1' if d == 0 else None),
                    volta_stop=('stop' if d == blk.ending_len - 1 else None),
                    repeat_end=(2 if d == blk.ending_len - 1 else None),
                ))
            second_end = i + blk.body_len + shared
            for d in range(blk.ending_len):
                marked.append(_BarMark(
                    bars[second_end + d],
                    volta_start=('2' if d == 0 else None),
                    volta_stop=('discontinue' if d == blk.ending_len - 1 else None),
                ))
        i = blk.end
    return marked


def _split_segments(marked: list[_BarMark]) -> list[list[_BarMark]]:
    segments: list[list[_BarMark]] = []
    cur: list[_BarMark] = []
    for item in marked:
        if cur and (item.repeat_start or item.volta_start is not None or item.bar.section is not None):
            segments.append(cur)
            cur = []
        cur.append(item)
        if item.repeat_end is not None or item.volta_stop is not None:
            segments.append(cur)
            cur = []
    if cur:
        segments.append(cur)
    return segments


def _plan_segment(bars: list[Bar], *, enable_similes: bool, repeat_counters: bool,
                  no_simile_bars: set[int] | frozenset[int]) -> list[MeasureUnit]:
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
        if not enable_similes:
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
                        units[u + offset] = replace(units[u + offset], counter=offset + 2)
                u = v
            else:
                u += 1

    return units


def plan_units(bars: list[Bar], *, repeats: str = 'simile', repeat_counters: bool = False,
               no_simile_bars: set[int] | frozenset[int] = frozenset()) -> list[MeasureUnit]:
    """Group bars into multi-bar rests, 1-bar/2-bar simile repeats, and (when ``repeats='full'``)
    folded ``|: ... :|`` repeat blocks and 1st/2nd ending voltas.

    ``no_simile_bars`` lists 0-based ``bar.index`` values that must be engraved in full (for
    example, the first bar on a new PDF page so the reader never sees ``%`` or ``//`` after a
    page turn).
    """
    if repeats not in REPEAT_MODES:
        raise ValueError(f'Unknown repeats mode {repeats!r}; expected one of {", ".join(REPEAT_MODES)}')
    if not bars:
        return []

    if repeats == 'full':
        marked = _build_marked_bars(bars, select_repeat_blocks(bars))
    else:
        marked = [_BarMark(b) for b in bars]

    units: list[MeasureUnit] = []
    enable_similes = repeats != 'off'
    for seg in _split_segments(marked):
        seg_units = _plan_segment([m.bar for m in seg], enable_similes=enable_similes,
                                  repeat_counters=repeat_counters, no_simile_bars=no_simile_bars)
        first_m, last_m = seg[0], seg[-1]
        if first_m.repeat_start or first_m.volta_start is not None:
            seg_units[0] = replace(seg_units[0],
                                   repeat_start=first_m.repeat_start,
                                   volta_start=first_m.volta_start)
        if last_m.repeat_end is not None or last_m.volta_stop is not None:
            seg_units[-1] = replace(seg_units[-1],
                                    repeat_end=last_m.repeat_end,
                                    volta_stop=last_m.volta_stop)
        units.extend(seg_units)

    engraved_bars = [b for u in units for b in u.bars]
    final: list[MeasureUnit] = []
    pos = 0
    printed = 0 if units[0].first.pickup else units[0].first.number
    for u_idx, unit in enumerate(units):
        prev = final[-1] if final else None
        dbl = (u_idx > 0
               and has_double_bar_before(engraved_bars, pos)
               and prev.repeat_end is None
               and not unit.repeat_start)
        final.append(replace(unit, double_bar_before=dbl, printed_start=printed))
        pos += len(unit.bars)
        printed += len(unit.bars)
    return final


def unroll_units(units: list[MeasureUnit]) -> list[Bar]:
    """Unroll folded repeats (``|: ... :|``) and 1st/2nd voltas back into linear playback order."""
    out: list[Bar] = []
    u = 0
    n = len(units)
    repeat_origin = 0
    pass_no = 1
    while u < n:
        unit = units[u]
        if unit.repeat_start:
            repeat_origin = u
        if unit.volta_start is not None:
            want_pass = int(unit.volta_start)
            if pass_no != want_pass:
                while u < n and units[u].volta_stop is None:
                    u += 1
                u += 1
                continue
        out.extend(unit.bars)
        if unit.repeat_end is not None and pass_no < unit.repeat_end:
            pass_no += 1
            u = repeat_origin
            continue
        if unit.repeat_end is not None or unit.volta_stop == 'discontinue':
            pass_no = 1
        u += 1
    return out


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
