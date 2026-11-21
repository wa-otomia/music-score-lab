"""Tests for Phase 2 features: intra-beat post-rest beaming, notation.beam_eighths, and sections."""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from conftest import HAVE_PDF_TOOLS, HH, KICK, RIDE, SNARE, SONG_META, SONG_MIDI, TOM, build, make_midi
import build_score
import midi_to_musicxml
import midi_to_musixtex
import render_score
import score_core
import validate_score
from score_core import R, ScoreError, assign_beams, parse_settings, voice_items
from score_structure import has_double_bar_before, multi_rest_lengths, plan_units
from validate_score import ValidationError, validate_musicxml, validate_pdf

FOUR_FOUR = {'sigs': [(0, 4, 4)]}
XSD = os.environ.get('MUSICXML_XSD')
needs_xsd = pytest.mark.skipif(not (XSD and Path(XSD).exists()), reason='set MUSICXML_XSD to the MusicXML 4.0 XSD')
needs_pdf = pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs musixtex, etex, musixflx, dvipdfmx, xelatex, gs')


# --------------------------------------------------------------------------- pattern & TeX helpers

def _bar_a(offset: float) -> list[tuple]:
    """Standard 4/4 pure eighth-note groove."""
    return ([(offset + x / 2, HH) for x in range(8)]
            + [(offset, KICK), (offset + 2.5, KICK), (offset + 1, SNARE), (offset + 3, SNARE)])


def _bar_b(offset: float) -> list[tuple]:
    """Second distinct 4/4 pure eighth-note groove."""
    return ([(offset + x / 2, RIDE) for x in range(8)]
            + [(offset, KICK), (offset + 2, KICK), (offset + 1, SNARE), (offset + 3, SNARE)])


def _bar_8th_variant(offset: float, variant: int) -> list[tuple]:
    """One of 16 distinct 4/4 pure eighth-note bars (8 hand eighth-notes each)."""
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


def _system_bar_labels(system_tex: str) -> list[str]:
    return re.findall(r'^% bar (\d+(?:-\d+)?)', system_tex, flags=re.M)


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
                        or body[-1].strip() in (r'\bar', r'\doublebar', r'\setdoublebar',
                                                r'\alaligne', r'\changecontext', r'\Changecontext')
                        or body[-1].strip().startswith(r'\generalmeter')):
            body.pop()
        cleaned.append((hdr, body))
    return cleaned


def _voice_note_beams_xml(measure: ET.Element, voice: str = '1') -> list[list[tuple[str, str]]]:
    """Beam lists for primary (non-chord, non-rest, non-grace) notes in one MusicXML measure voice."""
    out: list[list[tuple[str, str]]] = []
    for note in measure.findall('note'):
        if (note.findtext('voice') == voice and note.find('chord') is None
                and note.find('rest') is None and note.find('grace') is None):
            out.append([(b.get('number'), b.text) for b in note.findall('beam')])
    return out


# --------------------------------------------------------------------------- 1. Intra-beat post-rest beaming

def test_post_rest_beaming_core(tmp_path):
    # Sextuplet beat: note at 0, 16th-triplet rest at 2/6, two consecutive beamable notes at 3/6 and 4/6.
    score = build(tmp_path, [(0, SNARE), (3 / 6, SNARE), (4 / 6, SNARE), (3, KICK)], **FOUR_FOUR)
    beat0 = [it for it in voice_items(score.bars[0], 'hand') if it.start < R]
    assert [(it.start, it.duration, it.is_rest, it.tuplet, it.beams) for it in beat0] == [
        (0, 16, False, 6, []),
        (16, 8, True, 6, []),
        (24, 8, False, 6, [(1, 'begin'), (2, 'forward hook')]),
        (32, 16, False, 6, [(1, 'end')]),
    ]
    assert all(it.tuplet_bracket is True for it in beat0)

    # Two separate beamable runs separated by a mid-beat rest inside one sextuplet beat: 0, 1/6, [rest], 4/6, 5/6.
    score2 = build(tmp_path, [(0, SNARE), (1 / 6, SNARE), (4 / 6, SNARE), (5 / 6, SNARE), (3, KICK)], **FOUR_FOUR)
    beat0_2 = [it for it in voice_items(score2.bars[0], 'hand') if it.start < R]
    assert [(it.start, it.duration, it.is_rest, it.beams) for it in beat0_2] == [
        (0, 8, False, [(1, 'begin'), (2, 'forward hook')]),
        (8, 16, False, [(1, 'end')]),
        (24, 8, True, []),
        (32, 8, False, [(1, 'begin'), (2, 'begin')]),
        (40, 8, False, [(1, 'end'), (2, 'end')]),
    ]
    assert all(it.tuplet_bracket is True for it in beat0_2)


