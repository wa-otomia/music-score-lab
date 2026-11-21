"""Tests for Phase 3 features: notation.repeats='full' (|: ... :| and 1./2. volta endings)."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from conftest import CRASH, HAVE_PDF_TOOLS, HH, HHO, KICK, RIDE, SNARE, SONG_META, SONG_MIDI, TOM, build, make_midi
import build_score
import midi_to_musicxml
import midi_to_musixtex
import render_score
import score_core
import validate_score
from score_core import ScoreError, parse_settings
from score_structure import (
    RepeatBlock,
    bar_signature,
    plan_units,
    select_repeat_blocks,
    strict_bar_signature,
    unroll_units,
)
from validate_score import ValidationError, validate_musicxml, validate_pdf

FOUR_FOUR = {'sigs': [(0, 4, 4)]}
XSD = os.environ.get('MUSICXML_XSD')
needs_xsd = pytest.mark.skipif(not (XSD and Path(XSD).exists()), reason='set MUSICXML_XSD to the MusicXML 4.0 XSD')
needs_pdf = pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs musixtex, etex, musixflx, dvipdfmx, xelatex, gs')

INOCHI_SECTIONS = {
    1: 'Intro', 9: 'A', 25: 'B', 49: 'Chorus', 65: 'A2',
    105: 'Bridge', 121: 'Chorus2', 161: 'Interlude', 169: 'Final',
}


# --------------------------------------------------------------------------- pattern & inspection helpers

def _bar_v(variant: int, *, snare: int = SNARE):
    """Return a factory producing one of 64 distinct 4/4 eighth-note bars."""
    def make(offset: float) -> list[tuple]:
        cymbal = RIDE if (variant & 16) else HH
        hits: list[tuple] = [(offset + x / 2, cymbal) for x in range(8)]
        if variant & 32:
            hits[0] = (offset, CRASH)
        hits += [(offset, KICK), (offset + 1, snare), (offset + 3, snare)]
        if variant & 1:
            hits.append((offset + 0.5, KICK))
        if variant & 2:
            hits.append((offset + 1.5, KICK))
        if variant & 4:
            hits.append((offset + 2, KICK))
        if variant & 8:
            hits.append((offset + 3.5, TOM))
        return hits
    return make


def _phrase(length: int, start_variant: int = 0, *, snare: int = SNARE) -> list:
    return [_bar_v(start_variant + i, snare=snare) for i in range(length)]


def _sequence(bars_spec: list, *, start: float = 0, beats_per_bar: int = 4) -> list[tuple]:
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
    for marker in (r'\setdoubleBAR', r'\setrightrepeat\endpiece', r'\endpiece'):
        if marker in after_start:
            return after_start.split(marker, 1)[0]
    return after_start


def _systems_from_tex(tex: str) -> list[str]:
    return _score_body(tex).split(r'\alaligne')


def _bar_blocks(tex: str) -> list[tuple[str, list[str]]]:
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

    seps = {
        r'\bar', r'\doublebar', r'\setdoublebar', r'\alaligne',
        r'\changecontext', r'\Changecontext', r'\leftrepeat', r'\rightrepeat',
        r'\leftrightrepeat', r'\setrightrepeat', r'\setleftrepeat',
    }
    cleaned: list[tuple[str, list[str]]] = []
    for hdr, lines in blocks:
        body = list(lines)
        while body and (not body[-1].strip() or body[-1].strip() in seps
                        or body[-1].strip().startswith(r'\generalmeter')):
            body.pop()
        cleaned.append((hdr, body))
    return cleaned


def _count_staves_per_page(pdf_path: Path) -> list[int]:
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


def _barline_at(measure: ET.Element, location: str) -> ET.Element | None:
    return measure.find(f'barline[@location="{location}"]')


def _assert_unrolls_losslessly(bars, units):
    unrolled = unroll_units(units)
    assert len(unrolled) == len(bars)
    assert [strict_bar_signature(b) for b in unrolled] == [strict_bar_signature(b) for b in bars]


# --------------------------------------------------------------------------- 1. Settings & metadata

def test_settings_repeats_full_and_validation(tmp_path):
    assert parse_settings({'notation': {'repeats': 'full'}}).repeats == 'full'
    assert parse_settings({'notation': {'repeats': 'off'}}, cli={'repeats': 'full'}).repeats == 'full'
    assert parse_settings({'notation': {'repeats': 'full'}}, cli={'repeats': 'simile'}).repeats == 'simile'

    for bad in ('always', 'section', True, 2):
        with pytest.raises(ScoreError, match='off, simile or full'):
            parse_settings({'notation': {'repeats': bad}})

    score = build(tmp_path, _sequence(_phrase(4) * 2), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert score.settings.repeats == 'full'


# --------------------------------------------------------------------------- 2. score_structure

@pytest.mark.parametrize('length,times', [(4, 2), (4, 3), (8, 2), (16, 2)])
def test_structure_plain_repeats_4_8_16_and_multi_time(tmp_path, length, times):
    body = _phrase(length)
    score = build(tmp_path, _sequence(body * times), cli={'repeats': 'full'}, **FOUR_FOUR)
    blocks = select_repeat_blocks(score.bars)
    assert blocks == [RepeatBlock('plain', 0, length * times, length, times)]

    units = plan_units(score.bars, repeats='full')
    assert sum(len(u.bars) for u in units) == length
    assert units[0].repeat_start is True
    assert units[-1].repeat_end == times
    assert all(not u.repeat_start for u in units[1:])
    assert all(u.repeat_end is None for u in units[:-1])
    _assert_unrolls_losslessly(score.bars, units)


def test_structure_volta_endings_e1_e2_and_preferences(tmp_path):
    # L=4, e=1: |: A B C | [1. D1 :| [2. D2
    p_e1 = [_bar_v(0), _bar_v(1), _bar_v(2), _bar_v(3), _bar_v(0), _bar_v(1), _bar_v(2), _bar_v(4)]
    s_e1 = build(tmp_path, _sequence(p_e1), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_e1.bars) == [RepeatBlock('volta', 0, 8, 4, 2, ending_len=1)]
    u_e1 = plan_units(s_e1.bars, repeats='full')
    assert len(u_e1) == 5
    assert (u_e1[0].repeat_start, u_e1[0].volta_start) == (True, None)
    assert (u_e1[3].volta_start, u_e1[3].volta_stop, u_e1[3].repeat_end) == ('1', 'stop', 2)
    assert (u_e1[4].volta_start, u_e1[4].volta_stop, u_e1[4].repeat_end) == ('2', 'discontinue', None)
    _assert_unrolls_losslessly(s_e1.bars, u_e1)

    # L=8, e=2: 6 shared bars + 2-bar 1st ending + 2-bar 2nd ending.
    shared6 = _phrase(6, 0)
    p_e2 = shared6 + [_bar_v(10), _bar_v(11)] + shared6 + [_bar_v(12), _bar_v(13)]
    s_e2 = build(tmp_path, _sequence(p_e2), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_e2.bars) == [RepeatBlock('volta', 0, 16, 8, 2, ending_len=2)]
    u_e2 = plan_units(s_e2.bars, repeats='full')
    assert len(u_e2) == 10
    assert (u_e2[6].volta_start, u_e2[6].volta_stop, u_e2[6].repeat_end) == ('1', None, None)
    assert (u_e2[7].volta_start, u_e2[7].volta_stop, u_e2[7].repeat_end) == (None, 'stop', 2)
    assert (u_e2[8].volta_start, u_e2[8].volta_stop, u_e2[8].repeat_end) == ('2', None, None)
    assert (u_e2[9].volta_start, u_e2[9].volta_stop, u_e2[9].repeat_end) == (None, 'discontinue', None)
    _assert_unrolls_losslessly(s_e2.bars, u_e2)

    # L=8 when only the final bar differs must prefer e=1 (saves 7) over e=2 (saves 6).
    shared7 = _phrase(7, 0)
    s_pref = build(tmp_path, _sequence(shared7 + [_bar_v(10)] + shared7 + [_bar_v(11)]),
                   cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_pref.bars) == [RepeatBlock('volta', 0, 16, 8, 2, ending_len=1)]
    _assert_unrolls_losslessly(s_pref.bars, plan_units(s_pref.bars, repeats='full'))

    # L=4, e=2 has L - e = 2 < 3 so it must NOT fold into a volta.
    p_short = [_bar_v(0), _bar_v(1), _bar_v(2), _bar_v(3), _bar_v(0), _bar_v(1), _bar_v(4), _bar_v(5)]
    s_short = build(tmp_path, _sequence(p_short), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_short.bars) == []


def test_structure_phrase_anchor_alignment_and_resets(tmp_path):
    # Off-by-1 shift (1 intro bar + P4 + P4) is misaligned with anchor 0 -> NOT folded.
    p4 = _phrase(4, 1)
    s_mis = build(tmp_path, _sequence([_bar_v(0)] + p4 + p4), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_mis.bars) == []

    # Section on bar 2 (index 1) resets the 4-bar anchor -> DOES fold bars[1:9].
    s_sec = build(tmp_path, _sequence([_bar_v(0)] + p4 + p4),
                  meta={'sections': {2: 'A'}}, cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_sec.bars) == [RepeatBlock('plain', 1, 9, 4, 2)]
    _assert_unrolls_losslessly(s_sec.bars, plan_units(s_sec.bars, repeats='full'))

    # Meter change on bar 2 (3/4 intro bar -> 4/4 phrase) resets the 4-bar anchor -> DOES fold bars[1:9].
    hits_meter = [(0, KICK), (1, SNARE), (2, KICK)] + _sequence(p4 + p4, start=3)
    s_meter = build(tmp_path, hits_meter, sigs=[(0, 3, 4), (3, 4, 4)], cli={'repeats': 'full'})
    assert select_repeat_blocks(s_meter.bars) == [RepeatBlock('plain', 1, 9, 4, 2)]
    _assert_unrolls_losslessly(s_meter.bars, plan_units(s_meter.bars, repeats='full'))

    # Pickup bar 0 sets first non-pickup anchor at index 1 -> DOES fold bars[1:9].
    hits_pick = [(0, SNARE)] + _sequence(p4 + p4, start=1)
    s_pick = build(tmp_path, hits_pick, meta={'pickup_beats': 1, 'source_leading_beats': 1},
                   sigs=[(0, 1, 4), (1, 4, 4)], cli={'repeats': 'full'})
    assert select_repeat_blocks(s_pick.bars) == [RepeatBlock('plain', 1, 9, 4, 2)]
    _assert_unrolls_losslessly(s_pick.bars, plan_units(s_pick.bars, repeats='full'))


def test_structure_single_bar_groove_and_strict_midi_note_equality(tmp_path):
    # Single-bar groove A*8 is NOT folded into |: ... :| (handled by % similes instead).
    s_groove = build(tmp_path, _sequence([_bar_v(0)] * 8), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_groove.bars) == []
    units_g = plan_units(s_groove.bars, repeats='full')
    assert [u.kind for u in units_g] == ['bar'] + ['simile-1'] * 7

    # Visually identical GM 38 (Acoustic Snare) vs GM 40 (Electric Snare) MUST NOT fold in repeats='full'.
    p_38 = _phrase(4, 0, snare=38)
    p_40 = _phrase(4, 0, snare=40)
    s_snare = build(tmp_path, _sequence(p_38 + p_40), cli={'repeats': 'full'}, **FOUR_FOUR)
    assert bar_signature(s_snare.bars[0]) == bar_signature(s_snare.bars[4])
    assert strict_bar_signature(s_snare.bars[0]) != strict_bar_signature(s_snare.bars[4])
    assert select_repeat_blocks(s_snare.bars) == []

    # Simultaneous mixed-mark hits (HH mark=None + HHO mark='open') sort cleanly in strict_bar_signature.
    s_mixed = build(tmp_path, [(0, HH), (0, HHO), (4, HH), (4, HHO)], **FOUR_FOUR)
    assert strict_bar_signature(s_mixed.bars[0]) == strict_bar_signature(s_mixed.bars[1])


def test_structure_interior_guards_and_double_bar_precedence(tmp_path):
    p4 = _phrase(4, 0)
    q4 = _phrase(4, 10)

    # Section label on pass 2 (bar 5) prevents folding so the section is never swallowed.
    s_sec2 = build(tmp_path, _sequence(p4 + p4), meta={'sections': {5: 'B'}}, cli={'repeats': 'full'}, **FOUR_FOUR)
    assert select_repeat_blocks(s_sec2.bars) == []

    # Tempo change on pass 2 (beat 16 = bar 5) prevents folding.
    s_tmp2 = build(tmp_path, _sequence(p4 + p4), sigs=[(0, 4, 4)], tempo=120, tempos=[(16, 150)],
                   cli={'repeats': 'full'})
    assert select_repeat_blocks(s_tmp2.bars) == []

    # Interior meter change inside body prevents folding.
    hits_m = ([(0, KICK), (1, SNARE), (4, KICK), (5, TOM), (7, KICK), (8, SNARE), (11, KICK), (12, HH)]
              + [(15, KICK), (16, SNARE), (19, KICK), (20, TOM), (22, KICK), (23, SNARE), (26, KICK), (27, HH)])
    s_int_m = build(tmp_path, hits_m,
                    sigs=[(0, 4, 4), (4, 3, 4), (7, 4, 4), (15, 4, 4), (19, 3, 4), (22, 4, 4)],
                    cli={'repeats': 'full'})
    assert select_repeat_blocks(s_int_m.bars) == []

    # Double bar precedence:
    # - Section starting at |: (bar 5): |: takes precedence -> double_bar_before is False.
    # - Section starting right after :| (bar 13): :| takes precedence -> double_bar_before is False.
    # - Section starting after a plain bar (bar 17): double_bar_before is True.
    r4 = _phrase(4, 20)
    t4 = _phrase(4, 30)
    s_dbl = build(tmp_path, _sequence(q4 + p4 + p4 + r4 + t4),
                  meta={'sections': {5: 'Chorus', 13: 'Bridge', 17: 'Outro'}},
                  cli={'repeats': 'full'}, **FOUR_FOUR)
    units_dbl = plan_units(s_dbl.bars, repeats='full')
    by_sec = {u.first.section: u for u in units_dbl if u.first.section is not None}
    assert by_sec['Chorus'].repeat_start is True and by_sec['Chorus'].double_bar_before is False
    assert by_sec['Bridge'].repeat_start is False and by_sec['Bridge'].double_bar_before is False
    assert by_sec['Outro'].double_bar_before is True
    _assert_unrolls_losslessly(s_dbl.bars, units_dbl)


def test_structure_printed_start_similes_and_no_simile_bars_in_full_mode(tmp_path):
    # Shared body [A, A, B] + [1. B :| + [2. C] + [C] outside:
    # - Inside shared body: bar 1 becomes % (simile-1).
    # - Inside [1.: B MUST NOT become % across the volta_start='1' boundary!
    # - After [2.: C MUST NOT become % across the volta_stop='discontinue' boundary!
    a, b, c = _bar_v(0), _bar_v(1), _bar_v(2)
    seq = [a, a, b, b, a, a, b, c, c]
    score = build(tmp_path, _sequence(seq), cli={'repeats': 'full'}, **FOUR_FOUR)
    units = plan_units(score.bars, repeats='full')
    assert [(u.kind, u.printed_start, u.repeat_start, u.volta_start, u.volta_stop, u.repeat_end) for u in units] == [
        ('bar', 1, True, None, None, None),
        ('simile-1', 2, False, None, None, None),
        ('bar', 3, False, None, None, None),
        ('bar', 4, False, '1', 'stop', 2),       # B inside [1. stays plain 'bar', not '%'
        ('bar', 5, False, '2', 'discontinue', None),
        ('bar', 6, False, None, None, None),     # C after [2. stays plain 'bar', not '%'
    ]
    _assert_unrolls_losslessly(score.bars, units)

    # no_simile_bars forces bar index 1 inside the repeat body to engrave in full.
    units_nosim = plan_units(score.bars, repeats='full', no_simile_bars={1})
    assert units_nosim[1].kind == 'bar'
    _assert_unrolls_losslessly(score.bars, units_nosim)

    # With pickup bar 0 + plain repeat + multi-rest: printed_start is sequential 0, 1, 2, ...
    p4 = [_bar_v(0), _bar_v(1), _bar_v(2), _bar_v(3)]
    hits = [(0, SNARE)] + _sequence(p4 + p4 + [None, None, _bar_v(4)], start=1)
    s_pick = build(tmp_path, hits, meta={'pickup_beats': 1, 'source_leading_beats': 1},
                   sigs=[(0, 1, 4), (1, 4, 4)], cli={'repeats': 'full'})
    u_pick = plan_units(s_pick.bars, repeats='full')
    assert [(u.kind, u.printed_start, len(u.bars)) for u in u_pick] == [
        ('bar', 0, 1),
        ('bar', 1, 1), ('bar', 2, 1), ('bar', 3, 1), ('bar', 4, 1),
        ('multi-rest', 5, 2),
        ('bar', 7, 1),
    ]
    _assert_unrolls_losslessly(s_pick.bars, u_pick)


def test_structure_real_song_inochi_full_repeats():
    song_full = score_core.build_score(SONG_MIDI, SONG_META, cli={'repeats': 'full'})
    units = plan_units(song_full.bars, repeats='full', repeat_counters=True)
    assert len(song_full.bars) == 202
    assert sum(len(u.bars) for u in units) == 177
    assert units[0].printed_start == 0
    cursor = 0
    for u in units:
        assert u.printed_start == cursor
        cursor += len(u.bars)
    assert cursor == 177
    _assert_unrolls_losslessly(song_full.bars, units)


# --------------------------------------------------------------------------- 3. MusicXML + Unrolling Validator

def test_musicxml_barline_xsd_order_and_topologies(tmp_path):
    # A. Piece-start |:, plain x3, back-to-back :| |:, piece-end :|.
    p4, q4 = _phrase(4, 0), _phrase(4, 10)
    s_plain = build(tmp_path, _sequence(p4 * 3 + q4 * 2), cli={'repeats': 'full'}, **FOUR_FOUR)
    p_xml, r_plain = _write_xml(s_plain, tmp_path, 'plain.musicxml')
    ms = r_plain.findall('part/measure')
    assert len(ms) == 8

    # Piece-start |:
    bl0_l = _barline_at(ms[0], 'left')
    assert bl0_l is not None and [c.tag for c in bl0_l] == ['bar-style', 'repeat']
    assert bl0_l.findtext('bar-style') == 'heavy-light'
    assert bl0_l.find('repeat').get('direction') == 'forward'

    # End of plain x3 (back-to-back with next |:)
    bl3_r = _barline_at(ms[3], 'right')
    assert bl3_r is not None and [c.tag for c in bl3_r] == ['bar-style', 'repeat']
    assert bl3_r.findtext('bar-style') == 'light-heavy'
    assert (bl3_r.find('repeat').get('direction'), bl3_r.find('repeat').get('times')) == ('backward', '3')

    # Start of second repeat (back-to-back)
    bl4_l = _barline_at(ms[4], 'left')
    assert bl4_l is not None and [c.tag for c in bl4_l] == ['bar-style', 'repeat']
    assert bl4_l.find('repeat').get('direction') == 'forward'

    # Piece-end :|
    bl7_r = _barline_at(ms[7], 'right')
    assert bl7_r is not None and [c.tag for c in bl7_r] == ['bar-style', 'repeat']
    assert bl7_r.findtext('bar-style') == 'light-heavy'
    assert (bl7_r.find('repeat').get('direction'), bl7_r.find('repeat').get('times')) == ('backward', '2')
    assert validate_musicxml(s_plain, p_xml).startswith('MusicXML OK')

    # B. Volta e=1 ending at piece-end [2.
    s_v1 = build(tmp_path, _sequence([_bar_v(0), _bar_v(1), _bar_v(2), _bar_v(3),
                                      _bar_v(0), _bar_v(1), _bar_v(2), _bar_v(4)]),
                 cli={'repeats': 'full'}, **FOUR_FOUR)
    p_v1, r_v1 = _write_xml(s_v1, tmp_path, 'volta1.musicxml')
    mv1 = r_v1.findall('part/measure')
    assert len(mv1) == 5
    # Measure 3 ([1. + :|): exact XSD child order bar-style -> ending -> repeat.
    bl3_l = _barline_at(mv1[3], 'left')
    assert bl3_l is not None and [c.tag for c in bl3_l] == ['ending']
    assert (bl3_l.find('ending').get('number'), bl3_l.find('ending').get('type')) == ('1', 'start')
    bl3_r = _barline_at(mv1[3], 'right')
    assert bl3_r is not None and [c.tag for c in bl3_r] == ['bar-style', 'ending', 'repeat']
    assert (bl3_r.find('ending').get('number'), bl3_r.find('ending').get('type')) == ('1', 'stop')
    assert (bl3_r.find('repeat').get('direction'), bl3_r.find('repeat').get('times')) == ('backward', '2')
    # Measure 4 ([2. at piece-end): left ending start, right bar-style light-heavy -> ending discontinue.
    bl4_l = _barline_at(mv1[4], 'left')
    assert bl4_l is not None and [c.tag for c in bl4_l] == ['ending']
    assert (bl4_l.find('ending').get('number'), bl4_l.find('ending').get('type')) == ('2', 'start')
    bl4_r = _barline_at(mv1[4], 'right')
    assert bl4_r is not None and [c.tag for c in bl4_r] == ['bar-style', 'ending']
    assert bl4_r.findtext('bar-style') == 'light-heavy'
    assert (bl4_r.find('ending').get('number'), bl4_r.find('ending').get('type')) == ('2', 'discontinue')
    assert validate_musicxml(s_v1, p_v1).startswith('MusicXML OK')

    # C. Volta e=2 (2-bar endings).
    shared6 = _phrase(6, 0)
    s_v2 = build(tmp_path, _sequence(shared6 + [_bar_v(10), _bar_v(11)] + shared6 + [_bar_v(12), _bar_v(13)]),
                 cli={'repeats': 'full'}, **FOUR_FOUR)
    p_v2, r_v2 = _write_xml(s_v2, tmp_path, 'volta2.musicxml')
    mv2 = r_v2.findall('part/measure')
    assert len(mv2) == 10
    assert _barline_at(mv2[6], 'left').find('ending').get('type') == 'start'
    assert _barline_at(mv2[6], 'right') is None
    assert _barline_at(mv2[7], 'left') is None
    assert [c.tag for c in _barline_at(mv2[7], 'right')] == ['bar-style', 'ending', 'repeat']
    assert _barline_at(mv2[8], 'left').find('ending').get('number') == '2'
    assert _barline_at(mv2[8], 'right') is None
    assert [c.tag for c in _barline_at(mv2[9], 'right')] == ['bar-style', 'ending']
    assert validate_musicxml(s_v2, p_v2).startswith('MusicXML OK')


def test_validator_unroll_real_song_full_repeats_with_and_without_sections(tmp_path):
    # Without sections
    s_full = score_core.build_score(SONG_MIDI, SONG_META, cli={'repeats': 'full'})
    p_full, r_full = _write_xml(s_full, tmp_path, 'inochi-full.musicxml')
    assert len(r_full.findall('part/measure')) == 177
    msg = validate_musicxml(s_full, p_full)
    assert msg.startswith('MusicXML OK')
    assert '177' in msg and '202' in msg and '1952' in msg

    # With 9 sections
    meta_sec = dict(score_core.read_yaml(SONG_META))
    meta_sec['sections'] = dict(INOCHI_SECTIONS)
    s_sec = score_core.build_score(SONG_MIDI, metadata=meta_sec, cli={'repeats': 'full'})
    p_sec, r_sec = _write_xml(s_sec, tmp_path, 'inochi-full-sec.musicxml')
    assert len(r_sec.findall('part/measure')) == 177
    msg_sec = validate_musicxml(s_sec, p_sec)
    assert msg_sec.startswith('MusicXML OK')
    assert '177' in msg_sec and '202' in msg_sec and '1952' in msg_sec


@pytest.mark.parametrize('tamper', ['times', 'remove_repeat', 'ending_number', 'ending_type', 'mutate_note'])
def test_validator_catches_full_repeat_tampering(tmp_path, tamper):
    p4 = _phrase(4, 0)
    volta = [_bar_v(10), _bar_v(11), _bar_v(12), _bar_v(13), _bar_v(10), _bar_v(11), _bar_v(12), _bar_v(14)]
    score = build(tmp_path, _sequence(p4 * 3 + volta), cli={'repeats': 'full'}, **FOUR_FOUR)
    path, root = _write_xml(score, tmp_path, f'tamper-{tamper}.musicxml')
    assert validate_musicxml(score, path).startswith('MusicXML OK')

    ms = root.findall('part/measure')
    if tamper == 'times':
        _barline_at(ms[3], 'right').find('repeat').set('times', '2')
    elif tamper == 'remove_repeat':
        bl = _barline_at(ms[3], 'right')
        bl.remove(bl.find('repeat'))
    elif tamper == 'ending_number':
        _barline_at(ms[7], 'left').find('ending').set('number', '2')
    elif tamper == 'ending_type':
        _barline_at(ms[7], 'right').find('ending').set('type', 'discontinue')
    elif tamper == 'mutate_note':
        note = next(n for n in ms[0].findall('note') if n.find('instrument') is not None)
        inst = note.find('instrument')
        inst.set('id', 'P1-I47' if not inst.get('id').endswith('I47') else 'P1-I38')
    ET.ElementTree(root).write(path)

    with pytest.raises(ValidationError):
        validate_musicxml(score, path)


def test_musicxml_cli_repeats_full(tmp_path):
    midi = make_midi(tmp_path / 'rep.mid', _sequence(_phrase(4) * 2), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: Full Repeat CLI\n', encoding='utf-8')
    xml_full = tmp_path / 'full.musicxml'

    assert midi_to_musicxml.main([str(midi), '--metadata', str(meta), '--out', str(xml_full),
                                  '--repeats', 'full']) == 0
    assert len(ET.parse(xml_full).getroot().findall('part/measure')) == 4
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml_full),
                                '--repeats', 'full']) == 0
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml_full),
                                '--repeats', 'simile']) == 1

    out_dir = tmp_path / 'build-full'
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out_dir),
                             '--no-pdf', '--repeats', 'full']) == 0
    assert len(ET.parse(out_dir / 'score.musicxml').getroot().findall('part/measure')) == 4


@needs_xsd
def test_musicxml_xsd_full_repeats(tmp_path):
    p4 = _phrase(4, 0)
    v1 = [_bar_v(10), _bar_v(11), _bar_v(12), _bar_v(13), _bar_v(10), _bar_v(11), _bar_v(12), _bar_v(14)]
    shared6 = _phrase(6, 20)
    v2 = shared6 + [_bar_v(30), _bar_v(31)] + shared6 + [_bar_v(32), _bar_v(33)]
    hits = [(0, SNARE)] + _sequence(p4 * 3 + v1 + v2, start=1)
    score = build(tmp_path, hits,
                  meta={'pickup_beats': 1, 'source_leading_beats': 1,
                        'sections': {1: 'Intro', 13: 'A', 21: 'Chorus'}},
                  sigs=[(0, 1, 4), (1, 4, 4)], cli={'repeats': 'full'})
    path, _root = _write_xml(score, tmp_path)
    validate_musicxml(score, path, Path(XSD))


# --------------------------------------------------------------------------- 4. MusiXTeX + PDF integration

def test_musixtex_full_repeats_barlines_voltas_times_and_cli(tmp_path):
    p4, q4 = _phrase(4, 0), _phrase(4, 10)
    v1 = [_bar_v(20), _bar_v(21), _bar_v(22), _bar_v(23), _bar_v(20), _bar_v(21), _bar_v(22), _bar_v(24)]

    # Piece-start |:, x3 label, back-to-back :| |:, and piece-end :| (single-line budget for inline :| |:).
    s_b2b = build(tmp_path, _sequence(p4 * 3 + q4 * 2), cli={'repeats': 'full'}, **FOUR_FOUR)
    tex_b2b = midi_to_musixtex.convert(s_b2b, line_width=300.0, max_bars_per_line=8)
    tex_b2b.encode('ascii')
    assert r'\zleftrepeat' in tex_b2b
    assert r'\leftrightrepeat' in tex_b2b
    assert r'\setrightrepeat' in tex_b2b
    assert '3x' in tex_b2b

    # Mid-system \leftrepeat and \rightrepeat surrounded by plain bars.
    s_mid = build(tmp_path, _sequence([_bar_v(0)] + _phrase(4, 1) * 2 + [_bar_v(30)]),
                  meta={'sections': {2: 'A'}}, cli={'repeats': 'full'}, **FOUR_FOUR)
    tex_mid = midi_to_musixtex.convert(s_mid, line_width=300.0, max_bars_per_line=6)
    tex_mid.encode('ascii')
    assert r'\leftrepeat' in tex_mid
    assert r'\rightrepeat' in tex_mid

    # Volta 1. and 2. commands (MusiXTeX appends \voltadot automatically, so accept 1 or 1.).
    s_volta = build(tmp_path, _sequence(v1), cli={'repeats': 'full'}, **FOUR_FOUR)
    tex_volta = midi_to_musixtex.convert(s_volta)
    tex_volta.encode('ascii')
    assert re.search(r'\\[Ss]etvolta(?:box)?\{?1\.?\}?', tex_volta)
    assert re.search(r'\\[Ss]etvolta(?:box)?\{?2\.?\}?', tex_volta)

    # CLI --repeats full on midi_to_musixtex.
    midi = make_midi(tmp_path / 'rep.mid', _sequence(p4 * 2), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: TeX Full CLI\n', encoding='utf-8')
    out_tex = tmp_path / 'full.tex'
    assert midi_to_musixtex.main([str(midi), '--metadata', str(meta), '--out', str(out_tex),
                                  '--repeats', 'full']) == 0
    tex_cli = out_tex.read_text(encoding='ascii')
    assert r'\zleftrepeat' in tex_cli and r'\setrightrepeat' in tex_cli


def test_musixtex_full_repeats_sequential_mid_system_bar_numbers(tmp_path):
    p4 = _phrase(4, 0)
    v1 = [_bar_v(10), _bar_v(11), _bar_v(12), _bar_v(13), _bar_v(10), _bar_v(11), _bar_v(12), _bar_v(14)]
    shared6 = _phrase(6, 20)
    v2 = shared6 + [_bar_v(30), _bar_v(31)] + shared6 + [_bar_v(32), _bar_v(33)]
    score = build(tmp_path, _sequence(p4 * 3 + v1 + v2), cli={'repeats': 'full'}, **FOUR_FOUR)
    tex, systems = midi_to_musixtex.convert_with_layout(score)
    tex.encode('ascii')

    # Every system-start unit has no \barnum; every mid-system unit emits \barnum{pitch}{printed_start}.
    blocks = _bar_blocks(tex)
    flat_units = [u for sys_u in systems for u in sys_u]
    sys_start_ids = {id(sys_u[0]) for sys_u in systems}
    assert len(blocks) == len(flat_units)
    for unit, (_hdr, lines) in zip(flat_units, blocks):
        bn_hits = re.findall(r'\\barnum\{(\d+)\}\{(\d+)\}', '\n'.join(lines))
        if id(unit) in sys_start_ids:
            assert bn_hits == [], f'system-start bar {unit.printed_start} must not emit \\barnum'
        else:
            assert len(bn_hits) == 1, f'mid-system bar {unit.printed_start} expected 1 \\barnum, got {bn_hits}'
            assert int(bn_hits[0][1]) == unit.printed_start

    # Real song in repeats='full' mode: sequential printed_start bar numbers and zero on simile-2 interior barlines.
    song_full = score_core.build_score(SONG_MIDI, SONG_META, cli={'repeats': 'full'})
    song_tex, song_sys = midi_to_musixtex.convert_with_layout(song_full)
    song_blocks = _bar_blocks(song_tex)
    song_units = [u for sys_u in song_sys for u in sys_u]
    song_starts = {id(sys_u[0]) for sys_u in song_sys}
    assert len(song_blocks) == len(song_units)
    for unit, (_hdr, lines) in zip(song_units, song_blocks):
        joined = '\n'.join(lines)
        bn_hits = re.findall(r'\\barnum\{(\d+)\}\{(\d+)\}', joined)
        if id(unit) in song_starts:
            assert bn_hits == []
        else:
            assert len(bn_hits) == 1 and int(bn_hits[0][1]) == unit.printed_start
        if unit.kind == 'simile-2':
            # Interior \bar (where \similetwo sits) must have no \barnum after it.
            after_mid_bar = joined.split(r'\bar', 1)[1]
            assert r'\barnum' not in after_mid_bar


@needs_pdf
def test_pdf_full_repeats_synthetic_end_to_end(tmp_path):
    p4 = _phrase(4, 0)
    v1 = [_bar_v(10), _bar_v(11), _bar_v(12), _bar_v(13), _bar_v(10), _bar_v(11), _bar_v(12), _bar_v(14)]
    shared6 = _phrase(6, 20)
    v2 = shared6 + [_bar_v(30), _bar_v(31)] + shared6 + [_bar_v(32), _bar_v(33)]
    midi = make_midi(tmp_path / 'synth.mid', _sequence(p4 * 3 + v1 + v2), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text(
        'title: Phase 3 Full Repeat Synthetic\n'
        'sections:\n'
        '  1: Intro\n'
        '  13: A\n'
        '  21: Chorus\n',
        encoding='utf-8',
    )
    out = tmp_path / 'out'
    work = tmp_path / 'work'
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out),
                             '--work-dir', str(work), '--repeats', 'full']) == 0
    assert (out / 'score.musicxml').exists() and (out / 'score.pdf').exists()
    log = (work / 'score.log').read_text(errors='replace')
    overfull = [float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
    assert not overfull or max(overfull) <= 4.0

    # Also verify render_score CLI directly accepts --repeats full.
    short_midi = make_midi(tmp_path / 'short.mid', _sequence(p4 * 2), **FOUR_FOUR)
    short_meta = tmp_path / 'short.yaml'
    short_meta.write_text('title: Render Full CLI\n', encoding='utf-8')
    short_pdf = tmp_path / 'short.pdf'
    assert render_score.main([str(short_midi), '--metadata', str(short_meta), '--out', str(short_pdf),
                              '--repeats', 'full']) == 0
    short_score = score_core.build_score(short_midi, short_meta, cli={'repeats': 'full'})
    assert validate_pdf(short_score, short_pdf).startswith('PDF OK')


@needs_pdf
def test_pdf_full_repeats_inochi_end_to_end(tmp_path):
    out = tmp_path / 'out'
    work = tmp_path / 'work'
    assert build_score.main([str(SONG_MIDI), '--metadata', str(SONG_META), '--out-dir', str(out),
                             '--work-dir', str(work), '--repeats', 'full']) == 0

    assert len(ET.parse(out / 'score.musicxml').getroot().findall('part/measure')) == 177
    log = (work / 'score.log').read_text(errors='replace')
    overfull = [float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
    assert not overfull or max(overfull) <= 4.0

    # Verify pages 2..N never start with a simile (% or //).
    tex = (work / 'score.tex').read_text(encoding='ascii')
    systems = _systems_from_tex(tex)
    staves_per_page = _count_staves_per_page(work / 'notes.pdf')
    assert len(staves_per_page) >= 2
    assert sum(staves_per_page) == len(systems)
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
        sys_offset += n_staves
