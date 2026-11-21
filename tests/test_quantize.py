import random

import pytest

from conftest import HH, HHO, KICK, RIDE, SNARE, TOM, build, events_at
from score_core import R, ScoreError, tuplet_number, tuplet_ratio

FOUR_FOUR = {'sigs': [(0, 4, 4)]}


def all_events(score):
    """absolute R tick → sorted notes."""
    return {bar.start + t: sorted(h) for bar in score.bars for t, h in bar.events.items()}


def test_humanized_tpq480_lands_on_grid(tmp_path):
    rng = random.Random(1234)
    grid = []
    for bar in range(4):
        for step in range(16):
            beat = bar * 4 + step / 4
            grid.append((beat, HH))
            if step % 8 == 0:
                grid.append((beat, KICK))
            if step % 8 == 4:
                grid.append((beat, SNARE))
    jitter = 19 / 480  # just under 1/24 beat
    hits = [(max(0.0, b + rng.uniform(-jitter, jitter)), n, rng.randint(60, 110)) for b, n in grid]
    hits[0] = (0.0, hits[0][1], hits[0][2])
    hits.append((4 * 3 + 3.75 + jitter, HHO))  # open HH pushed late by almost the full tolerance
    score = build(tmp_path, hits, tpq=480, **FOUR_FOUR)
    expected = {}
    for b, n in grid + [(15.75, HHO)]:
        expected.setdefault(int(round(b * R)), []).append(n)
    assert all_events(score) == {t: sorted(ns) for t, ns in expected.items()}
    assert score.grace_hits == 0 and score.duplicate_hits == 0
    assert not any('不齐' in w for w in score.warnings)
    assert len(score.bars) == 4


def test_humanized_triplets_land_on_triplet_grid(tmp_path):
    hits = [(0, RIDE), (1 / 3 + 0.03, RIDE), (2 / 3 - 0.03, RIDE), (1, RIDE)]
    score = build(tmp_path, hits, tpq=480, **FOUR_FOUR)
    assert sorted(score.bars[0].events) == [0, 16, 32, 48]
    assert score.bars[0].triplet_beats == {0: 6}


@pytest.mark.parametrize('tpq', [96, 480, 960])
def test_eighth_note_triplets(tmp_path, tpq):
    hits = [(1 + i / 3, RIDE) for i in range(3)] + [(0, KICK), (2, KICK)]
    score = build(tmp_path, hits, tpq=tpq, **FOUR_FOUR)
    bar = score.bars[0]
    assert bar.triplet_beats == {1: 6}
    assert sorted(bar.events) == [0, 48, 64, 80, 96]
    assert tuplet_ratio(bar, 1) == (3, 2) and tuplet_number(bar, 1) == 3
    assert score.triplet_beat_count == 1


def test_sixteenth_sextuplets(tmp_path):
    hits = [(i / 6, SNARE) for i in range(6)] + [(1 + i / 6, TOM) for i in range(6)]
    score = build(tmp_path, hits, **FOUR_FOUR)
    bar = score.bars[0]
    assert bar.triplet_beats == {0: 6, 1: 6}
    assert sorted(bar.events) == [i * 8 for i in range(12)]
    assert tuplet_ratio(bar, 0) == (6, 4) and tuplet_number(bar, 0) == 6
    assert score.triplet_beat_count == 2


def test_triplets_with_eighth_grid(tmp_path):
    hits = [(i / 3, RIDE) for i in range(3)]
    score = build(tmp_path, hits, {'quantize': {'subdivision': 2}}, **FOUR_FOUR)
    assert score.bars[0].triplet_beats == {0: 3}
    assert tuplet_ratio(score.bars[0], 0) == (3, 2)


def test_32nd_note_run_alternating_pitches_raises(tmp_path):
    hits = [(0, KICK)] + [(5 + i / 8, SNARE if i % 2 else TOM) for i in range(8)]
    with pytest.raises(ScoreError, match='32 分音符') as exc:
        build(tmp_path, hits, **FOUR_FOUR)
    assert '第 6 拍' in str(exc.value)


