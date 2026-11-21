import pytest

from conftest import HH, KICK, SNARE, build, events_at
from score_core import R, ScoreError


def beats_hits(n_beats, note=HH):
    return [(b, note) for b in range(n_beats)]


def test_midi_three_four_is_honoured(tmp_path):
    score = build(tmp_path, beats_hits(6), sigs=[(0, 3, 4)])
    assert [(b.beats, b.beat_type, b.start) for b in score.bars] == [(3, 4, 0), (3, 4, 3 * R)]
    assert [b.number for b in score.bars] == [1, 2]
    assert score.bars[0].show_meter and not score.bars[1].show_meter
    assert all(len(b.events) == 3 for b in score.bars)


def test_meter_change_on_barline(tmp_path):
    score = build(tmp_path, beats_hits(12), sigs=[(0, 4, 4), (4, 3, 4), (7, 2, 4), (9, 3, 4)])
    meters = [(b.beats, b.show_meter) for b in score.bars]
    assert meters == [(4, True), (3, True), (2, True), (3, True)]
    assert [b.start for b in score.bars] == [0, 4 * R, 7 * R, 9 * R]


def test_repeated_identical_time_signature_does_not_show_meter(tmp_path):
    score = build(tmp_path, beats_hits(8), sigs=[(0, 4, 4), (4, 4, 4)])
    assert [b.show_meter for b in score.bars] == [True, False]


def test_meter_change_inside_bar_raises(tmp_path):
    with pytest.raises(ScoreError, match='barline'):
        build(tmp_path, beats_hits(8), sigs=[(0, 4, 4), (2, 3, 4)])


@pytest.mark.parametrize('n, d', [(6, 8), (12, 8), (3, 2), (13, 4)])
def test_unsupported_meters_raise(tmp_path, n, d):
    with pytest.raises(ScoreError, match=f'{n}/{d}'):
        build(tmp_path, beats_hits(4), sigs=[(0, n, d)])


def test_metadata_time_signature_mismatch_raises(tmp_path):
    with pytest.raises(ScoreError, match='does not match'):
        build(tmp_path, beats_hits(4), {'time_signature': '4/4'}, sigs=[(0, 3, 4)])


def test_metadata_time_signature_without_midi_signature(tmp_path):
    score = build(tmp_path, beats_hits(10), {'time_signature': '5/4'})
    assert [b.beats for b in score.bars] == [5, 5]
    assert not any('time signature' in w for w in score.warnings)


def test_metadata_time_signature_bad_syntax(tmp_path):
    with pytest.raises(ScoreError, match='time_signature'):
        build(tmp_path, beats_hits(4), {'time_signature': 'four'})


def test_legacy_beats_keys(tmp_path):
    score = build(tmp_path, beats_hits(6), {'beats': 3, 'beat_type': 4})
    assert [b.beats for b in score.bars] == [3, 3]
    assert score.settings.time_signature == (3, 4)


def test_legacy_quantize_divisions_per_beat(tmp_path):
    score = build(tmp_path, [(0.5, HH)], {'quantize_divisions_per_beat': 2}, sigs=[(0, 4, 4)])
    assert score.settings.subdivision == 2
    with pytest.raises(ScoreError, match='8th'):
        build(tmp_path, [(i / 4, HH) for i in range(4)], {'quantize_divisions_per_beat': 2}, sigs=[(0, 4, 4)])


def test_missing_time_signature_defaults_to_four_four_with_warning(tmp_path):
    score = build(tmp_path, beats_hits(5))
    assert [b.beats for b in score.bars] == [4, 4]
    assert any('4/4' in w for w in score.warnings)


def test_pickup_bar_with_notes(tmp_path):
    hits = [(0, SNARE), (0.5, SNARE), (1, KICK), (1, HH), (2, HH)]
    score = build(tmp_path, hits, {'pickup_beats': 1, 'source_leading_beats': 1}, sigs=[(0, 4, 4)])
    first, second = score.bars[0], score.bars[1]
    assert (first.pickup, first.number, first.beats, first.start, first.show_meter) == (True, 0, 1, 0, True)
    assert events_at(first) == {0: [SNARE], 24: [SNARE]}
    assert (second.pickup, second.number, second.beats, second.start, second.show_meter) == (False, 1, 4, R, True)
    assert events_at(second) == {0: [KICK, HH], 48: [HH]}