def test_musicxml_post_rest_beaming(tmp_path):
    score = build(tmp_path, [(0, SNARE), (3 / 6, SNARE), (4 / 6, SNARE), (3, KICK)], **FOUR_FOUR)
    path, root = _write_xml(score, tmp_path)
    m0 = root.findall('part/measure')[0]
    assert _voice_note_beams_xml(m0, '1') == [
        [],
        [('1', 'begin'), ('2', 'forward hook')],
        [('1', 'end')],
    ]
    starts = [t for t in m0.findall('.//notations/tuplet') if t.get('type') == 'start']
    assert len(starts) == 1 and starts[0].get('bracket') == 'yes'
    assert validate_musicxml(score, path).startswith('MusicXML OK')


def test_musixtex_post_rest_beaming(tmp_path):
    score = build(tmp_path, [(0, SNARE), (3 / 6, SNARE), (4 / 6, SNARE), (3, KICK)], **FOUR_FOUR)
    tex = midi_to_musixtex.convert(score)
    tex.encode('ascii')
    bar1 = '\n'.join(_bar_blocks(tex)[0][1])
    # First stroke at 0 is an isolated flagged 8th; post-rest strokes at 3/6 & 4/6 are beamed with a forward hook.
    assert r'\@cu{j}' in bar1
    assert r'\ibbu0{j}0\roff{\tbbu0}' in bar1
    assert r'\@tqh0{j}' in bar1
    # Tuplet contains a rest so the number is placed as a floating label, not on a beam.
    assert r'\eightit 6' in bar1
    assert r'\butext0' not in bar1


# --------------------------------------------------------------------------- 2. notation.beam_eighths

def test_beam_eighths_settings_and_override(tmp_path):
    assert parse_settings({}).beam_eighths == 'beat'
    assert parse_settings({'notation': {'beam_eighths': 'beat'}}).beam_eighths == 'beat'
    assert parse_settings({'notation': {'beam_eighths': 'half-bar'}}).beam_eighths == 'half-bar'

    for bad in ('bar', 'off', False, True, 4, None):
        with pytest.raises(ScoreError):
            parse_settings({'notation': {'beam_eighths': bad}})

    assert parse_settings({'notation': {'beam_eighths': 'beat'}}, cli={'beam_eighths': 'half-bar'}).beam_eighths == 'half-bar'
    assert parse_settings({'notation': {'beam_eighths': 'half-bar'}}, cli={'beam_eighths': 'beat'}).beam_eighths == 'beat'
    assert parse_settings({'notation': {'beam_eighths': 'half-bar'}}, cli={'beam_eighths': None}).beam_eighths == 'half-bar'

    score = build(tmp_path, _bar_a(0), meta={'notation': {'beam_eighths': 'beat'}},
                  cli={'beam_eighths': 'half-bar'}, **FOUR_FOUR)
    assert score.settings.beam_eighths == 'half-bar'
    with pytest.raises(ScoreError):
        voice_items(score.bars[0], 'hand', beam_eighths='bar')
    with pytest.raises(ScoreError):
        assign_beams([], score.bars[0], beam_eighths='bar')