def test_32nd_note_run_single_pitch_raises(tmp_path):
    hits = [(i / 8, SNARE) for i in range(8)]
    with pytest.raises(ScoreError):
        score = build(tmp_path, hits, **FOUR_FOUR)
        assert score.engraved_hits == 8  # anything else is lost notes


def test_isolated_32nd_offbeat_is_not_a_sextuplet(tmp_path):
    hits = [(0, KICK), (0.125, SNARE)]
    try:
        score = build(tmp_path, hits, **FOUR_FOUR)
    except ScoreError:
        return
    assert score.bars[0].triplet_beats == {}


def test_quintuplets_raise(tmp_path):
    hits = [(i / 5, SNARE if i % 2 else HH) for i in range(5)]
    with pytest.raises(ScoreError, match='五连音'):
        build(tmp_path, hits, **FOUR_FOUR)


def test_unquantized_performance_raises(tmp_path):
    hits = [(0, KICK), (0.1, SNARE), (0.42, HH)]
    with pytest.raises(ScoreError, match='未量化'):
        build(tmp_path, hits, **FOUR_FOUR)


def test_tuplets_off_with_triplets_raises(tmp_path):
    with pytest.raises(ScoreError, match='tuplets: off'):
        build(tmp_path, [(i / 3, RIDE) for i in range(3)], {'quantize': {'tuplets': 'off'}}, **FOUR_FOUR)


def test_tuplets_off_with_sextuplets_raises(tmp_path):
    with pytest.raises(ScoreError):
        build(tmp_path, [(i / 6, SNARE) for i in range(6)], {'quantize': {'tuplets': 'off'}}, **FOUR_FOUR)


def test_tuplets_off_far_off_grid_raises_with_hint(tmp_path):
    # 1/6 and 5/6 are 1/12 from the 16th grid as well, but 1/2 - 1/12 is not: use a quintuplet-ish point.
    with pytest.raises(ScoreError, match='tuplets: off'):
        build(tmp_path, [(0, SNARE), (0.4, HH)], {'quantize': {'tuplets': 'off'}}, **FOUR_FOUR)


def test_subdivision_2_with_sixteenths_raises(tmp_path):
    with pytest.raises(ScoreError, match='8 分'):
        build(tmp_path, [(i / 4, HH) for i in range(4)], {'quantize': {'subdivision': 2}}, **FOUR_FOUR)


@pytest.mark.parametrize('offset', [0.25, 0.75])
def test_subdivision_2_with_single_sixteenth_raises(tmp_path, offset):
    with pytest.raises(ScoreError, match='8 分'):
        build(tmp_path, [(0, KICK), (offset, HH)], {'quantize': {'subdivision': 2}}, **FOUR_FOUR)


def test_subdivision_2_accepts_eighths(tmp_path):
    score = build(tmp_path, [(i / 2, HH) for i in range(8)], {'quantize': {'subdivision': 2}}, **FOUR_FOUR)
    assert sorted(score.bars[0].events) == [i * 24 for i in range(8)]


@pytest.mark.parametrize('value', [3, 8])
def test_bad_subdivision(tmp_path, value):
    with pytest.raises(ScoreError, match='subdivision'):
        build(tmp_path, [(0, HH)], {'quantize': {'subdivision': value}})


@pytest.mark.parametrize('meta', [{'quantize': {'subdivision': 'x'}}, {'tempo_bpm': 'fast'}])
def test_non_numeric_metadata_is_score_error(tmp_path, meta):
    with pytest.raises(ScoreError):
        build(tmp_path, [(0, HH)], meta)