def test_source_leading_beats_trimmed_before_pickup(tmp_path):
    # 4 beats of silence in the source, but only a 2-beat pickup is printed.
    hits = [(3.5, SNARE), (4, KICK), (5, SNARE)]
    score = build(tmp_path, hits, {'pickup_beats': 2, 'source_leading_beats': 4}, sigs=[(0, 4, 4)])
    assert score.bars[0].pickup and score.bars[0].beats == 2
    assert events_at(score.bars[0]) == {72: [SNARE]}
    assert events_at(score.bars[1]) == {0: [KICK], 48: [SNARE]}
    assert len(score.bars) == 2


def test_silent_pickup_bar(tmp_path):
    score = build(tmp_path, [(4, KICK)], {'pickup_beats': 2, 'source_leading_beats': 4}, sigs=[(0, 4, 4)])
    assert score.bars[0].pickup and not score.bars[0].events
    assert events_at(score.bars[1]) == {0: [KICK]}


def test_source_leading_without_pickup(tmp_path):
    score = build(tmp_path, [(4, KICK), (5, SNARE)], {'source_leading_beats': 4}, sigs=[(0, 4, 4)])
    assert len(score.bars) == 1 and not score.bars[0].pickup
    assert events_at(score.bars[0]) == {0: [KICK], 48: [SNARE]}


def test_notes_before_score_start_raise(tmp_path):
    with pytest.raises(ScoreError, match='source_leading_beats'):
        build(tmp_path, [(1, KICK), (4, KICK)], {'source_leading_beats': 4}, sigs=[(0, 4, 4)])


@pytest.mark.parametrize('meta', [{'pickup_beats': 3, 'source_leading_beats': 2},
                                  {'pickup_beats': 1.5, 'source_leading_beats': 2},
                                  {'pickup_beats': -1}])
def test_invalid_pickup_settings(tmp_path, meta):
    with pytest.raises(ScoreError, match='pickup_beats'):
        build(tmp_path, [(4, KICK)], meta)


def test_pickup_followed_by_midi_meter(tmp_path):
    # Showcase-style: MIDI has 1/4 then 4/4; metadata declares a 1-beat pickup.
    hits = [(0, SNARE), (1, KICK), (5, KICK)]
    score = build(tmp_path, hits, {'pickup_beats': 1, 'source_leading_beats': 1}, sigs=[(0, 1, 4), (1, 4, 4)])
    assert [(b.number, b.beats, b.pickup) for b in score.bars] == [(0, 1, True), (1, 4, False), (2, 4, False)]


def test_tempo_from_midi_and_changes(tmp_path):
    score = build(tmp_path, beats_hits(12), sigs=[(0, 4, 4)], tempo=96, tempos=[(4, 132), (8, 132.2)])
    assert score.tempo_bpm == 96
    assert [b.tempo for b in score.bars] == [96, 132, None]


def test_metadata_tempo_overrides_with_warning(tmp_path):
    score = build(tmp_path, beats_hits(4), {'tempo_bpm': 200}, sigs=[(0, 4, 4)], tempo=120)
    assert score.tempo_bpm == 200 and score.bars[0].tempo == 200
    assert any('tempo_bpm' in w for w in score.warnings)


def test_bar_count_extends_to_last_note(tmp_path):
    score = build(tmp_path, [(0, KICK), (9.75, HH)], sigs=[(0, 4, 4)])
    assert len(score.bars) == 3
    assert events_at(score.bars[2]) == {84: [HH]}
    assert not score.bars[1].events


def test_repo_song(song):
    assert len(song.bars) == 202
    assert song.engraved_hits == 1952
    assert song.grace_hits == 4
    assert song.triplet_beat_count == 0
    first = song.bars[0]
    assert first.pickup and first.number == 0 and first.beats == 2 and first.beat_type == 4
    assert not first.events
    assert song.bars[1].beats == 4 and song.bars[1].show_meter and song.bars[1].number == 1
    assert all(b.beats == 4 for b in song.bars[1:])
    assert song.tempo_bpm == 200
    assert song.midi.selected == [(1, 1)]
    assert song.drum_map.name.startswith('FL Studio FPC')
    graces = sum(1 for b in song.bars for hs in b.events.values() for h in hs.values() if h.grace)
    assert graces == 4