def test_beam_eighths_core_pure_mixed_independent_and_non_4_4(tmp_path):
    # Pure 4/4 eighth notes: 4-eighth beam in beats 0-1 and 2-3; per-beat stays pairs.
    s_pure = build(tmp_path, _bar_a(0), **FOUR_FOUR)
    hand_hb = voice_items(s_pure.bars[0], 'hand', beam_eighths='half-bar')
    assert [it.beams for it in hand_hb] == [
        [(1, 'begin')], [(1, 'continue')], [(1, 'continue')], [(1, 'end')],
        [(1, 'begin')], [(1, 'continue')], [(1, 'continue')], [(1, 'end')],
    ]
    hand_beat = voice_items(s_pure.bars[0], 'hand', beam_eighths='beat')
    assert [it.beams for it in hand_beat] == [[(1, 'begin')], [(1, 'end')]] * 4

    # Independent per voice and per half-bar:
    # Hand: pure 8ths on beats 0-1, 16-16-8 + 8-8 on beats 2-3.
    # Foot: quarter + 8-8 on beats 0-1, pure 8ths on beats 2-3.
    hits = ([(x / 2, HH) for x in range(4)]
            + [(2, HH), (2.25, HH), (2.5, HH), (3, HH), (3.5, HH)]
            + [(0, KICK), (1, KICK), (1.5, KICK)]
            + [(2 + x / 2, KICK) for x in range(4)])
    s_indep = build(tmp_path, hits, **FOUR_FOUR)
    h_items = voice_items(s_indep.bars[0], 'hand', beam_eighths='half-bar')
    f_items = voice_items(s_indep.bars[0], 'foot', beam_eighths='half-bar')
    assert [it.beams for it in h_items[:4]] == [[(1, 'begin')], [(1, 'continue')], [(1, 'continue')], [(1, 'end')]]
    assert [it.beams for it in h_items[4:7]] == [
        [(1, 'begin'), (2, 'begin')], [(1, 'continue'), (2, 'end')], [(1, 'end')],
    ]
    assert [it.beams for it in h_items[7:]] == [[(1, 'begin')], [(1, 'end')]]
    assert [it.beams for it in f_items[:3]] == [[], [(1, 'begin')], [(1, 'end')]]
    assert [it.beams for it in f_items[3:]] == [[(1, 'begin')], [(1, 'continue')], [(1, 'continue')], [(1, 'end')]]

    # Mixed half-bars (rest, quarter, dotted-8th+16th, 16th, tuplet) stay per-beat in beats 0-1.
    mixed_cases = [
        [(0.5, HH), (1, HH), (1.5, HH), (3, KICK)],                            # leading 8th rest
        [(0, HH), (1, HH), (1.5, HH), (3, KICK)],                              # quarter on beat 0
        [(0, HH), (0.75, HH), (1, HH), (1.5, HH), (3, KICK)],                  # dotted 8th + 16th
        [(0, HH), (0.25, HH), (0.5, HH), (1, HH), (1.5, HH), (3, KICK)],       # 16ths in beat 0
        [(0, HH), (1 / 3, HH), (2 / 3, HH), (1, HH), (1.5, HH), (3, KICK)],    # triplet in beat 0
    ]
    for case in mixed_cases:
        bar = build(tmp_path, case, **FOUR_FOUR).bars[0]
        assert [it.beams for it in voice_items(bar, 'hand', beam_eighths='half-bar')] == [
            it.beams for it in voice_items(bar, 'hand', beam_eighths='beat')
        ]

    # Non-4/4 meters (3/4, 5/4) and 2/4 pickup stay per-beat even with pure 8ths.
    for beats in (3, 5):
        s_odd = build(tmp_path, [(x / 2, HH) for x in range(beats * 2)] + [(0, KICK)], sigs=[(0, beats, 4)])
        assert [it.beams for it in voice_items(s_odd.bars[0], 'hand', beam_eighths='half-bar')] == [
            [(1, 'begin')], [(1, 'end')]
        ] * beats

    s_pickup = build(tmp_path, [(x / 2, SNARE) for x in range(4)] + _bar_a(2),
                     meta={'pickup_beats': 2, 'source_leading_beats': 2}, sigs=[(0, 2, 4), (2, 4, 4)])
    assert [it.beams for it in voice_items(s_pickup.bars[0], 'hand', beam_eighths='half-bar')] == [
        [(1, 'begin')], [(1, 'end')], [(1, 'begin')], [(1, 'end')],
    ]
    assert [it.beams for it in voice_items(s_pickup.bars[1], 'hand', beam_eighths='half-bar')] == [
        [(1, 'begin')], [(1, 'continue')], [(1, 'continue')], [(1, 'end')],
    ] * 2


