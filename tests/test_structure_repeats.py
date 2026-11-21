"""Tests for notation repeat settings, score_structure planning, MusicXML, MusiXTeX, and PDF output."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import pytest
import yaml

from conftest import CRASH, HAVE_PDF_TOOLS, HH, HHO, KICK, RIDE, SNARE, TOM, build, make_midi
import build_score
import midi_to_musicxml
import midi_to_musixtex
import render_score
import validate_score
from score_core import Bar, Hit, R, ScoreError, load_instruments, parse_settings
from score_structure import MeasureUnit, bar_signature, measure_repeat_events, multi_rest_lengths, plan_units
from validate_score import ValidationError, validate_musicxml, validate_pdf

FOUR_FOUR = {'sigs': [(0, 4, 4)]}
XSD = os.environ.get('MUSICXML_XSD')
needs_xsd = pytest.mark.skipif(not (XSD and Path(XSD).exists()), reason='set MUSICXML_XSD to the MusicXML 4.0 XSD')
needs_pdf = pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs musixtex, etex, musixflx, dvipdfmx, xelatex, gs')


# --------------------------------------------------------------------------- pattern & inspection helpers

def _bar_a(offset: float) -> list[tuple]:
    """Standard 4/4 eighth-note rock groove."""
    return ([(offset + x / 2, HH) for x in range(8)]
            + [(offset, KICK), (offset + 2.5, KICK), (offset + 1, SNARE), (offset + 3, SNARE)])


def _bar_b(offset: float) -> list[tuple]:
    """Distinct 4/4 eighth-note groove (extra kick + tom fill on 4-and)."""
    return ([(offset + x / 2, HH) for x in range(7)]
            + [(offset, KICK), (offset + 2, KICK), (offset + 2.5, KICK),
               (offset + 1, SNARE), (offset + 3, SNARE), (offset + 3.5, TOM)])


def _bar_c(offset: float) -> list[tuple]:
    """Third distinct 4/4 groove on ride cymbal."""
    return ([(offset + x / 2, RIDE) for x in range(8)]
            + [(offset, KICK), (offset + 2, KICK), (offset + 1, SNARE), (offset + 3, SNARE)])


def _bar_d(offset: float) -> list[tuple]:
    """Fourth distinct 4/4 groove with crash on beat 1."""
    return ([(offset, CRASH)] + [(offset + x / 2, HH) for x in range(1, 8)]
            + [(offset, KICK), (offset + 1, SNARE), (offset + 2, KICK), (offset + 3, SNARE)])


def _bar_8th_variant(offset: float, variant: int) -> list[tuple]:
    """One of 16 distinct ordinary 8th-note 4/4 bars (8 slots each, no 16ths)."""
    cymbal = RIDE if (variant & 8) else HH
    hits: list[tuple] = [(offset + x / 2, cymbal) for x in range(8)]
    hits += [(offset, KICK), (offset + 1, SNARE), (offset + 3, SNARE)]
    if variant & 1:
        hits.append((offset + 2, KICK))
    if variant & 2:
        hits.append((offset + 2.5, KICK))
    if variant & 4:
        hits.append((offset + 3.5, TOM))
    return hits


def _sequence(bars_spec: list, *, start: float = 0, beats_per_bar: int = 4) -> list[tuple]:
    """Concatenate per-bar hit factories (or None for an empty bar)."""
    hits: list[tuple] = []
    for i, fn in enumerate(bars_spec):
        if fn is not None:
            hits.extend(fn(start + i * beats_per_bar))
    return hits


def _write_xml(score, tmp_path: Path, name: str = 'score.musicxml') -> tuple[Path, ET.Element]:
    path = tmp_path / name
    midi_to_musicxml.write(score, path)
    return path, ET.parse(path).getroot()


def _score_body(tex: str) -> str:
    after_start = tex.split(r'\startpiece', 1)[1]
    for marker in (r'\setdoubleBAR', r'\endpiece'):
        if marker in after_start:
            return after_start.split(marker, 1)[0]
    return after_start


def _systems_from_tex(tex: str) -> list[str]:
    return _score_body(tex).split(r'\alaligne')


def _bar_blocks(tex: str) -> list[tuple[str, list[str]]]:
    """Return ``(comment_line, body_lines)`` for each ``% bar ...`` unit, trimming trailing separators."""
    blocks: list[tuple[str, list[str]]] = []
    header: str | None = None
    buf: list[str] = []
    for line in _score_body(tex).splitlines():
        if line.startswith('% bar '):
            if header is not None:
                blocks.append((header, buf))
            header = line
            buf = []
        elif header is not None:
            buf.append(line)
    if header is not None:
        blocks.append((header, buf))

    cleaned: list[tuple[str, list[str]]] = []
    for hdr, lines in blocks:
        body = list(lines)
        while body and (not body[-1].strip()
                        or body[-1].strip() in (r'\bar', r'\alaligne', r'\changecontext')
                        or body[-1].strip().startswith(r'\generalmeter')):
            body.pop()
        cleaned.append((hdr, body))
    return cleaned


def _system_bar_labels(system_tex: str) -> list[str]:
    return re.findall(r'^% bar (\d+(?:-\d+)?)', system_tex, flags=re.M)


def _count_staves_per_page(pdf_path: Path) -> list[int]:
    """Count 5-line systems on each page of an outlined score PDF."""
    import pymupdf

    counts: list[int] = []
    with pymupdf.open(pdf_path) as doc:
        for page in doc:
            ys = sorted(
                (d['rect'].y0 + d['rect'].y1) / 2
                for d in page.get_drawings()
                if d['rect'].width > 400 and d['rect'].height < 1.5
            )
            staves = 0
            last_y: float | None = None
            for y in ys:
                if last_y is None or y - last_y > 10.0:
                    staves += 1
                last_y = y
            counts.append(staves)
    return counts


# --------------------------------------------------------------------------- 1. Settings & metadata parsing

def test_settings_notation_defaults():
    s = parse_settings({})
    assert s.repeats == 'simile'
    assert s.repeat_counters is False
    assert s.system_spacing == pytest.approx(1.1)


def test_settings_notation_system_spacing(tmp_path):
    for raw, expected in ((0.7, 0.7), (1.0, 1.0), (1.1, 1.1), (1.5, 1.5), (2.5, 2.5),
                          (2, 2.0), ('1.25', 1.25), ('6/5', 1.2)):
        assert parse_settings({'notation': {'system_spacing': raw}}).system_spacing == pytest.approx(expected)

    for bad in (True, False, None, 'wide', '広い', '', 0.5, 0.69, 2.51, 3.0, -1, [], {}):
        with pytest.raises(ScoreError) as exc_info:
            parse_settings({'notation': {'system_spacing': bad}})
        msg = str(exc_info.value)
        assert msg.isascii(), f'Error message must be ASCII only: {msg!r}'
        assert 'notation.system_spacing' in msg and '0.7' in msg and '2.5' in msg

    assert parse_settings({'notation': {'system_spacing': 0.9}}, cli={'system_spacing': '1.5'}).system_spacing == pytest.approx(1.5)
    assert parse_settings({'notation': {'system_spacing': 0.9}}, cli={'system_spacing': None}).system_spacing == pytest.approx(0.9)
    with pytest.raises(ScoreError):
        parse_settings({}, cli={'system_spacing': '3.0'})

    score = build(tmp_path, _sequence([_bar_a]), meta={'notation': {'system_spacing': 0.9}},
                  cli={'system_spacing': '1.4'}, **FOUR_FOUR)
    assert score.settings.system_spacing == pytest.approx(1.4)


def test_settings_notation_repeats_modes():
    assert parse_settings({'notation': {'repeats': 'off'}}).repeats == 'off'
    assert parse_settings({'notation': {'repeats': False}}).repeats == 'off'
    assert parse_settings({'notation': {'repeats': 'simile'}}).repeats == 'simile'

    # PyYAML (YAML 1.1) parses an unquoted `off` as boolean False.
    loaded = yaml.safe_load('notation:\n  repeats: off\n')
    assert loaded['notation']['repeats'] is False
    assert parse_settings(loaded).repeats == 'off'


def test_settings_notation_repeat_counters():
    assert parse_settings({'notation': {'repeat_counters': True}}).repeat_counters is True
    assert parse_settings({'notation': {'repeat_counters': False}}).repeat_counters is False


@pytest.mark.parametrize('meta', [
    {'notation': 'simile'},
    {'notation': ['off']},
    {'notation': False},
    {'notation': []},
    {'notation': ''},
    {'notation': {'repeats': 'always'}},
    {'notation': {'repeats': True}},
    {'notation': {'repeats': 2}},
    {'notation': {'repeat_counters': 'true'}},
    {'notation': {'repeat_counters': 'false'}},
    {'notation': {'repeat_counters': 1}},
    {'notation': {'repeat_counters': 0}},
    {'notation': {'repeat_counters': None}},
    {'notation': {'unknown_key': True}},
    {'notation': {'repeats': 'simile', 'extra': 'x'}},
])
def test_settings_notation_validation_errors(meta):
    with pytest.raises(ScoreError):
        parse_settings(meta)


def test_settings_cli_repeats_override(tmp_path):
    assert parse_settings({'notation': {'repeats': 'simile'}}, cli={'repeats': 'off'}).repeats == 'off'
    assert parse_settings({'notation': {'repeats': 'off'}}, cli={'repeats': 'simile'}).repeats == 'simile'
    assert parse_settings({'notation': {'repeats': 'off'}}, cli={'repeats': None}).repeats == 'off'

    score = build(tmp_path, _sequence([_bar_a, _bar_a]),
                  meta={'notation': {'repeats': 'simile'}}, cli={'repeats': 'off'}, **FOUR_FOUR)
    assert score.settings.repeats == 'off'


# --------------------------------------------------------------------------- 2. score_structure.plan_units() & events

def test_plan_units_repeats_off_keeps_multi_rests(tmp_path):
    score = build(tmp_path, _sequence([_bar_a, _bar_a, None, None, None, _bar_a, _bar_b, _bar_a, _bar_b]),
                  **FOUR_FOUR)
    units = plan_units(score.bars, repeats='off')
    assert [(u.kind, [b.index for b in u.bars], u.counter) for u in units] == [
        ('bar', [0], None),
        ('bar', [1], None),
        ('multi-rest', [2, 3, 4], None),
        ('bar', [5], None),
        ('bar', [6], None),
        ('bar', [7], None),
        ('bar', [8], None),
    ]
    with pytest.raises(ValueError, match='Unknown repeats mode'):
        plan_units(score.bars, repeats='bogus')


def test_structure_multi_rest_lengths(tmp_path):
    score = build(tmp_path, [(0, KICK), (8, KICK), (20, KICK), (36, KICK)],
                  sigs=[(0, 4, 4)], tempo=120, tempos=[(28, 100)])
    # Bar 0: hit, bar 1: single empty, bar 2: hit, bars 3-4: 2 empty, bar 5: hit,
    # bars 6-8: 3 empty split by tempo at beat 28 (bar 7) -> bar 6 empty (1), bars 7-8 empty (2).
    assert multi_rest_lengths(score.bars) == {3: 2, 7: 2}


def test_plan_units_simile_1_isolated_counted_and_suppressed(tmp_path):
    two = build(tmp_path, _sequence([_bar_a, _bar_a]), **FOUR_FOUR)
    u2 = plan_units(two.bars)
    assert [(u.kind, u.counter) for u in u2] == [('bar', None), ('simile-1', None)]
    assert u2[1].first is two.bars[1] and u2[1].last is two.bars[1]

    five = build(tmp_path, _sequence([_bar_a] * 5), **FOUR_FOUR)
    # Default repeat_counters is False: no counters on runs of >=2 %.
    u5_default = plan_units(five.bars)
    assert [(u.kind, u.counter) for u in u5_default] == [
        ('bar', None),
        ('simile-1', None),
        ('simile-1', None),
        ('simile-1', None),
        ('simile-1', None),
    ]

    u5 = plan_units(five.bars, repeat_counters=True)
    assert [(u.kind, u.counter) for u in u5] == [
        ('bar', None),
        ('simile-1', 2),
        ('simile-1', 3),
        ('simile-1', 4),
        ('simile-1', 5),
    ]

    u5_no_cnt = plan_units(five.bars, repeat_counters=False)
    assert [(u.kind, u.counter) for u in u5_no_cnt] == [
        ('bar', None),
        ('simile-1', None),
        ('simile-1', None),
        ('simile-1', None),
        ('simile-1', None),
    ]


def test_plan_units_simile_breaks_on_empty_and_pickup(tmp_path):
    # Empty bar breaks 1-bar repeat.
    single_gap = build(tmp_path, _sequence([_bar_a, None, _bar_a]), **FOUR_FOUR)
    assert [u.kind for u in plan_units(single_gap.bars)] == ['bar', 'bar', 'bar']

    multi_gap = build(tmp_path, _sequence([_bar_a, None, None, _bar_a]), **FOUR_FOUR)
    assert [u.kind for u in plan_units(multi_gap.bars)] == ['bar', 'multi-rest', 'bar']

    # Pickup bar with MIDI: pickup never templates or becomes a simile.
    hits = [(0, SNARE), (1, SNARE)] + _sequence([_bar_a, _bar_a], start=2)
    pickup_score = build(tmp_path, hits, meta={'pickup_beats': 2, 'source_leading_beats': 2},
                         sigs=[(0, 2, 4), (2, 4, 4)])
    assert [(u.kind, u.first.number) for u in plan_units(pickup_score.bars)] == [
        ('bar', 0), ('bar', 1), ('simile-1', 2),
    ]

    # Direct Bar check: even if pickup bar has identical events and next bar has show_meter=False,
    # pickup cannot template a simile and a pickup bar cannot become a simile.
    snare = load_instruments()['snare']
    ev = {0: {SNARE: Hit(SNARE, snare, 100)}}
    b0 = Bar(0, 0, 2, 4, 0, pickup=True, events=ev)
    b1 = Bar(1, 1, 2, 4, 2 * R, pickup=False, events=ev, show_meter=False)
    b2 = Bar(2, 2, 2, 4, 4 * R, pickup=True, events=ev, show_meter=False)
    assert [u.kind for u in plan_units([b0, b1, b2])] == ['bar', 'bar', 'bar']


def test_plan_units_simile_breaks_on_meter_and_tempo(tmp_path):
    # Meter change (4/4 -> 3/4) breaks simile.
    hits_meter = [(0, KICK), (1, SNARE), (2, KICK), (4, KICK), (5, SNARE), (6, KICK)]
    s_meter = build(tmp_path, hits_meter, sigs=[(0, 4, 4), (4, 3, 4)])
    assert [u.kind for u in plan_units(s_meter.bars)] == ['bar', 'bar']

    # Even with identical bar length and events, show_meter=True breaks simile.
    snare = load_instruments()['snare']
    ev = {0: {SNARE: Hit(SNARE, snare, 100)}}
    b0 = Bar(0, 1, 4, 4, 0, events=ev, show_meter=True)
    b1 = Bar(1, 2, 4, 4, 4 * R, events=ev, show_meter=True)
    assert [u.kind for u in plan_units([b0, b1])] == ['bar', 'bar']

    # Tempo change on bar 1 breaks simile; bar 2 (no tempo change) matches bar 1.
    s_tempo = build(tmp_path, _sequence([_bar_a, _bar_a, _bar_a]),
                    sigs=[(0, 4, 4)], tempo=120, tempos=[(4, 150)])
    assert [u.kind for u in plan_units(s_tempo.bars)] == ['bar', 'bar', 'simile-1']


def test_plan_units_simile_breaks_on_articulation_grace_mark_and_tuplet(tmp_path):
    dyn = {'dynamics': {'ghost_below': 40, 'accent_above': 110}}

    # Distinct accent
    s_acc = build(tmp_path, [(0, KICK), (1, SNARE, 90), (4, KICK), (5, SNARE, 120)], meta=dyn, **FOUR_FOUR)
    assert [u.kind for u in plan_units(s_acc.bars)] == ['bar', 'bar']

    # Distinct ghost note
    s_ghost = build(tmp_path, [(0, KICK), (1, SNARE, 90), (4, KICK), (5, SNARE, 25)], meta=dyn, **FOUR_FOUR)
    assert [u.kind for u in plan_units(s_ghost.bars)] == ['bar', 'bar']

    # Distinct grace note (flam before beat 2 snare in bar 1)
    s_grace = build(tmp_path, [(0, KICK), (1, SNARE, 100),
                               (4, KICK), (5 - 40 / 480, SNARE, 35), (5, SNARE, 100)], **FOUR_FOUR)
    assert s_grace.grace_hits == 1
    assert [u.kind for u in plan_units(s_grace.bars)] == ['bar', 'bar']

    # Distinct open/closed mark (HH 42 vs HHO 46 share staff 'n' and head 'x', differ only in mark)
    s_mark = build(tmp_path, [(0, KICK), (1, HH), (4, KICK), (5, HHO)], **FOUR_FOUR)
    assert [u.kind for u in plan_units(s_mark.bars)] == ['bar', 'bar']

    # Distinct tuplet grid on same beat
    s_tup = build(tmp_path, [(0, SNARE), (1, KICK), (4, SNARE), (4 + 1 / 3, SNARE), (4 + 2 / 3, SNARE), (5, KICK)],
                  **FOUR_FOUR)
    assert [u.kind for u in plan_units(s_tup.bars)] == ['bar', 'bar']


def test_plan_units_no_simile_bars_resets_pattern_and_counter(tmp_path):
    five = build(tmp_path, _sequence([_bar_a] * 5), **FOUR_FOUR)
    assert [(u.kind, u.first.index, u.counter) for u in plan_units(five.bars, no_simile_bars={2})] == [
        ('bar', 0, None),
        ('simile-1', 1, None),
        ('bar', 2, None),
        ('simile-1', 3, None),
        ('simile-1', 4, None),
    ]
    units5 = plan_units(five.bars, repeat_counters=True, no_simile_bars={2})
    assert [(u.kind, u.first.index, u.counter) for u in units5] == [
        ('bar', 0, None),
        ('simile-1', 1, None),   # isolated after split -> unnumbered
        ('bar', 2, None),        # forced full engraving
        ('simile-1', 3, 2),      # counter restarts at 2
        ('simile-1', 4, 3),
    ]

    six = build(tmp_path, _sequence([_bar_a] * 6), **FOUR_FOUR)
    units6 = plan_units(six.bars, repeat_counters=True, no_simile_bars={3})
    assert [(u.kind, u.first.index, u.counter) for u in units6] == [
        ('bar', 0, None),
        ('simile-1', 1, 2),
        ('simile-1', 2, 3),
        ('bar', 3, None),
        ('simile-1', 4, 2),
        ('simile-1', 5, 3),
    ]


def test_structure_visual_equivalence_snare_38_and_40(tmp_path):
    # GM 38 (Acoustic Snare) and GM 40 (Electric Snare) both engrave as the same snare.
    hits = [(0, KICK), (1, 38), (2, HH), (4, KICK), (5, 40), (6, HH)]
    s_eq = build(tmp_path, hits, **FOUR_FOUR)
    assert bar_signature(s_eq.bars[0]) == bar_signature(s_eq.bars[1])
    assert [u.kind for u in plan_units(s_eq.bars)] == ['bar', 'simile-1']

    # GM 38 (normal head) vs GM 37 (side-stick, x head on same staff 'j') must NOT match.
    s_diff = build(tmp_path, [(0, KICK), (1, 38), (4, KICK), (5, 37)], **FOUR_FOUR)
    assert bar_signature(s_diff.bars[0]) != bar_signature(s_diff.bars[1])
    assert [u.kind for u in plan_units(s_diff.bars)] == ['bar', 'bar']

    # Simultaneous hits sharing (staff, head) with mixed mark (None vs 'open') must sort cleanly.
    s_mixed = build(tmp_path, [(0, HH), (0, HHO), (4, HH), (4, HHO)], **FOUR_FOUR)
    assert bar_signature(s_mixed.bars[0]) == bar_signature(s_mixed.bars[1])
    assert [u.kind for u in plan_units(s_mixed.bars)] == ['bar', 'simile-1']


def test_plan_units_simile_2_detection_and_constraints(tmp_path):
    # A | B | A | B | A | B -> two simile-2 units, both counter=None.
    s_ab = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b, _bar_a, _bar_b]), **FOUR_FOUR)
    u_ab = plan_units(s_ab.bars, repeat_counters=True)
    assert [(u.kind, [b.index for b in u.bars], u.counter) for u in u_ab] == [
        ('bar', [0], None),
        ('bar', [1], None),
        ('simile-2', [2, 3], None),
        ('simile-2', [4, 5], None),
    ]

    # Non-zero-based slice still plans simile-2 using bar object identity.
    slice_units = plan_units(s_ab.bars[2:])
    assert [(u.kind, [b.index for b in u.bars]) for u in slice_units] == [
        ('bar', [2]), ('bar', [3]), ('simile-2', [4, 5]),
    ]

    # A | A | A | A must use 1-bar similes, never 2-bar simile.
    s_aaaa = build(tmp_path, _sequence([_bar_a] * 4), **FOUR_FOUR)
    u_aaaa_default = plan_units(s_aaaa.bars)
    assert all(u.kind != 'simile-2' for u in u_aaaa_default)
    assert [(u.kind, u.counter) for u in u_aaaa_default] == [
        ('bar', None), ('simile-1', None), ('simile-1', None), ('simile-1', None),
    ]
    u_aaaa = plan_units(s_aaaa.bars, repeat_counters=True)
    assert all(u.kind != 'simile-2' for u in u_aaaa)
    assert [(u.kind, u.counter) for u in u_aaaa] == [
        ('bar', None), ('simile-1', 2), ('simile-1', 3), ('simile-1', 4),
    ]

    # A | A | B | A | B -> simile-2 must NOT reference a % bar (bars 1-2 are % | B).
    s_aabab = build(tmp_path, _sequence([_bar_a, _bar_a, _bar_b, _bar_a, _bar_b]), **FOUR_FOUR)
    assert [u.kind for u in plan_units(s_aabab.bars)] == ['bar', 'simile-1', 'bar', 'bar', 'bar']

    # Continuing with A | B after A | % | B | A: plain bars (2=B, 3=A) template simile-2(4=B, 5=A).
    s_aababab = build(tmp_path, _sequence([_bar_a, _bar_a, _bar_b, _bar_a, _bar_b, _bar_a, _bar_b]), **FOUR_FOUR)
    assert [(u.kind, [b.index for b in u.bars]) for u in plan_units(s_aababab.bars)] == [
        ('bar', [0]), ('simile-1', [1]), ('bar', [2]), ('bar', [3]), ('simile-2', [4, 5]), ('bar', [6]),
    ]


def test_plan_units_simile_2_broken_by_meter_tempo_no_simile(tmp_path):
    base = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b]), **FOUR_FOUR)
    assert [u.kind for u in plan_units(base.bars)] == ['bar', 'bar', 'simile-2']

    # no_simile_bars on either bar of the pair prevents simile-2.
    assert [u.kind for u in plan_units(base.bars, no_simile_bars={2})] == ['bar', 'bar', 'bar', 'bar']
    assert [u.kind for u in plan_units(base.bars, no_simile_bars={3})] == ['bar', 'bar', 'bar', 'bar']

    # Page-turn reset on bar 2 of A|B|A|B|A|B keeps page 2 self-contained (A|B|//, never phase-shifted B|A).
    six_ab = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b, _bar_a, _bar_b]), **FOUR_FOUR)
    assert [(u.kind, [b.index for b in u.bars]) for u in plan_units(six_ab.bars, no_simile_bars={2})] == [
        ('bar', [0]), ('bar', [1]), ('bar', [2]), ('bar', [3]), ('simile-2', [4, 5]),
    ]

    # Tempo change on either bar of the repeated pair OR mid-template (bar 1) breaks simile-2.
    t_first = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b]),
                    sigs=[(0, 4, 4)], tempo=120, tempos=[(8, 140)])
    assert [u.kind for u in plan_units(t_first.bars)] == ['bar', 'bar', 'bar', 'bar']

    t_second = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b]),
                     sigs=[(0, 4, 4)], tempo=120, tempos=[(12, 140)])
    assert [u.kind for u in plan_units(t_second.bars)] == ['bar', 'bar', 'bar', 'bar']

    t_mid_template = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b]),
                           sigs=[(0, 4, 4)], tempo=120, tempos=[(4, 150)])
    assert [u.kind for u in plan_units(t_mid_template.bars)] == ['bar', 'bar', 'bar', 'bar']

    # Meter change on either bar of the pair breaks simile-2.
    m_alt = build(tmp_path,
                  [(0, KICK), (1, SNARE), (4, KICK), (5, TOM), (7, KICK), (8, SNARE), (11, KICK), (12, TOM)],
                  sigs=[(0, 4, 4), (4, 3, 4), (7, 4, 4), (11, 3, 4)])
    assert [u.kind for u in plan_units(m_alt.bars)] == ['bar', 'bar', 'bar', 'bar']

    # Explicit show_meter on bar 1 (mid-template), bar 2, or bar 3 breaks simile-2.
    inst = load_instruments()
    ev_a = {0: {KICK: Hit(KICK, inst['kick'], 100)}}
    ev_b = {0: {SNARE: Hit(SNARE, inst['snare'], 100)}}
    for bad_idx in (1, 2, 3):
        bars = [
            Bar(0, 1, 4, 4, 0, events=ev_a, show_meter=True),
            Bar(1, 2, 4, 4, 4 * R, events=ev_b, show_meter=(bad_idx == 1)),
            Bar(2, 3, 4, 4, 8 * R, events=ev_a, show_meter=(bad_idx == 2)),
            Bar(3, 4, 4, 4, 12 * R, events=ev_b, show_meter=(bad_idx == 3)),
        ]
        assert [u.kind for u in plan_units(bars)] == ['bar', 'bar', 'bar', 'bar']


def test_events_measure_repeat_transitions(tmp_path):
    # Direct unit-level transitions: bar -> % -> // -> multi-rest -> bar -> % (end of piece).
    fake = [Bar(i, i + 1, 4, 4, i * 4 * R) for i in range(8)]
    synthetic_units = [
        MeasureUnit('bar', (fake[0],)),
        MeasureUnit('simile-1', (fake[1],)),
        MeasureUnit('simile-2', (fake[2], fake[3])),
        MeasureUnit('multi-rest', (fake[4], fake[5])),
        MeasureUnit('bar', (fake[6],)),
        MeasureUnit('simile-1', (fake[7],)),
    ]
    assert measure_repeat_events(synthetic_units) == {
        1: [('start', 1)],
        2: [('stop', None), ('start', 2)],
        4: [('stop', None)],
        7: [('start', 1)],
    }

    # MIDI-derived sequence covering %, stop, //, stop on multi-rest, and trailing % to end-of-piece.
    seq = [_bar_a, _bar_a, _bar_a, _bar_b, _bar_c, _bar_b, _bar_c, None, None, _bar_d, _bar_d]
    score = build(tmp_path, _sequence(seq), **FOUR_FOUR)
    units = plan_units(score.bars)
    assert measure_repeat_events(units) == {
        1: [('start', 1)],
        3: [('stop', None)],
        5: [('start', 2)],
        7: [('stop', None)],
        10: [('start', 1)],
    }

    # Consecutive simile-2 to end-of-piece: single start, no intermediate stop, no trailing stop.
    ab = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b, _bar_a, _bar_b]), **FOUR_FOUR)
    assert measure_repeat_events(plan_units(ab.bars)) == {2: [('start', 2)]}

    # Repeats off emits no repeat events.
    assert measure_repeat_events(plan_units(score.bars, repeats='off')) == {}


def test_structure_real_song_inochi_simile_counts(song):
    units = plan_units(song.bars, repeats=song.settings.repeats, repeat_counters=song.settings.repeat_counters)
    counts = Counter(u.kind for u in units)
    assert counts['simile-1'] == 32
    assert counts['simile-2'] == 4
    assert [b.index for u in units for b in u.bars] == list(range(len(song.bars)))


# --------------------------------------------------------------------------- 3. MusicXML + validator integration

def _repeat_tags(measure: ET.Element) -> list[tuple[str | None, str | None, str | None]]:
    return [
        (mr.get('type'), mr.get('slashes'), mr.text)
        for mr in measure.findall('attributes/measure-style/measure-repeat')
    ]


def test_musicxml_measure_repeats_and_full_notes_preserved(tmp_path):
    seq = [_bar_a, _bar_a, _bar_a, _bar_b, _bar_c, _bar_b, _bar_c, None, None, _bar_d, _bar_d]
    score = build(tmp_path, _sequence(seq), **FOUR_FOUR)
    path, root = _write_xml(score, tmp_path)
    measures = root.findall('part/measure')
    assert len(measures) == len(seq)

    # Check exact start/stop measure-repeat elements on expected bars.
    assert _repeat_tags(measures[0]) == []
    assert _repeat_tags(measures[1]) == [('start', '1', '1')]
    assert _repeat_tags(measures[2]) == []
    assert _repeat_tags(measures[3]) == [('stop', None, None)]
    assert _repeat_tags(measures[4]) == []
    assert _repeat_tags(measures[5]) == [('start', '2', '2')]
    assert _repeat_tags(measures[6]) == []
    assert _repeat_tags(measures[7]) == [('stop', None, None)]
    assert measures[7].findtext('attributes/measure-style/multiple-rest') == '2'
    assert _repeat_tags(measures[8]) == []
    assert _repeat_tags(measures[9]) == []
    assert _repeat_tags(measures[10]) == [('start', '1', '1')]

    # Measure-style children must appear after divisions/key/time/clef/staff-details,
    # and on bar 7 the repeat stop precedes the multiple-rest element.
    styles7 = measures[7].findall('attributes/measure-style')
    assert [s[0].tag for s in styles7] == ['measure-repeat', 'multiple-rest']

    # Every repeated measure still encodes all real notes (lossless playback & validation).
    xml_notes = [n for n in root.iter('note') if n.find('rest') is None and n.find('grace') is None]
    assert len(xml_notes) == score.engraved_hits
    assert len([n for n in measures[1].findall('note') if n.find('rest') is None]) == len(
        [n for n in measures[0].findall('note') if n.find('rest') is None]
    )

    assert validate_musicxml(score, path).startswith('MusicXML OK')


def test_musicxml_repeats_off_omits_repeat_tags_and_validates(tmp_path):
    seq = [_bar_a, _bar_a, _bar_b, _bar_a, _bar_b, None, None, _bar_c]
    score = build(tmp_path, _sequence(seq), meta={'notation': {'repeats': 'off'}}, **FOUR_FOUR)
    path, root = _write_xml(score, tmp_path)
    assert root.findall('.//measure-repeat') == []
    assert root.findtext('.//multiple-rest') == '2'
    assert validate_musicxml(score, path).startswith('MusicXML OK')


@pytest.mark.parametrize('tamper', ['slashes', 'type', 'text', 'remove'])
def test_musicxml_validator_catches_measure_repeat_tampering(tmp_path, tamper):
    score = build(tmp_path, _sequence([_bar_a, _bar_a, _bar_b]), **FOUR_FOUR)
    path, root = _write_xml(score, tmp_path)
    assert validate_musicxml(score, path).startswith('MusicXML OK')

    measure1 = root.findall('part/measure')[1]
    style = measure1.find('attributes/measure-style')
    mr = style.find('measure-repeat')
    assert mr is not None
    if tamper == 'slashes':
        mr.set('slashes', '2')
    elif tamper == 'type':
        mr.set('type', 'stop')
    elif tamper == 'text':
        mr.text = '2'
    elif tamper == 'remove':
        measure1.find('attributes').remove(style)
    ET.ElementTree(root).write(path)

    with pytest.raises(ValidationError):
        validate_musicxml(score, path)


def test_musicxml_cli_repeats_flag(tmp_path):
    midi = make_midi(tmp_path / 'rep.mid', _sequence([_bar_a, _bar_a, _bar_b]), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: Repeat CLI\n', encoding='utf-8')

    xml_off = tmp_path / 'off.musicxml'
    assert midi_to_musicxml.main([str(midi), '--metadata', str(meta), '--out', str(xml_off), '--repeats', 'off']) == 0
    assert ET.parse(xml_off).getroot().findall('.//measure-repeat') == []
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml_off), '--repeats', 'off']) == 0
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml_off), '--repeats', 'simile']) == 1

    out_dir = tmp_path / 'build-off'
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out_dir),
                             '--no-pdf', '--repeats', 'off']) == 0
    assert ET.parse(out_dir / 'score.musicxml').getroot().findall('.//measure-repeat') == []


@needs_xsd
def test_musicxml_xsd_valid_with_similes_and_multirest(tmp_path):
    hits = [(0, SNARE)] + _sequence(
        [_bar_a, _bar_a, _bar_a, _bar_b, _bar_c, _bar_b, _bar_c, None, None, _bar_d, _bar_d],
        start=1,
    )
    score = build(tmp_path, hits, meta={'pickup_beats': 1, 'source_leading_beats': 1},
                  sigs=[(0, 1, 4), (1, 4, 4)], tempo=128)
    path, _root = _write_xml(score, tmp_path)
    validate_musicxml(score, path, Path(XSD))


# --------------------------------------------------------------------------- 4. MusiXTeX + PDF integration

def _has_counter_token(lines: list[str], number: int) -> bool:
    """Match a printed repeat counter digit inside TeX braces or command argument (ignores \\vnotes and \\barnum)."""
    non_spacing = [l for l in lines if not l.lstrip().startswith((r'\vnotes', r'\znotes\barnum'))]
    pat = re.compile(rf'(?:\{{|\s){number}(?:\}}|\\)')
    return any(pat.search(l) for l in non_spacing)


def test_musixtex_simile_1_duevolte_counters_and_no_simile_bars(tmp_path):
    # Isolated %: emits \duevolte, no counter.
    s_iso = build(tmp_path, _sequence([_bar_a, _bar_a]), **FOUR_FOUR)
    tex_iso = midi_to_musixtex.convert(s_iso)
    tex_iso.encode('ascii')
    blocks_iso = _bar_blocks(tex_iso)
    assert len(blocks_iso) == 2
    assert 'simile' not in blocks_iso[0][0]
    assert 'simile' in blocks_iso[1][0]
    assert any(r'\duevolte' in l for l in blocks_iso[1][1])
    assert not _has_counter_token(blocks_iso[1][1], 2)

    # >=2 consecutive %: counters omitted by default (and when repeat_counters=False), emitted when True.
    s_default = build(tmp_path, _sequence([_bar_a] * 4), **FOUR_FOUR)
    s_cnt = build(tmp_path, _sequence([_bar_a] * 4), meta={'notation': {'repeat_counters': True}}, **FOUR_FOUR)
    s_nocnt = build(tmp_path, _sequence([_bar_a] * 4), meta={'notation': {'repeat_counters': False}}, **FOUR_FOUR)
    tex_def = midi_to_musixtex.convert(s_default)
    tex_cnt = midi_to_musixtex.convert(s_cnt)
    tex_nocnt = midi_to_musixtex.convert(s_nocnt)
    tex_def.encode('ascii')
    tex_cnt.encode('ascii')
    tex_nocnt.encode('ascii')
    assert tex_def == tex_nocnt
    assert r'\csimile' not in _score_body(tex_def)

    assert r'\duevolte' in tex_cnt
    b_cnt = _bar_blocks(tex_cnt)
    b_nocnt = _bar_blocks(tex_nocnt)
    assert len(b_cnt) == len(b_nocnt) == 4
    for idx, num in ((1, 2), (2, 3), (3, 4)):
        assert 'simile' in b_cnt[idx][0]
        assert _has_counter_token(b_cnt[idx][1], num)
        assert 'simile' in b_nocnt[idx][0]
        assert any(r'\duevolte' in l for l in b_nocnt[idx][1])
        assert not _has_counter_token(b_nocnt[idx][1], num)
    body_only = lambda lines: [l for l in lines if r'\barnum' not in l]
    assert body_only(b_nocnt[1][1]) == body_only(b_nocnt[2][1]) == body_only(b_nocnt[3][1])
    assert body_only(b_cnt[1][1]) != body_only(b_cnt[2][1]) != body_only(b_cnt[3][1])

    # repeats='off' emits no similes in the score body.
    s_off = build(tmp_path, _sequence([_bar_a] * 4), meta={'notation': {'repeats': 'off'}}, **FOUR_FOUR)
    body_off = _score_body(midi_to_musixtex.convert(s_off))
    assert r'\duevolte' not in body_off and 'simile' not in body_off

    # no_simile_bars forces full engraving and restarts counters when repeat_counters=True (and keeps counters off by default).
    s_five_def = build(tmp_path, _sequence([_bar_a] * 5), **FOUR_FOUR)
    assert r'\csimile' not in _score_body(midi_to_musixtex.convert(s_five_def, no_simile_bars={2}))
    s_five = build(tmp_path, _sequence([_bar_a] * 5), meta={'notation': {'repeat_counters': True}}, **FOUR_FOUR)
    tex_reset = midi_to_musixtex.convert(s_five, no_simile_bars={2})
    b_reset = _bar_blocks(tex_reset)
    assert len(b_reset) == 5
    assert 'simile' in b_reset[1][0] and not _has_counter_token(b_reset[1][1], 2)
    assert 'simile' not in b_reset[2][0] and not any(r'\duevolte' in l for l in b_reset[2][1])
    assert 'simile' in b_reset[3][0] and _has_counter_token(b_reset[3][1], 2)
    assert 'simile' in b_reset[4][0] and _has_counter_token(b_reset[4][1], 3)


def test_musixtex_simile_2_never_split_by_alaligne(tmp_path, song):
    # Bars 4-5 (1-based) form a simile-2 straddling the natural 4-bar boundary.
    seq = [_bar_c, _bar_a, _bar_b, _bar_a, _bar_b, _bar_d, _bar_a, _bar_b, _bar_a, _bar_b]
    score = build(tmp_path, _sequence(seq), **FOUR_FOUR)
    for lw in (None, 55.0):
        tex = midi_to_musixtex.convert(score) if lw is None else midi_to_musixtex.convert(score, line_width=lw)
        tex.encode('ascii')
        blocks = _bar_blocks(tex)
        s2_blocks = [(hdr, lines) for hdr, lines in blocks if 'simile-2' in hdr]
        assert len(s2_blocks) == 2
        for hdr, lines in s2_blocks:
            joined = '\n'.join(lines)
            assert r'\alaligne' not in joined, f'simile-2 split across lines: {hdr}'
            assert r'\bar' in joined, f'simile-2 missing middle \\bar: {hdr}'

    # Real song also keeps all 4 simile-2 units atomic.
    song_tex = midi_to_musixtex.convert(song)
    song_tex.encode('ascii')
    song_s2 = [(hdr, lines) for hdr, lines in _bar_blocks(song_tex) if 'simile-2' in hdr]
    assert len(song_s2) == 4
    for hdr, lines in song_s2:
        assert r'\alaligne' not in '\n'.join(lines), f'song simile-2 split: {hdr}'


def test_musixtex_pickup_and_phrase_aligned_lines(tmp_path, song):
    # Pickup bar 0 + 8-bar phrase: line 1 keeps pickup 0 with bars 1..4; line 2 has 5..8.
    hits = [(0, SNARE)] + _sequence([_bar_a, _bar_a, _bar_a, _bar_b, _bar_a, _bar_a, _bar_a, _bar_b], start=1)
    s_pickup = build(tmp_path, hits, meta={'pickup_beats': 1, 'source_leading_beats': 1},
                     sigs=[(0, 1, 4), (1, 4, 4)])
    sys_pickup = [_system_bar_labels(s) for s in _systems_from_tex(midi_to_musixtex.convert(s_pickup))]
    assert sys_pickup[0] == ['0', '1', '2', '3', '4']
    assert sys_pickup[1] == ['5', '6', '7', '8']

    # 12 distinct full 8th-note groove bars pack cleanly 4 bars per line.
    twelve = [_bar_8th_variant(4 * i, i) for i in range(12)]
    s_8th = build(tmp_path, [h for bar in twelve for h in bar], **FOUR_FOUR)
    sys_8th = [_system_bar_labels(s) for s in _systems_from_tex(midi_to_musixtex.convert(s_8th))]
    assert sys_8th == [['1', '2', '3', '4'], ['5', '6', '7', '8'], ['9', '10', '11', '12']]

    # Real song line 1 also keeps pickup bar 0 with bars 1..4.
    song_sys0 = _system_bar_labels(_systems_from_tex(midi_to_musixtex.convert(song))[0])
    assert song_sys0 == ['0', '1', '2', '3', '4']


def test_musixtex_cli_repeats_flag(tmp_path):
    midi = make_midi(tmp_path / 'rep.mid', _sequence([_bar_a, _bar_a, _bar_a]), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: TeX CLI\n', encoding='utf-8')
    out_off = tmp_path / 'off.tex'
    out_sim = tmp_path / 'sim.tex'
    assert midi_to_musixtex.main([str(midi), '--metadata', str(meta), '--out', str(out_off), '--repeats', 'off']) == 0
    assert midi_to_musixtex.main([str(midi), '--metadata', str(meta), '--out', str(out_sim), '--repeats', 'simile']) == 0
    assert 'simile' not in _score_body(out_off.read_text(encoding='ascii'))
    assert 'simile' in _score_body(out_sim.read_text(encoding='ascii'))


@needs_pdf
def test_pdf_multipage_repeating_groove_never_starts_page_with_simile(tmp_path):
    # 72 identical 4/4 bars guarantee >=2 pages where every bar after bar 1 would otherwise be %.
    score = build(tmp_path, _sequence([_bar_a] * 72),
                  meta={'title': 'Repeat Page Break Test', 'legend': True}, **FOUR_FOUR)
    out = tmp_path / 'score.pdf'
    work = tmp_path / 'work'
    work.mkdir()
    info = render_score.render(score, out, work)
    assert info['pages'] >= 2
    assert validate_pdf(score, out).startswith('PDF OK')

    tex = (work / 'score.tex').read_text(encoding='ascii')
    systems = _systems_from_tex(tex)
    staves_per_page = _count_staves_per_page(work / 'notes.pdf')
    assert len(staves_per_page) == info['pages']
    assert sum(staves_per_page) == len(systems)

    unconstrained = {u.first.index: u.kind for u in plan_units(score.bars)}
    sys_offset = 0
    for page_idx, n_staves in enumerate(staves_per_page):
        if page_idx >= 1:
            first_sys = systems[sys_offset]
            first_blocks = _bar_blocks(r'\startpiece' + '\n' + first_sys + '\n' + r'\endpiece')
            assert first_blocks, f'page {page_idx + 1} first system has no bar blocks'
            hdr, body = first_blocks[0]
            assert 'simile' not in hdr, f'page {page_idx + 1} started with simile: {hdr}'
            joined = '\n'.join(body)
            assert r'\duevolte' not in joined and r'\csimile' not in joined
            assert any(tok in joined for tok in (r'\@qb', r'\@xqb', r'\@qu', r'\@ql'))

            # Confirm the page-break reset actually acted on a bar that was otherwise a simile.
            m = re.match(r'^% bar (\d+)\b', hdr)
            assert m is not None
            bar_idx = int(m.group(1)) - 1  # no pickup -> 1-based number maps to 0-based index
            assert unconstrained[bar_idx] == 'simile-1'
        sys_offset += n_staves


@needs_pdf
def test_pdf_cli_repeats_off(tmp_path):
    midi = make_midi(tmp_path / 'short.mid', _sequence([_bar_a] * 4), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: PDF CLI Off\n', encoding='utf-8')
    out = tmp_path / 'score.pdf'
    work = tmp_path / 'work'
    assert render_score.main([str(midi), '--metadata', str(meta), '--out', str(out),
                              '--work-dir', str(work), '--repeats', 'off']) == 0
    assert 'simile' not in _score_body((work / 'score.tex').read_text(encoding='ascii'))
    score_off = build_score.build_score(midi, meta, cli={'repeats': 'off'})
    assert validate_pdf(score_off, out).startswith('PDF OK')
