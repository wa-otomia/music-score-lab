import random
from fractions import Fraction

import pytest
from score_core import ScoreError

from conftest import HH, KICK, RIDE, SNARE, TOM, build
from score_core import R, beam_level, note_type, voice_hits, voice_items

FOUR_FOUR = {'sigs': [(0, 4, 4)]}
PEDAL = 44


def check_voice(bar, part):
    items = voice_items(bar, part)
    where = f'bar {bar.number} {part}'
    assert sum(it.duration for it in items) == bar.length, where
    cursor = 0
    for it in items:
        assert it.start == cursor, where
        cursor += it.duration
        note_type(it)  # every duration must be engravable
        if it.is_rest and not it.measure_rest:
            end = it.start + it.duration
            same_beat = it.start // R == (end - 1) // R
            whole_beats = it.start % R == 0 and it.duration % R == 0
            assert same_beat or whole_beats, f'{where}: rest {it.start}+{it.duration} crosses a beat'
        if not it.is_rest:
            assert it.start // R == (it.start + it.duration - 1) // R, f'{where}: note crosses a beat'
    onsets = sorted(voice_hits(bar, part))
    assert [it.start for it in items if not it.is_rest] == onsets, where
    return items


def test_repo_song_voices_add_up(song):
    for bar in song.bars:
        for part in ('hand', 'foot'):
            check_voice(bar, part)


def random_rhythm(seed, bars=24):
    rng = random.Random(seed)
    hits = []
    grids = {'straight': [Fraction(i, 4) for i in range(4)], 'eighths': [Fraction(i, 2) for i in range(2)],
             'triplet': [Fraction(i, 3) for i in range(3)], 'sext': [Fraction(i, 6) for i in range(6)]}
    for beat in range(bars * 4):
        grid = grids[rng.choice(list(grids))]
        for note in (HH, SNARE, KICK, PEDAL):
            if rng.random() < 0.45:
                for pos in grid:
                    if rng.random() < 0.5:
                        hits.append((beat + pos, note))
    hits.append((0, KICK))
    return hits


@pytest.mark.parametrize('seed', [1, 2, 3])
def test_synthetic_rhythms_add_up(tmp_path, seed):
    score = build(tmp_path, random_rhythm(seed), **FOUR_FOUR)
    assert score.triplet_beat_count > 0
    for bar in score.bars:
        for part in ('hand', 'foot'):
            check_voice(bar, part)


def test_pickup_must_be_shorter_than_first_bar(tmp_path):
    with pytest.raises(ScoreError, match='弱起'):
        build(tmp_path, [(0.75, SNARE), (2, KICK)], {'pickup_beats': 1, 'source_leading_beats': 1},
              sigs=[(0, 1, 4), (1, 1, 4)])


@pytest.mark.parametrize('beats', [2, 3, 5, 7])
def test_odd_meters_and_pickups_add_up(tmp_path, beats):
    hits = [(0.75, SNARE), (beats + 1.5, KICK), (beats + 2, HH), (2 * beats - 0.25, HH)]
    score = build(tmp_path, hits, {'pickup_beats': 1, 'source_leading_beats': 1},
                  sigs=[(0, 1, 4), (1, beats, 4)])
    for bar in score.bars:
        for part in ('hand', 'foot'):
            check_voice(bar, part)


def test_empty_bar_is_measure_rest(tmp_path):
    score = build(tmp_path, [(0, KICK), (8, KICK)], **FOUR_FOUR)
    items = voice_items(score.bars[1], 'hand')
    assert len(items) == 1 and items[0].measure_rest and items[0].duration == 4 * R
    assert note_type(items[0]) == ('whole', 0)


def test_rest_grouping_in_four_four(tmp_path):
    score = build(tmp_path, [(3, SNARE), (0, KICK)], **FOUR_FOUR)
    items = voice_items(score.bars[0], 'hand')
    assert [(it.start, it.duration, it.is_rest) for it in items] == [(0, 2 * R, True), (2 * R, R, True),
                                                                     (3 * R, R, False)]


def test_offbeat_rests(tmp_path):
    score = build(tmp_path, [(0.75, SNARE), (1.5, SNARE), (0, KICK)], **FOUR_FOUR)
    items = voice_items(score.bars[0], 'hand')
    assert [(it.start, it.duration, it.is_rest) for it in items][:4] == [
        (0, 36, True), (36, 12, False), (48, 24, True), (72, 24, False)]
    assert note_type(items[0]) == ('eighth', 1)


def test_quarter_inside_triplet_beat(tmp_path):
    hits = [(i / 3, RIDE) for i in range(3)] + [(0, KICK)]
    score = build(tmp_path, hits, **FOUR_FOUR)
    bar = score.bars[0]
    assert bar.triplet_beats == {0: 6}
    foot = voice_items(bar, 'foot')
    assert (foot[0].start, foot[0].duration, foot[0].tuplet) == (0, R, None)
    assert note_type(foot[0]) == ('quarter', 0)
    assert foot[0].tuplet_edge is None and not foot[0].beams
    hand = voice_items(bar, 'hand')
    assert [(it.duration, it.tuplet) for it in hand[:3]] == [(16, 3)] * 3  # 8th triplets print '3'


def test_triplet_rest_inside_triplet_beat(tmp_path):
    hits = [(1 / 3, RIDE), (2 / 3, RIDE), (0, KICK)]
    score = build(tmp_path, hits, **FOUR_FOUR)
    hand = voice_items(score.bars[0], 'hand')
    assert [(it.start, it.duration, it.is_rest, it.tuplet) for it in hand[:3]] == [
        (0, 16, True, 3), (16, 16, False, 3), (32, 16, False, 3)]
    assert hand[0].tuplet_edge == 'start' and hand[2].tuplet_edge == 'stop'