def test_musicxml_beam_eighths_half_bar_and_real_song(tmp_path):
    s_hb = build(tmp_path, _bar_a(0), meta={'notation': {'beam_eighths': 'half-bar'}}, **FOUR_FOUR)
    path, root = _write_xml(s_hb, tmp_path)
    m0 = root.findall('part/measure')[0]
    assert _voice_note_beams_xml(m0, '1') == [
        [('1', 'begin')], [('1', 'continue')], [('1', 'continue')], [('1', 'end')],
        [('1', 'begin')], [('1', 'continue')], [('1', 'continue')], [('1', 'end')],
    ]
    assert validate_musicxml(s_hb, path).startswith('MusicXML OK')

    # Real song in half-bar mode: valid MusicXML and visibly more 8th-note continue beams than beat mode.
    song_beat = score_core.build_score(SONG_MIDI, SONG_META, cli={'beam_eighths': 'beat'})
    song_hb = score_core.build_score(SONG_MIDI, SONG_META, cli={'beam_eighths': 'half-bar'})
    p_hb, r_hb = _write_xml(song_hb, tmp_path, 'song-hb.musicxml')
    assert validate_musicxml(song_hb, p_hb).startswith('MusicXML OK')
    r_beat, _ = midi_to_musicxml.convert(song_beat)

    def eighth_continues(root_el: ET.Element) -> int:
        return sum(
            1 for n in root_el.iter('note')
            if n.findtext('type') == 'eighth'
            and any(b.get('number') == '1' and b.text == 'continue' for b in n.findall('beam'))
        )

    assert eighth_continues(r_hb) > eighth_continues(r_beat)


def test_musicxml_cli_beam_eighths_flag(tmp_path):
    midi = make_midi(tmp_path / 'e8.mid', _bar_a(0), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: Beam CLI\n', encoding='utf-8')
    xml_hb = tmp_path / 'hb.musicxml'

    assert midi_to_musicxml.main([str(midi), '--metadata', str(meta), '--out', str(xml_hb),
                                  '--beam-eighths', 'half-bar']) == 0
    assert _voice_note_beams_xml(ET.parse(xml_hb).getroot().findall('part/measure')[0], '1') == [
        [('1', 'begin')], [('1', 'continue')], [('1', 'continue')], [('1', 'end')],
    ] * 2
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml_hb),
                                '--beam-eighths', 'half-bar']) == 0
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml_hb),
                                '--beam-eighths', 'beat']) == 1

    out_dir = tmp_path / 'build-hb'
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out_dir),
                             '--no-pdf', '--beam-eighths', 'half-bar']) == 0
    assert _voice_note_beams_xml(ET.parse(out_dir / 'score.musicxml').getroot().findall('part/measure')[0], '1') == [
        [('1', 'begin')], [('1', 'continue')], [('1', 'continue')], [('1', 'end')],
    ] * 2


