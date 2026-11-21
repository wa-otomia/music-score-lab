"""Model-level odds and ends, the command-line entry points and the GM retag helper."""
import xml.etree.ElementTree as ET

import mido
import pytest
import yaml

from conftest import HH, KICK, SNARE, SONG_DIR, SONG_META, build, make_midi
import build_score
import midi_to_musicxml
import validate_score
from retag_gm_channel10 import retag
from score_core import R, STAFF_LETTERS, ScoreError, build_score as core_build, parse_settings


def test_internal_resolution():
    assert R == 48
    for div in (2, 3, 4, 6, 8, 12, 16, 24):
        assert R % div == 0


def test_settings_defaults():
    s = parse_settings({})
    assert (s.drum_map, s.subdivision, s.tuplets, s.time_signature) == ('gm', 4, 'auto', None)
    assert (s.repeats, s.repeat_counters, s.beam_eighths) == ('simile', False, 'beat')
    assert s.pickup_beats == 0 and s.source_leading_beats == 0


def test_source_leading_defaults_to_pickup():
    assert parse_settings({'pickup_beats': 2}).source_leading_beats == 2


@pytest.mark.parametrize('meta', [{'midi': ['x']}, {'note_map': ['x']}, {'quantize': 4},
                                  {'quantize': {'tuplets': 'maybe'}}, {'tempo_bpm': 1000}])
def test_settings_validation(meta):
    with pytest.raises(ScoreError):
        parse_settings(meta)


def test_summary_and_instruments_used(tmp_path):
    score = build(tmp_path, [(0, KICK), (0, 49), (1, SNARE), (1.5, HH), (2, 44)], sigs=[(0, 4, 4)])
    text = score.summary()
    assert '1 bar,' in text and '5 notes engraved' in text and 'track selection' in text
    used = score.instruments_used()
    letters = [inst.staff for _n, inst in used]
    assert letters == sorted(letters, key=STAFF_LETTERS.index, reverse=True)  # high to low
    assert [n for n, _ in used] == [49, HH, SNARE, KICK, 44]


def test_metadata_file_and_dict_agree(tmp_path):
    midi = make_midi(tmp_path / 'a.mid', [(0, KICK), (1, SNARE)], sigs=[(0, 4, 4)])
    meta = {'title': 'x', 'tempo_bpm': 100}
    path = tmp_path / 'm.yaml'
    path.write_text(yaml.safe_dump(meta))
    a = core_build(midi, path)
    b = core_build(midi, metadata=meta)
    assert [x.events.keys() for x in a.bars] == [x.events.keys() for x in b.bars]
    assert a.tempo_bpm == b.tempo_bpm == 100


def test_bad_midi_and_yaml(tmp_path):
    bad = tmp_path / 'bad.mid'
    bad.write_bytes(b'not a midi file')
    with pytest.raises(ScoreError, match='MIDI'):
        core_build(bad, metadata={'title': 't'})
    ok = make_midi(tmp_path / 'ok.mid', [(0, KICK)])
    meta = tmp_path / 'm.yaml'
    meta.write_text('title: [unclosed\n')
    with pytest.raises(ScoreError, match='YAML'):
        core_build(ok, meta)
    with pytest.raises(ScoreError, match='not found'):
        core_build(ok, tmp_path / 'missing.yaml')


def _meta(tmp_path):
    meta = tmp_path / 'm.yaml'
    meta.write_text('title: CLI\n', encoding='utf-8')
    return meta


def test_cli_no_pdf_success(tmp_path, capsys):
    midi = make_midi(tmp_path / 'a.mid', [(0, KICK), (1, SNARE), (1.5, HH)], sigs=[(0, 4, 4)])
    out = tmp_path / 'out'
    assert build_score.main([str(midi), '--metadata', str(_meta(tmp_path)), '--out-dir', str(out), '--no-pdf']) == 0
    assert ET.parse(out / 'score.musicxml').getroot().findtext('work/work-title') == 'CLI'
    assert not (out / 'score.pdf').exists()
    assert 'MusicXML OK' in capsys.readouterr().out


def test_cli_reports_score_errors(tmp_path, capsys):
    midi = make_midi(tmp_path / 'bad.mid', [(0, 100)], sigs=[(0, 4, 4)])
    args = [str(midi), '--metadata', str(_meta(tmp_path)), '--out-dir', str(tmp_path / 'o'), '--no-pdf']
    assert build_score.main(args) == 2
    assert 'note_map' in capsys.readouterr().err


def test_cli_track_and_channel_options(tmp_path):
    tracks = [{'hits': [(0, 60)], 'channel': 1, 'name': 'Piano'},
              {'hits': [(0, KICK), (1, SNARE)], 'channel': 2, 'name': 'Beat'}]
    midi = make_midi(tmp_path / 'a.mid', tracks=tracks, sigs=[(0, 4, 4)])
    base = [str(midi), '--metadata', str(_meta(tmp_path)), '--no-pdf']
    assert build_score.main(base + ['--out-dir', str(tmp_path / 'o1')]) == 2
    assert build_score.main(base + ['--out-dir', str(tmp_path / 'o2'), '--track', 'Beat']) == 0
    assert build_score.main(base + ['--out-dir', str(tmp_path / 'o3'), '--channel', '2']) == 0


def test_validate_cli(tmp_path):
    meta = _meta(tmp_path)
    midi = make_midi(tmp_path / 'a.mid', [(0, KICK), (1, SNARE)], sigs=[(0, 4, 4)])
    xml = tmp_path / 's.musicxml'
    assert midi_to_musicxml.main([str(midi), '--metadata', str(meta), '--out', str(xml)]) == 0
    assert validate_score.main([str(midi), '--metadata', str(meta), '--musicxml', str(xml)]) == 0
    other = make_midi(tmp_path / 'b.mid', [(0, KICK), (1, SNARE), (2, SNARE)], sigs=[(0, 4, 4)])
    assert validate_score.main([str(other), '--metadata', str(meta), '--musicxml', str(xml)]) == 1


def test_retag_does_not_change_timing(tmp_path):
    src = tmp_path / 'source.mid'
    mf = mido.MidiFile(ticks_per_beat=96)
    track = mido.MidiTrack()
    track.append(mido.Message('note_on', note=42, velocity=100, channel=0, time=48))
    track.append(mido.Message('note_off', note=42, velocity=0, channel=0, time=24))
    mf.tracks.append(track)
    mf.save(src)
    dst = tmp_path / 'out.mid'
    assert retag(src, dst) == 2
    assert [(m.type, m.time, getattr(m, 'channel', None)) for m in mido.MidiFile(dst).tracks[0]] == [
        ('note_on', 48, 9), ('note_off', 24, 9), ('end_of_track', 0, None)]
    with pytest.raises(ValueError):
        retag(src, src)


def test_repo_gm_channel10_copy_matches_source(song):
    b = core_build(SONG_DIR / 'gm-channel10.mid', SONG_META)
    assert b.midi.selected[0][1] == 10
    assert [bar.events.keys() for bar in song.bars] == [bar.events.keys() for bar in b.bars]
    assert song.engraved_hits == b.engraved_hits