def test_flam_main_on_grid(tmp_path):
    hits = [(0, KICK), (1 - 50 / 480, SNARE, 40), (1, SNARE, 110)]
    score = build(tmp_path, hits, tpq=480, **FOUR_FOUR)
    bar = score.bars[0]
    assert events_at(bar) == {0: [KICK], 48: [SNARE]}
    hit = bar.events[48][SNARE]
    assert hit.grace and hit.velocity == 110
    assert score.grace_hits == 1 and score.engraved_hits == 2 and score.duplicate_hits == 0


def test_flam_grace_on_grid(tmp_path):
    # DAW put the grace on the grid; the accented stroke follows 50 ticks later.
    hits = [(0, KICK), (1, SNARE, 40), (1 + 50 / 480, SNARE, 110)]
    score = build(tmp_path, hits, tpq=480, **FOUR_FOUR)
    bar = score.bars[0]
    assert events_at(bar) == {0: [KICK], 48: [SNARE]}
    assert bar.events[48][SNARE].grace
    assert score.grace_hits == 1


def test_flam_at_window_edge(tmp_path):
    hits = [(1 - 60 / 480, SNARE, 40), (1, SNARE, 110), (0, KICK)]
    score = build(tmp_path, hits, tpq=480, **FOUR_FOUR)
    assert score.grace_hits == 1
    assert score.bars[0].events[48][SNARE].grace


def test_flam_window_configurable(tmp_path):
    hits = [(0, KICK), (1 - 50 / 480, SNARE, 40), (1, SNARE, 110)]
    with pytest.raises(ScoreError):
        # with no flam window the weak hit is its own (unquantizable) note
        build(tmp_path, hits, {'quantize': {'flam_window': 0}}, tpq=480, **FOUR_FOUR)


def test_sixteenths_same_pitch_are_not_flams(tmp_path):
    hits = [(i / 4, SNARE, 40 if i % 2 else 110) for i in range(8)]
    score = build(tmp_path, hits, **FOUR_FOUR)
    assert score.grace_hits == 0 and score.engraved_hits == 8


def test_exact_duplicates_merged_and_counted(tmp_path):
    hits = [(0, KICK), (0, KICK), (1, SNARE, 70), (1, SNARE, 100), (2, HH)]
    score = build(tmp_path, hits, **FOUR_FOUR)
    assert score.source_hits == 5
    assert score.engraved_hits == 3
    assert score.duplicate_hits == 2
    assert score.grace_hits == 0
    assert score.bars[0].events[48][SNARE].velocity == 100
    assert any('重复' in w for w in score.warnings)


def test_two_strokes_snapping_to_one_cell_raise(tmp_path):
    # two hits 70 ticks apart (outside the flam window, 1/7 beat) cannot both be notated
    hits = [(1 - 35 / 480, HH, 80), (1 + 35 / 480, HH, 90)]
    with pytest.raises(ScoreError, match='无法准确记谱|同一位置'):
        build(tmp_path, hits, {'quantize': {'flam_window': '1/16'}}, tpq=480, **FOUR_FOUR)


def test_near_simultaneous_retrigger_is_merged(tmp_path):
    # the same pad triggered twice within 1/48 beat is one stroke
    hits = [(1, HH, 80), (1 + 5 / 480, HH, 90)]
    score = build(tmp_path, hits, tpq=480, **FOUR_FOUR)
    assert score.engraved_hits == 1
    assert score.duplicate_hits == 1


def test_ghost_and_accent_dynamics(tmp_path):
    hits = [(0, SNARE, 30), (1, SNARE, 80), (2, SNARE, 120), (3, KICK, 20)]
    score = build(tmp_path, hits, {'dynamics': {'ghost_below': 40, 'accent_above': 110}}, **FOUR_FOUR)
    ev = score.bars[0].events
    assert ev[0][SNARE].ghost and not ev[0][SNARE].accent
    assert not ev[48][SNARE].ghost and not ev[48][SNARE].accent
    assert ev[96][SNARE].accent
    assert not ev[144][KICK].ghost  # feet never get ghost parentheses