def first_beat(tmp_path, hits, part='hand'):
    """(start, duration, beams) of the items in beat 1 of a 4/4 bar."""
    score = build(tmp_path, hits + [(3, KICK if part == 'hand' else HH)], **FOUR_FOUR)
    return [(it.start, it.duration, it.beams) for it in voice_items(score.bars[0], part) if it.start < R]


def test_beams_16_8_16(tmp_path):
    assert first_beat(tmp_path, [(0, SNARE), (0.25, SNARE), (0.75, SNARE)]) == [
        (0, 12, [(1, 'begin'), (2, 'forward hook')]),
        (12, 24, [(1, 'continue')]),
        (36, 12, [(1, 'end'), (2, 'backward hook')])]


def test_beams_8_16_16(tmp_path):
    assert first_beat(tmp_path, [(0, SNARE), (0.5, SNARE), (0.75, SNARE)]) == [
        (0, 24, [(1, 'begin')]),
        (24, 12, [(1, 'continue'), (2, 'begin')]),
        (36, 12, [(1, 'end'), (2, 'end')])]


def test_beams_16_16_8(tmp_path):
    assert first_beat(tmp_path, [(0, SNARE), (0.25, SNARE), (0.5, SNARE)]) == [
        (0, 12, [(1, 'begin'), (2, 'begin')]),
        (12, 12, [(1, 'continue'), (2, 'end')]),
        (24, 24, [(1, 'end')])]


def test_beams_dotted8_16(tmp_path):
    beams = first_beat(tmp_path, [(0, SNARE), (0.75, SNARE)])
    assert beams == [(0, 36, [(1, 'begin')]), (36, 12, [(1, 'end'), (2, 'backward hook')])]


def test_beams_16_dotted8(tmp_path):
    beams = first_beat(tmp_path, [(0, SNARE), (0.25, SNARE)])
    assert beams == [(0, 12, [(1, 'begin'), (2, 'forward hook')]), (12, 36, [(1, 'end')])]


def test_beams_four_sixteenths(tmp_path):
    assert first_beat(tmp_path, [(x / 4, HH) for x in range(4)]) == [
        (0, 12, [(1, 'begin'), (2, 'begin')]),
        (12, 12, [(1, 'continue'), (2, 'continue')]),
        (24, 12, [(1, 'continue'), (2, 'continue')]),
        (36, 12, [(1, 'end'), (2, 'end')])]


def test_beams_two_eighths_and_quarter(tmp_path):
    assert first_beat(tmp_path, [(0, HH), (0.5, HH)]) == [(0, 24, [(1, 'begin')]), (24, 24, [(1, 'end')])]
    assert first_beat(tmp_path, [(0, HH)]) == [(0, R, [])]


def test_beams_after_leading_rest(tmp_path):
    beams = first_beat(tmp_path, [(0.25, SNARE), (0.5, SNARE), (0.75, SNARE)])
    assert beams[0] == (0, 12, [])  # the rest
    assert [b for _s, _d, b in beams[1:]] == [
        [(1, 'begin'), (2, 'begin')], [(1, 'continue'), (2, 'continue')], [(1, 'end'), (2, 'end')]]


def test_single_offbeat_note_has_no_beam(tmp_path):
    beams = first_beat(tmp_path, [(0.5, HH)])
    assert beams == [(0, 24, []), (24, 24, [])]


def test_foot_voice_beams(tmp_path):
    beams = first_beat(tmp_path, [(0, KICK), (0.25, KICK), (0.75, KICK)], part='foot')
    assert [b for _s, _d, b in beams] == [[(1, 'begin'), (2, 'forward hook')], [(1, 'continue')],
                                          [(1, 'end'), (2, 'backward hook')]]


def test_triplet_beams_and_tuplet_marks(tmp_path):
    score = build(tmp_path, [(i / 3, RIDE) for i in range(3)] + [(1 + i / 6, SNARE) for i in range(6)],
                  **FOUR_FOUR)
    hand = voice_items(score.bars[0], 'hand')
    trip, sext = hand[:3], hand[3:9]
    assert [it.beams for it in trip] == [[(1, 'begin')], [(1, 'continue')], [(1, 'end')]]
    assert [it.tuplet_edge for it in trip] == ['start', None, 'stop']
    assert [it.tuplet_label for it in trip] == [False, True, False]
    assert all(note_type(it) == ('eighth', 0) for it in trip)
    assert [it.beams for it in sext] == [[(1, 'begin'), (2, 'begin')]] + \
        [[(1, 'continue'), (2, 'continue')]] * 4 + [[(1, 'end'), (2, 'end')]]
    assert all(note_type(it) == ('16th', 0) for it in sext)
    assert sum(it.tuplet_label for it in sext) == 1


def test_mixed_triplet_beam_eighth_and_sixteenths(tmp_path):
    # triplet eighth + two sextuplet 16ths: 0, 1/3, 1/2
    score = build(tmp_path, [(0, SNARE), (1 / 3, SNARE), (0.5, SNARE), (3, KICK)], **FOUR_FOUR)
    hand = voice_items(score.bars[0], 'hand')[:3]
    # inside a tuplet beat with several strokes a note lasts at most an 8th-note triplet,
    # so the last stroke is an 8th triplet followed by a 16th-triplet rest
    assert [(it.duration, it.tuplet) for it in hand] == [(16, 6), (8, 6), (16, 6)]
    assert [beam_level(it) for it in hand] == [1, 2, 1]
    assert hand[1].beams == [(1, 'continue'), (2, 'backward hook')]
