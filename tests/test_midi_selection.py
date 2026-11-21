import pytest

from conftest import HH, KICK, SNARE, build
from score_core import ScoreError

GROOVE = [(0, KICK), (1, SNARE), (2, KICK), (3, SNARE)] + [(x / 2, HH) for x in range(8)]
BASS = [(0, 40), (1, 43), (2, 45), (3, 47), (0.5, 33)]   # pitched bass notes that collide with drum keys
PIANO = [(0, 60), (1, 64), (2, 67)]


def notes_in(score):
    return sorted({n for bar in score.bars for hits in bar.events.values() for n in hits})


def test_single_fpc_track_on_channel_1_is_auto_selected(tmp_path):
    score = build(tmp_path, GROOVE, {'drum_map': 'fpc-default'}, channel=1, name='FPC 1')
    assert score.midi.selected == [(1, 1)]
    assert score.engraved_hits == len(GROOVE)
    assert score.midi.groups[(1, 1)]['name'] == 'FPC 1'


def test_channel_10_preferred_over_other_channels(tmp_path):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 10, 'name': 'Track 2'}]
    score = build(tmp_path, tracks=tracks)
    assert score.midi.selected == [(2, 10)]
    assert '10' in score.midi.selection_reason
    assert notes_in(score) == [KICK, SNARE, HH]


def test_bass_on_channel_1_not_treated_as_drums(tmp_path):
    # 40/43/45/47 are valid drum keys: if the bass leaked in, toms and snare would appear.
    tracks = [{'hits': BASS, 'channel': 1, 'name': 'Bass'},
              {'hits': GROOVE, 'channel': 10, 'name': 'Drums'}]
    score = build(tmp_path, tracks=tracks)
    assert notes_in(score) == [KICK, SNARE, HH]
    assert score.source_hits == len(GROOVE)


def test_bass_and_drums_on_same_track_different_channels(tmp_path):
    # One track carrying both channels (as a format-0 export would): channel 10 wins.
    hits = [(b, n, 90, 1) for b, n in BASS] + [(b, n, 100, 10) for b, n in GROOVE]
    score = build(tmp_path, hits, name='All')
    assert score.midi.selected == [(1, 10)]
    assert notes_in(score) == [KICK, SNARE, HH]


@pytest.mark.parametrize('name', ['FPC 1', 'Drums', 'Percussion', 'Kit', 'drum kit'])
def test_track_name_heuristic(tmp_path, name):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 2, 'name': name}]
    score = build(tmp_path, tracks=tracks)
    assert score.midi.selected == [(2, 2)]
    assert 'FPC' in score.midi.selection_reason


@pytest.mark.parametrize('name', ['ドラム', '鼓'])
def test_track_name_heuristic_japanese_utf8(tmp_path, name):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 2, 'name': name}]
    score = build(tmp_path, tracks=tracks, charset='utf-8')
    assert score.midi.selected == [(2, 2)]


def test_ambiguous_multichannel_file_raises_listing_groups(tmp_path):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 2, 'name': 'Something'}]
    with pytest.raises(ScoreError) as exc:
        build(tmp_path, tracks=tracks)
    msg = str(exc.value)
    assert 'midi.tracks' in msg and 'midi.channels' in msg
    assert 'Piano' in msg and 'Something' in msg
    assert '通道 1' in msg and '通道 2' in msg
    assert f'{len(GROOVE)} 个音' in msg


def test_explicit_midi_tracks_by_name(tmp_path):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 2, 'name': 'Beat'}]
    score = build(tmp_path, meta={'midi': {'tracks': ['beat']}}, tracks=tracks)
    assert score.midi.selected == [(2, 2)]
    assert notes_in(score) == [KICK, SNARE, HH]


def test_explicit_midi_tracks_by_index(tmp_path):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 2, 'name': 'Beat'}]
    score = build(tmp_path, meta={'midi': {'tracks': 2}}, tracks=tracks)
    assert score.midi.selected == [(2, 2)]


def test_explicit_midi_channels_overrides_channel_10(tmp_path):
    tracks = [{'hits': GROOVE, 'channel': 3, 'name': 'Real drums'},
              {'hits': [(0, 39)], 'channel': 10, 'name': 'GM'}]
    score = build(tmp_path, meta={'midi': {'channels': [3]}}, tracks=tracks)
    assert score.midi.selected == [(1, 3)]
    assert notes_in(score) == [KICK, SNARE, HH]


def test_cli_tracks_override_metadata(tmp_path):
    tracks = [{'hits': PIANO, 'channel': 1, 'name': 'Piano'},
              {'hits': GROOVE, 'channel': 2, 'name': 'Beat'}]
    score = build(tmp_path, meta={'midi': {'tracks': ['piano']}}, cli={'tracks': ['Beat']}, tracks=tracks)
    assert score.midi.selected == [(2, 2)]
    score = build(tmp_path, cli={'channels': [2]}, tracks=tracks)
    assert score.midi.selected == [(2, 2)]


def test_selection_matching_nothing_raises(tmp_path):
    with pytest.raises(ScoreError, match='没有选中'):
        build(tmp_path, GROOVE, {'midi': {'channels': [5]}})


def test_channel_out_of_range(tmp_path):
    with pytest.raises(ScoreError, match='1–16'):
        build(tmp_path, GROOVE, {'midi': {'channels': [0]}})


def test_no_notes_raises(tmp_path):
    with pytest.raises(ScoreError, match='note-on'):
        build(tmp_path, [])


def test_unknown_metadata_key_raises(tmp_path):
    with pytest.raises(ScoreError, match='未知字段'):
        build(tmp_path, GROOVE, {'titel': 'x'})