def test_musixtex_beam_eighths_half_bar_and_cli(tmp_path):
    s_beat = build(tmp_path, _bar_a(0), meta={'notation': {'beam_eighths': 'beat'}}, **FOUR_FOUR)
    s_hb = build(tmp_path, _bar_a(0), meta={'notation': {'beam_eighths': 'half-bar'}}, **FOUR_FOUR)
    bar_beat = '\n'.join(_bar_blocks(midi_to_musixtex.convert(s_beat))[0][1])
    bar_hb = '\n'.join(_bar_blocks(midi_to_musixtex.convert(s_hb))[0][1])
    # 4/4 pure 8ths: 4 hand beam starts in beat mode vs 2 hand beam starts in half-bar mode.
    assert bar_beat.count(r'\ibu0{') == 4
    assert bar_hb.count(r'\ibu0{') == 2

    # Real song in half-bar mode converts to valid ASCII and reduces primary beam starts.
    song_beat = score_core.build_score(SONG_MIDI, SONG_META, cli={'beam_eighths': 'beat'})
    song_hb = score_core.build_score(SONG_MIDI, SONG_META, cli={'beam_eighths': 'half-bar'})
    tex_beat = midi_to_musixtex.convert(song_beat)
    tex_hb = midi_to_musixtex.convert(song_hb)
    tex_hb.encode('ascii')
    assert _score_body(tex_hb).count(r'\ibu0{') < _score_body(tex_beat).count(r'\ibu0{')

    # CLI --beam-eighths on midi_to_musixtex.
    midi = make_midi(tmp_path / 'e8.mid', _bar_a(0), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: TeX Beam CLI\n', encoding='utf-8')
    out_hb = tmp_path / 'hb.tex'
    assert midi_to_musixtex.main([str(midi), '--metadata', str(meta), '--out', str(out_hb),
                                  '--beam-eighths', 'half-bar']) == 0
    assert _score_body(out_hb.read_text(encoding='ascii')).count(r'\ibu0{') == 2


# --------------------------------------------------------------------------- 3. sections: metadata & structure

def test_sections_settings_parsing_and_validation(tmp_path):
    assert parse_settings({}).sections == {}
    assert parse_settings({'sections': {}}).sections == {}
    assert parse_settings({'sections': None}).sections == {}
    assert parse_settings({'sections': {5: ' A ', 1: 'Intro', '9': 'A' * 24}}).sections == {
        1: 'Intro', 5: 'A', 9: 'A' * 24,
    }

    bad_metas = [
        {'sections': False},
        {'sections': []},
        {'sections': ''},
        {'sections': 0},
        {'sections': 'Intro'},
        {'sections': {True: 'A'}},
        {'sections': {False: 'A'}},
        {'sections': {0: 'Intro'}},
        {'sections': {-2: 'Intro'}},
        {'sections': {'0': 'Intro'}},
        {'sections': {'1.5': 'A'}},
        {'sections': {'abc': 'A'}},
        {'sections': {1.5: 'A'}},
        {'sections': {1: 'A', '1': 'B'}},
        {'sections': {1: ''}},
        {'sections': {1: '   '}},
        {'sections': {1: 123}},
        {'sections': {1: None}},
        {'sections': {1: 'A' * 25}},
        {'sections': {1: 'Line1\nLine2'}},
    ]
    for meta in bad_metas:
        with pytest.raises(ScoreError):
            parse_settings(meta)

    # Non-ASCII rehearsal marks must fail with an English-only error message (no CJK leaked).
    for non_ascii in ('サビ', 'Aメロ', '前奏', 'Café'):
        with pytest.raises(ScoreError) as exc_info:
            parse_settings({'sections': {1: non_ascii}})
        msg = str(exc_info.value)
        assert msg.isascii(), f'Error message must be English/ASCII only: {msg!r}'

    # Out-of-range bar number fails during transcription.
    with pytest.raises(ScoreError, match=r'5.*1\.\.4'):
        build(tmp_path, _sequence([_bar_a] * 4), meta={'sections': {5: 'Chorus'}}, **FOUR_FOUR)

    # Pickup bar 0 does not shift valid section range 1..N; bar 1 works, bar 3 fails for 2 full bars.
    pickup_hits = [(0, SNARE)] + _sequence([_bar_a, _bar_b], start=1)
    s_ok = build(tmp_path, pickup_hits, meta={'pickup_beats': 1, 'source_leading_beats': 1,
                                              'sections': {1: 'Intro', 2: 'Verse'}},
                 sigs=[(0, 1, 4), (1, 4, 4)])
    assert [b.section for b in s_ok.bars] == [None, 'Intro', 'Verse']
    with pytest.raises(ScoreError, match=r'3.*1\.\.2'):
        build(tmp_path, pickup_hits, meta={'pickup_beats': 1, 'source_leading_beats': 1, 'sections': {3: 'X'}},
              sigs=[(0, 1, 4), (1, 4, 4)])


def test_sections_structure_multirest_similes_and_double_bar(tmp_path):
    # Section splits multi-rest runs cleanly.
    s_mr = build(tmp_path, _sequence([_bar_a, None, None, None, None, None, _bar_a]),
                 meta={'sections': {4: 'Break'}}, **FOUR_FOUR)
    units_mr = plan_units(s_mr.bars)
    assert [(u.kind, [b.number for b in u.bars]) for u in units_mr] == [
        ('bar', [1]), ('multi-rest', [2, 3]), ('multi-rest', [4, 5, 6]), ('bar', [7]),
    ]
    assert multi_rest_lengths(s_mr.bars) == {1: 2, 3: 3}

    # Section resets simile-1 pattern and counter.
    s_s1 = build(tmp_path, _sequence([_bar_a] * 6), meta={'sections': {4: 'A'}}, **FOUR_FOUR)
    assert [(u.kind, u.first.number, u.counter) for u in plan_units(s_s1.bars)] == [
        ('bar', 1, None), ('simile-1', 2, 2), ('simile-1', 3, 3),
        ('bar', 4, None), ('simile-1', 5, 2), ('simile-1', 6, 3),
    ]

    # Section resets simile-2: on bar 3 of A|B|A|B|A|B keeps new section self-contained (A|B|//).
    s_s2 = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b, _bar_a, _bar_b]),
                 meta={'sections': {3: 'B'}}, **FOUR_FOUR)
    assert [(u.kind, [b.number for b in u.bars]) for u in plan_units(s_s2.bars)] == [
        ('bar', [1]), ('bar', [2]), ('bar', [3]), ('bar', [4]), ('simile-2', [5, 6]),
    ]

    # Section on second bar of repeated pair OR mid-template (bar 2 of A|B|A|B) breaks simile-2.
    for sec_bar in (2, 4):
        s_mid = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b]),
                      meta={'sections': {sec_bar: 'Mid'}}, **FOUR_FOUR)
        assert [u.kind for u in plan_units(s_mid.bars)] == ['bar', 'bar', 'bar', 'bar']

    # has_double_bar_before: False on bar 0 (start), False on bar 1 after pickup bar 0, True on later sections.
    s_nopick = build(tmp_path, _sequence([_bar_a] * 4), meta={'sections': {1: 'Intro', 3: 'A'}}, **FOUR_FOUR)
    assert [has_double_bar_before(s_nopick.bars, i) for i in range(4)] == [False, False, True, False]
    assert not has_double_bar_before(s_nopick.bars, -1)
    assert not has_double_bar_before(s_nopick.bars, 4)

    pickup_hits = [(0, SNARE)] + _sequence([_bar_a] * 4, start=1)
    s_pick = build(tmp_path, pickup_hits,
                   meta={'pickup_beats': 1, 'source_leading_beats': 1, 'sections': {1: 'Intro', 3: 'A'}},
                   sigs=[(0, 1, 4), (1, 4, 4)])
    assert [has_double_bar_before(s_pick.bars, i) for i in range(len(s_pick.bars))] == [
        False, False, False, True, False,
    ]


