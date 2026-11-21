"""Regression tests for the bugs found in the 2026-11 adversarial review (V1–V30).

Each test names the review item it pins.  Synthetic MIDI only; two short PDF builds.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from fractions import Fraction

import pytest
import yaml

from conftest import HAVE_PDF_TOOLS, HH, KICK, RIDE, SNARE, build, make_midi
import midi_to_musicxml
import midi_to_musixtex
import render_score
import validate_score
from score_core import R, ScoreError, voice_items, voice_tuplets
from validate_score import ValidationError

FOUR = {'sigs': [(0, 4, 4)]}
PEDAL = 44


# --- V1: same-pitch strokes are not chained into one cluster -----------------------------

def test_v1_single_pitch_32nd_run_is_not_swallowed(tmp_path):
    with pytest.raises(ScoreError):
        build(tmp_path, [(i / 8, SNARE) for i in range(8)], **FOUR)


def test_v1_drag_after_main_stroke_is_not_dropped(tmp_path):
    # loud stroke then a soft one 1/8 beat later: a 32nd figure, not a duplicate
    with pytest.raises(ScoreError):
        build(tmp_path, [(1, SNARE, 110), (1.125, SNARE, 50)], **FOUR)


def test_v1_equal_velocity_pair_does_not_move_the_on_beat_stroke(tmp_path):
    with pytest.raises(ScoreError):
        build(tmp_path, [(1, SNARE), (1.125, SNARE)], **FOUR)


def test_v1_rising_run_is_not_three_graces(tmp_path):
    with pytest.raises(ScoreError):
        build(tmp_path, [(1 + i / 32, SNARE, 40 + 10 * i) for i in range(4)], tpq=480, **FOUR)


# --- V2: a flam's grace position never leaves the main stroke's beat ----------------------

def test_v2_flam_stays_on_the_beat(tmp_path):
    hits = [(0, KICK), (Fraction(1, 3), HH), (0.84, SNARE, 40), (0.965, SNARE, 110), (Fraction(4, 3), HH), (2, KICK)]
    score = build(tmp_path, hits, tpq=960, **FOUR)
    snare = [(t, h[SNARE].grace) for t, h in score.bars[0].events.items() if SNARE in h]
    assert snare == [(R, True)]


def test_v2_flam_without_triplet_neighbour_builds(tmp_path):
    hits = [(0, KICK), (0.84, SNARE, 40), (0.965, SNARE, 110), (2, KICK)]
    score = build(tmp_path, hits, tpq=960, **FOUR)
    midi_to_musicxml.convert(score)  # used to crash with an internal rest error
    assert R in score.bars[0].events


# --- V5/V6: strict grids, no silent re-timing ----------------------------------------------

def test_v5_isolated_32nd_is_not_a_sextuplet(tmp_path):
    with pytest.raises(ScoreError):
        build(tmp_path, [(0, KICK), (0.125, SNARE)], **FOUR)


def test_v5_dotted_16th_offset_is_rejected(tmp_path):
    with pytest.raises(ScoreError):
        build(tmp_path, [(0, HH), (0.375, SNARE)], **FOUR)


def test_v6_tuplets_off_names_the_setting(tmp_path):
    with pytest.raises(ScoreError, match='tuplets: off'):
        build(tmp_path, [(i / 3, RIDE) for i in range(3)], {'quantize': {'tuplets': 'off'}}, **FOUR)


# --- per-voice grids: hand sextuplets over straight feet ----------------------------------

def test_polyrhythm_hand_sextuplet_over_pedal_sixteenths(tmp_path):
    hits = [(i / 6, SNARE) for i in range(6)] + [(i / 4, PEDAL) for i in range(4)] + [(2, KICK)]
    score = build(tmp_path, hits, **FOUR)
    bar = score.bars[0]
    assert voice_tuplets(bar, 'hand') == {0: 6}
    assert voice_tuplets(bar, 'foot') == {}
    foot = [it for it in voice_items(bar, 'foot') if not it.is_rest]
    assert [(it.start, it.duration, it.tuplet) for it in foot[:4]] == [(0, 12, None), (12, 12, None),
                                                                     (24, 12, None), (36, 12, None)]
    root, _ = midi_to_musicxml.convert(score)
    validate_score.compare_with_model(score, root)
    assert r'\def\txt{6}' in midi_to_musixtex.convert(score)


# --- V7: track names in UTF-8 -------------------------------------------------------------

def test_v7_japanese_track_name_selects_drums(tmp_path):
    tracks = [{'hits': [(0, 60)], 'channel': 1, 'name': 'ピアノ'},
              {'hits': [(0, KICK), (1, SNARE)], 'channel': 2, 'name': 'ドラム'}]
    score = build(tmp_path, None, tracks=tracks, charset='utf-8', **FOUR)
    assert score.engraved_hits == 2


# --- V8/V9/V18/V19: tempo and meter maps ----------------------------------------------------

def test_v8_tempo_in_force_after_trimmed_lead_in(tmp_path):
    score = build(tmp_path, [(4, KICK), (5, SNARE)], {'source_leading_beats': 4},
                  tempo=100, tempos=[(2, 160)], **FOUR)
    assert score.tempo_bpm == 160


def test_v9_mid_bar_tempo_change_is_reported(tmp_path):
    score = build(tmp_path, [(0, KICK), (4, KICK), (8, KICK)], tempo=120, tempos=[(6, 160)], **FOUR)
    assert score.bars[1].tempo == 160
    assert any('中途的速度变化' in w for w in score.warnings)


def test_v18_late_first_time_signature_keeps_4_4_before_it(tmp_path):
    score = build(tmp_path, [(0, KICK), (8, KICK), (11, KICK)], sigs=[(8, 3, 4)])
    assert [b.beats for b in score.bars] == [4, 4, 3, 3]
    assert any('之前的部分按 4/4' in w for w in score.warnings)


def test_v19_last_event_at_same_tick_wins(tmp_path):
    score = build(tmp_path, [(0, KICK), (3, SNARE)], tempo=150, tempos=[(0, 90)], sigs=[(0, 4, 4), (0, 3, 4)])
    assert score.tempo_bpm == 90
    assert score.bars[0].beats == 3


# --- V10/V20: pickups ---------------------------------------------------------------------

def test_v10_long_silent_pickup_in_6_4(tmp_path):
    score = build(tmp_path, [(5, KICK), (6, SNARE)], {'pickup_beats': 5, 'source_leading_beats': 5},
                  sigs=[(0, 6, 4)])
    root, _ = midi_to_musicxml.convert(score)
    validate_score.compare_with_model(score, root)
    assert sum(it.duration for it in voice_items(score.bars[0], 'hand')) == 5 * R


def test_v20_pickup_longer_than_bar_is_rejected(tmp_path):
    with pytest.raises(ScoreError, match='弱起'):
        build(tmp_path, [(6, KICK)], {'pickup_beats': 6, 'source_leading_beats': 6}, **FOUR)


# --- V12: overlapping heads are reported ------------------------------------------------------

def test_v12_simultaneous_snares_are_reported(tmp_path):
    score = build(tmp_path, [(0, 38), (0, 40), (1, KICK)], **FOUR)
    assert any('同一位置' in w and '无法区分' in w for w in score.warnings)


# --- V16/V17/V22/V24: engraving details -------------------------------------------------------

def test_v16_triangle_and_solid_diamond_symbols(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(0, 56), (1, 82), (2, KICK)], **FOUR))
    assert r'\tl@symbol' in tex and r'\y@symbol' in tex and r'\r@symbol' not in tex


def test_v17_one_accent_per_chord(tmp_path):
    hits = [(0, SNARE, 120), (0, 49, 120), (1, KICK)]
    tex = midi_to_musixtex.convert(build(tmp_path, hits, {'dynamics': {'accent_above': 110}}, **FOUR))
    body = tex.split('% bar 1', 1)[1].split('\\bar', 1)[0]
    assert body.count(r'\usf') + body.count(r'\busf') == 1


def test_v22_rest_inside_tuplet_printed_for_its_voice(tmp_path):
    hits = [(2, KICK)] + [(2 + Fraction(k, 6), SNARE) for k in (1, 2, 4)]
    tex = midi_to_musixtex.convert(build(tmp_path, hits, **FOUR))
    assert r'\zcharnote{i}{\musixchar64}' in tex  # hand 16th rest, raised


def test_v24_piece_ends_with_final_double_bar(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(0, KICK), (4, KICK)], **FOUR))
    assert tex.rstrip().endswith('\\setdoubleBAR\\endpiece\n\\bye'.strip())


# --- V25/V26: CLI and validator ---------------------------------------------------------------

@pytest.mark.parametrize('meta', [{'tempo_bpm': 'fast'}, {'quantize': {'subdivision': 'x'}},
                                  {'dynamics': {'ghost_below': 'abc'}}, {'dynamics': [1]}])
def test_v25_bad_metadata_values_are_score_errors(tmp_path, meta):
    with pytest.raises(ScoreError):
        build(tmp_path, [(0, KICK)], meta, **FOUR)


def test_v25_validate_requires_a_target(tmp_path, capsys):
    midi = make_midi(tmp_path / 'a.mid', [(0, KICK)], **FOUR)
    meta = tmp_path / 'm.yaml'
    meta.write_text('title: t\n', encoding='utf-8')
    with pytest.raises(SystemExit):
        validate_score.main([str(midi), '--metadata', str(meta)])


def test_v25_missing_xsd_is_an_error(tmp_path):
    with pytest.raises(validate_score.SetupError, match='XSD'):
        validate_score.check_xsd(tmp_path / 'nope.xsd')


def test_v26_validator_catches_tampering(tmp_path):
    hits = [(0, SNARE, 40), (0.03, SNARE, 110), (1, 56), (2, KICK)]
    score = build(tmp_path, hits, tpq=480, **FOUR)
    path = tmp_path / 's.musicxml'
    midi_to_musicxml.write(score, path)
    validate_score.validate_musicxml(score, path)
    tree = ET.parse(path)
    for head in tree.iter('notehead'):
        if head.text == 'triangle':
            head.text = 'normal'
    tree.write(path, encoding='utf-8', xml_declaration=True)
    with pytest.raises(ValidationError, match='重新转换'):
        validate_score.validate_musicxml(score, path)


def test_v28_failed_build_keeps_previous_outputs(tmp_path):
    import build_score
    midi = make_midi(tmp_path / 'a.mid', [(0, KICK), (1, SNARE)], **FOUR)
    meta = tmp_path / 'm.yaml'
    meta.write_text('title: t\n', encoding='utf-8')
    out = tmp_path / 'out'
    out.mkdir()
    (out / 'score.musicxml').write_text('previous', encoding='utf-8')
    code = build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out), '--no-pdf',
                             '--xsd', str(tmp_path / 'missing.xsd')])
    assert code == 2  # setup error, not a validation mismatch
    assert (out / 'score.musicxml').read_text(encoding='utf-8') == 'previous'
    assert not list(out.glob('.score.*'))


# --- V29/V30: MusicXML credits and TeX escaping ------------------------------------------------

def test_v29_credits_use_the_right_fields(tmp_path):
    score = build(tmp_path, [(0, KICK)], {'artist': 'Band', 'composer': 'Comp', 'transcriber': 'Tr'}, **FOUR)
    root, _ = midi_to_musicxml.convert(score)
    credits = {c.findtext('credit-type'): c.findtext('credit-words') for c in root.findall('credit')}
    assert credits['composer'] == 'Comp' and credits['subtitle'] == 'Band' and credits['arranger'] == 'Tr'
    assert root.findtext('movement-title') == 'Test'  # what MuseScore 3 shows as the title


# --- V3/V4/V13/V27: header text through the real PDF pipeline ----------------------------------

pdf_only = pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs the TeX/Ghostscript toolchain')


@pdf_only
def test_v3_v4_quotes_dashes_ligatures_and_long_footer(tmp_path):
    meta = {'title': "Don't Stop -- Me ``Now'' office file", 'artist': "B'z",
            'copyright': '© ' + '長い著作権表示 ' * 30}
    score = build(tmp_path, [(0, KICK), (1, SNARE)], meta, **FOUR)
    out = tmp_path / 'score.pdf'
    (tmp_path / 'work').mkdir()
    render_score.render(score, out, tmp_path / 'work')
    validate_score.validate_pdf(score, out)  # exact text via ActualText and via ToUnicode only


@pdf_only
@pytest.mark.parametrize('title, message', [('Emoji 🥁', '方框'), ('〜 と ～', '同一个字形')])
def test_v13_v27_unprintable_or_ambiguous_text_fails_clearly(tmp_path, title, message):
    score = build(tmp_path, [(0, KICK)], {'title': title}, **FOUR)
    (tmp_path / 'work').mkdir()
    with pytest.raises(RuntimeError, match=message):
        render_score.render(score, tmp_path / 'score.pdf', tmp_path / 'work')


# --- final verification: seconds, merged last system, CJK spacing -------------------------------

def test_second_in_a_chord_puts_one_head_across_the_stem(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(0, 49), (0, HH), (1, KICK)], **FOUR))
    assert r'\do@symbol\@rq{o}' in tex  # crash beside the hi-hat, on the other side of the stem


def test_hand_and_foot_a_second_apart_are_offset(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(0, KICK), (0, 41), (2, KICK)], **FOUR))
    assert r'\roffset{1}{' in tex


def test_short_piece_merges_lonely_last_system(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(b * 4, KICK) for b in range(5)], **FOUR))
    assert tex.count(r'\alaligne') <= 1


def test_unknown_midi_subkey_is_rejected(tmp_path):
    with pytest.raises(ScoreError, match='midi'):
        build(tmp_path, [(0, KICK)], {'midi': {'track': ['x']}}, **FOUR)


def test_unmapped_note_message_names_the_note(tmp_path):
    with pytest.raises(ScoreError, match=r'note_map: \{90: '):
        build(tmp_path, [(0, KICK), (1, 90)], **FOUR)


@pdf_only
def test_cjk_latin_text_copies_without_invented_spaces(tmp_path):
    import shutil
    import subprocess
    if not shutil.which('pdftotext'):
        pytest.skip('needs pdftotext')
    score = build(tmp_path, [(0, KICK)], {'title': '夜行列車・2号 Live版 テスト'}, **FOUR)
    (tmp_path / 'work').mkdir()
    out = tmp_path / 'score.pdf'
    render_score.render(score, out, tmp_path / 'work')
    text = subprocess.run(['pdftotext', '-l', '1', str(out), '-'], capture_output=True, text=True).stdout
    assert text.splitlines()[0] == '夜行列車・2号 Live版 テスト'


def test_cross_head_stems_start_at_arm_tip(tmp_path):
    """User report: the stem of an x notehead went down to the centre of the X instead of
    meeting the arm tip.  Cross heads (x, circle-x) use the \\@x… stem routines."""
    hits = [(0, HH), (1, HH), (1.5, HH), (3.5, HH), (0, PEDAL), (2, 52), (4, SNARE)]
    tex = midi_to_musixtex.convert(build(tmp_path, hits, **FOUR))
    assert r'\do@symbol\@xqu{n}' in tex          # unbeamed quarter, stem up
    assert r'\do@symbol\@xqb0{n}' in tex         # beamed
    assert r'\do@symbol\@xcu{n}' in tex          # flagged 8th
    assert r'\do@symbol\@xql{d}' in tex          # pedal hi-hat, stem down
    assert r'\dc@symbol\@xqu{q}' in tex          # china (circle-x)
    assert r'\q@symbol\@qu{j}' in tex            # normal heads keep the centre stem


# --- final panel: unbeamed tuplets, moved-head ornaments, subtitle, bad XSD -----------------------

def test_shuffle_tuplet_with_rest_gets_a_number(tmp_path):
    hits = [(b, HH) for b in range(4)] + [(b + Fraction(2, 3), HH) for b in range(4)] + [(0, KICK)]
    score = build(tmp_path, hits, **FOUR)
    hand = voice_items(score.bars[0], 'hand')
    assert all(it.tuplet_bracket for it in hand if it.tuplet)
    tex = midi_to_musixtex.convert(score)
    assert tex.count(r'{\eightit 3}') == 4
    root, _ = midi_to_musicxml.convert(score)
    assert {t.get('bracket') for t in root.iter('tuplet') if t.get('type') == 'start'} == {'yes'}


def test_beam_text_follows_beam_start(tmp_path):
    hits = [(Fraction(1, 3), SNARE), (Fraction(2, 3), SNARE), (Fraction(4, 3), SNARE), (Fraction(5, 3), SNARE),
            (1, SNARE), (0, KICK)]
    tex = midi_to_musixtex.convert(build(tmp_path, hits, **FOUR))
    assert r'\butext0\ibu' not in tex


def test_ornaments_follow_a_moved_head(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(0, RIDE), (0, 46), (2, KICK)], **FOUR))
    assert r'\roffset{1}{\ccharnote{q}{$\circ$}}' in tex


def test_subtitle_is_work_number_for_musescore(tmp_path):
    root, _ = midi_to_musicxml.convert(build(tmp_path, [(0, KICK)], {'subtitle': 'Demo'}, **FOUR))
    assert root.findtext('work/work-number') == 'Demo' and root.findtext('work/work-title') == 'Test'


def test_malformed_xsd_is_a_setup_error(tmp_path):
    bad = tmp_path / 'bad.xsd'
    bad.write_text('not xml', encoding='utf-8')
    with pytest.raises(validate_score.SetupError):
        validate_score.check_xsd(bad)


def test_drag_prints_two_beamed_grace_notes(tmp_path):
    hits = [(0.9, SNARE, 40), (0.95, SNARE, 50), (1, SNARE, 100), (2.95, SNARE, 40), (3, SNARE, 100), (0, KICK)]
    score = build(tmp_path, hits, tpq=480, **FOUR)
    assert [h[SNARE].grace for t, h in sorted(score.bars[0].events.items()) if SNARE in h] == [2, 1]
    root, _ = midi_to_musicxml.convert(score)
    graces = [n for n in root.iter('note') if n.find('grace') is not None]
    assert len(graces) == 3
    assert [b.text for b in graces[0].findall('beam')] == ['begin', 'begin'] and graces[0].find('grace').get('slash') is None
    assert graces[2].find('grace').get('slash') == 'yes'  # the flam
    tex = midi_to_musixtex.convert(score)
    assert r'\tinynotesize\ibbu2{j}0' in tex and r'\@tqh2{j}' in tex


# --- every voice fills every beat with its own rests (user request) -------------------------------

def test_each_voice_prints_its_rests(tmp_path):
    # hands play quarters, feet play kick on 1& and 3,3&: foot rests must be printed
    hits = [(b, HH) for b in range(4)] + [(1, SNARE), (3, SNARE), (0.5, KICK), (2, KICK), (2.5, KICK)]
    tex = midi_to_musixtex.convert(build(tmp_path, hits, **FOUR))
    bar = tex.split('% bar 1', 1)[1]
    assert bar.count(r'\zcharnote{a}{\musixchar63}') == 1   # foot 8th rest on beat 1
    assert bar.count(r'\zcharnote{a}{\musixchar62}') == 2   # foot quarter rests on beats 2 and 4


def test_shared_rest_when_both_voices_rest(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(0, 49), (0, KICK), (2, HH), (2, KICK)], **FOUR))
    bar = tex.split('% bar 1', 1)[1]
    assert r'\qp' in bar and 'musixchar62' not in bar  # one centred quarter rest, not two


def test_silent_voice_gets_a_whole_rest_mid_bar(tmp_path):
    tex = midi_to_musixtex.convert(build(tmp_path, [(i / 2, HH) for i in range(8)], **FOUR))
    bar = tex.split('% bar 1', 1)[1]
    groups = [g for g in bar.split('\n') if g.startswith('\\vnotes')]
    index = next(i for i, g in enumerate(groups) if r'\zcharnote{g}{\musixchar61}' in g)
    assert 2 <= index <= 5


def test_legend_is_off_by_default_and_switchable(tmp_path):
    score = build(tmp_path, [(0, KICK)], **FOUR)
    assert '凡例' not in render_score.expected_page_text(score, 1)[0]
    score.metadata['legend'] = True
    assert '凡例' in render_score.expected_page_text(score, 1)[0]