# --------------------------------------------------------------------------- 4. MusicXML, MusiXTeX & PDF integration

def test_musicxml_sections_rehearsal_double_bar_and_tampering(tmp_path):
    hits = [(0, SNARE)] + _sequence([_bar_a, _bar_b, _bar_a, _bar_b, _bar_a, _bar_b], start=1)
    score = build(tmp_path, hits,
                  meta={'pickup_beats': 1, 'source_leading_beats': 1,
                        'sections': {1: 'Intro', 3: 'A', 5: 'Chorus'}},
                  sigs=[(0, 1, 4), (1, 4, 4)], tempo=120, tempos=[(17, 144)])
    path, root = _write_xml(score, tmp_path)
    measures = root.findall('part/measure')

    # Bar 0 (pickup): no light-light barline even though bar 1 has a section.
    assert measures[0].find('barline') is None
    # Bar 1 (index 1): rehearsal Intro with enclosure="square".
    r1 = measures[1].find('direction/direction-type/rehearsal')
    assert r1 is not None and r1.text == 'Intro' and r1.get('enclosure') == 'square'
    assert measures[1].find('direction').get('placement') == 'above'
    # Bar 2 (index 2): right light-light barline before section A on bar 3.
    bl2 = measures[2].find('barline')
    assert bl2 is not None and bl2.get('location') == 'right' and bl2.findtext('bar-style') == 'light-light'
    # Bar 3 (index 3): rehearsal A.
    assert measures[3].findtext('direction/direction-type/rehearsal') == 'A'
    # Bar 4 (index 4): right light-light barline before section Chorus on bar 5.
    assert measures[4].findtext('barline/bar-style') == 'light-light'
    # Bar 5 (index 5): rehearsal direction precedes tempo direction.
    dirs5 = measures[5].findall('direction')
    assert len(dirs5) == 2
    assert dirs5[0].findtext('direction-type/rehearsal') == 'Chorus'
    assert dirs5[1].findtext('direction-type/metronome/per-minute') == '144'
    # Final bar keeps light-heavy barline.
    assert measures[-1].findtext('barline/bar-style') == 'light-heavy'

    assert validate_musicxml(score, path).startswith('MusicXML OK')

    # Tampering with rehearsal text, rehearsal enclosure, or light-light barline fails validation.
    for tamper in ('rehearsal_text', 'rehearsal_enclosure', 'barline_style', 'barline_remove'):
        t_path, t_root = _write_xml(score, tmp_path, f'tamper-{tamper}.musicxml')
        ms = t_root.findall('part/measure')
        if tamper == 'rehearsal_text':
            ms[3].find('direction/direction-type/rehearsal').text = 'Z'
        elif tamper == 'rehearsal_enclosure':
            ms[3].find('direction/direction-type/rehearsal').set('enclosure', 'circle')
        elif tamper == 'barline_style':
            ms[2].find('barline/bar-style').text = 'regular'
        elif tamper == 'barline_remove':
            ms[2].remove(ms[2].find('barline'))
        ET.ElementTree(t_root).write(t_path)
        with pytest.raises(ValidationError):
            validate_musicxml(score, t_path)


@needs_xsd
def test_musicxml_xsd_sections_and_half_bar_beams(tmp_path):
    hits = ([(0, SNARE)]
            + [(1, SNARE), (1 + 3 / 6, SNARE), (1 + 4 / 6, SNARE), (4, KICK)]
            + _sequence([_bar_a, _bar_a, _bar_b, _bar_a, _bar_b, None, None, _bar_a], start=5))
    score = build(tmp_path, hits,
                  meta={'pickup_beats': 1, 'source_leading_beats': 1,
                        'notation': {'repeats': 'simile', 'beam_eighths': 'half-bar'},
                        'sections': {1: 'Intro', 4: 'A', 7: 'Rest', 9: 'Chorus'}},
                  sigs=[(0, 1, 4), (1, 4, 4)], tempo=128, tempos=[(33, 150)])
    path, _root = _write_xml(score, tmp_path)
    validate_musicxml(score, path, Path(XSD))


def test_musixtex_sections_barlines_escaping_empty_tempo_and_dp(tmp_path):
    # 1. Inline \doublebar (no line break, no meter change) vs \Changecontext (meter change inline).
    s_inline = build(tmp_path, _sequence([_bar_a, _bar_b]), meta={'sections': {2: 'A'}}, **FOUR_FOUR)
    tex_inline = midi_to_musixtex.convert(s_inline, line_width=200.0)
    tex_inline.encode('ascii')
    assert r'\doublebar' in _score_body(tex_inline)

    s_meter = build(tmp_path, _bar_a(0) + [(4, KICK), (5, SNARE), (6, KICK)],
                    meta={'sections': {2: 'Bridge'}}, sigs=[(0, 4, 4), (4, 3, 4)])
    tex_meter = midi_to_musixtex.convert(s_meter, line_width=200.0)
    tex_meter.encode('ascii')
    body_meter = _score_body(tex_meter)
    assert '\\generalmeter{\\meterfrac{3}{4}}\n\\Changecontext' in body_meter or (
        r'\generalmeter{\meterfrac{3}{4}}' in body_meter and r'\Changecontext' in body_meter
    )

    # Pickup bar 0 followed by section on bar 1 must NOT emit a double barline after bar 0.
    s_pick = build(tmp_path, [(0, SNARE)] + _sequence([_bar_a, _bar_b], start=1),
                   meta={'pickup_beats': 1, 'source_leading_beats': 1, 'sections': {1: 'Intro'}},
                   sigs=[(0, 1, 4), (1, 4, 4)])
    body_pick = _score_body(midi_to_musixtex.convert(s_pick))
    assert r'\doublebar' not in body_pick and r'\setdoublebar' not in body_pick and r'\Changecontext' not in body_pick

    # 2. Line break at section emits \setdoublebar before \alaligne, and DP prefers starting a system at section.
    eleven = [h for i in range(11) for h in _bar_8th_variant(4 * i, i)]
    s_dp = build(tmp_path, eleven, meta={'sections': {4: 'Chorus'}}, **FOUR_FOUR)
    tex_dp = midi_to_musixtex.convert(s_dp)
    tex_dp.encode('ascii')
    sys_labels = [_system_bar_labels(s) for s in _systems_from_tex(tex_dp)]
    assert sys_labels[0] == ['1', '2', '3']
    assert sys_labels[1][0] == '4'
    assert re.search(r'\\setdoublebar%?\s*\\alaligne', _score_body(tex_dp))

    # 3. TeX special-character escaping in rehearsal marks (must remain 100% ASCII).
    s_esc = build(tmp_path, _sequence([_bar_a, _bar_b, _bar_a, _bar_b]),
                  meta={'sections': {1: 'A&B', 2: '100%', 3: 'B_2', 4: 'C#1$'}}, **FOUR_FOUR)
    tex_esc = midi_to_musixtex.convert(s_esc)
    tex_esc.encode('ascii')
    blocks_esc = _bar_blocks(tex_esc)
    b0, b1, b2, b3 = ('\n'.join(blocks_esc[i][1]) for i in range(4))
    assert r'A\&B' in b0
    assert r'100\%' in b1
    assert 'B_2' not in b2 and (r'B\_2' in b2 or r'\char95' in b2)
    assert r'C\#1\$' in b3

    # 4. Section works on single empty bar, multi-rest bar, and bar with tempo change.
    s_spec = build(tmp_path, _sequence([_bar_a, None, _bar_b, None, None, None, _bar_a]),
                   meta={'sections': {2: 'Solo', 4: 'RestSec', 7: 'Fast'}},
                   sigs=[(0, 4, 4)], tempo=120, tempos=[(24, 150)])
    tex_spec = midi_to_musixtex.convert(s_spec)
    tex_spec.encode('ascii')
    blocks_spec = _bar_blocks(tex_spec)
    by_hdr = {hdr: '\n'.join(lines) for hdr, lines in blocks_spec}
    solo_body = next(v for k, v in by_hdr.items() if re.match(r'^% bar 2\b', k))
    rest_body = next(v for k, v in by_hdr.items() if re.match(r'^% bar 4-6\b', k))
    fast_body = next(v for k, v in by_hdr.items() if re.match(r'^% bar 7\b', k))
    assert 'Solo' in solo_body and r'\centerpause' in solo_body
    assert 'RestSec' in rest_body and r'\centerHpause{3}' in rest_body
    assert 'Fast' in fast_body and r'\metron{\qu}{150}' in fast_body


@needs_pdf
def test_pdf_sections_and_half_bar_beams_end_to_end(tmp_path):
    seq = [_bar_a, _bar_a, _bar_a, _bar_b, _bar_b, _bar_a, _bar_b, _bar_a, None, None, None, _bar_a, _bar_a]
    score = build(tmp_path, _sequence(seq),
                  meta={'title': 'Phase 2 PDF Check',
                        'notation': {'repeats': 'simile', 'beam_eighths': 'half-bar'},
                        'sections': {1: 'Intro', 5: 'A&B_2', 9: 'Rest100%', 12: 'Chorus'}},
                  sigs=[(0, 4, 4)], tempo=128, tempos=[(44, 152)])
    out = tmp_path / 'score.pdf'
    work = tmp_path / 'work'
    work.mkdir()
    info = render_score.render(score, out, work)
    assert info['pages'] >= 1
    # validate_pdf confirms rehearsal boxes are vector-outlined with zero leaked staff text.
    assert validate_pdf(score, out).startswith('PDF OK')
    log = (work / 'score.log').read_text(errors='replace')
    overfull = [float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
    assert not overfull or max(overfull) <= 4.0


@needs_pdf
def test_pdf_cli_beam_eighths_flag(tmp_path):
    midi = make_midi(tmp_path / 'e8.mid', _sequence([_bar_a, _bar_b]), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: PDF Beam CLI\n', encoding='utf-8')
    out = tmp_path / 'score.pdf'
    work = tmp_path / 'work'
    assert render_score.main([str(midi), '--metadata', str(meta), '--out', str(out),
                              '--work-dir', str(work), '--beam-eighths', 'half-bar']) == 0
    tex = (work / 'score.tex').read_text(encoding='ascii')
    assert _bar_blocks(tex)[0][1]
    assert '\n'.join(_bar_blocks(tex)[0][1]).count(r'\ibu0{') == 2
    score_hb = score_core.build_score(midi, meta, cli={'beam_eighths': 'half-bar'})
    assert validate_pdf(score_hb, out).startswith('PDF OK')
