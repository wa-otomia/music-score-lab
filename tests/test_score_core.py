from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mido
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from score_core import build_score, hand_beams
from midi_to_musicxml import convert


def fixture(tmp_path, pickup=0, lead=0):
    midi = mido.MidiFile(type=1, ticks_per_beat=96)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    # Four consecutive 16th closed hats with simultaneous kick on beat 1.
    for idx, t in enumerate((0, 24, 48, 72)):
        if idx == 0:
            track.append(mido.Message('note_on', note=36, velocity=90, channel=9, time=t + lead*96))
            track.append(mido.Message('note_on', note=42, velocity=80, channel=9, time=0))
        else:
            track.append(mido.Message('note_on', note=42, velocity=80, channel=9, time=24))
    path = tmp_path / 'example.mid'
    midi.save(path)
    cfg = tmp_path / 'meta.yaml'
    cfg.write_text(yaml.safe_dump({'title':'Original test rhythm','transcriber':'test','pickup_beats':pickup,
                                   'source_leading_beats':lead,'beats':4,'beat_type':4}), encoding='utf-8')
    return build_score(path, cfg, ROOT / 'configs/japanese-drums.yaml')


def test_four_sixteenths_have_double_beams(tmp_path):
    score = fixture(tmp_path)
    assert len(score.bars) == 1
    beams = hand_beams(score.bars[0], score)
    assert beams == {0:('start',2),24:('mid',2),48:('mid',2),72:('end',2)}
    root, count = convert(score)
    assert count == 5
    measure = root.find('part/measure')
    assert len(measure.findall('note')) >= 5
    for n in measure.findall('note'):
        if n.findtext('type') == '16th' and n.find('beam') is not None:
            assert len(n.findall('beam')) == 2


def test_silent_pickup_shifts_full_bar(tmp_path):
    score = fixture(tmp_path, pickup=2, lead=4)
    assert len(score.bars) == 2
    assert score.bars[0] == {}
    assert min(score.bars[1]) == 0
    root, _ = convert(score)
    assert root.findall('part/measure')[0].find('note/duration').text == '192'


def test_unmapped_note_fails(tmp_path):
    path = tmp_path / 'unknown.mid'
    mf = mido.MidiFile(ticks_per_beat=96)
    mf.tracks.append(mido.MidiTrack([mido.Message('note_on',note=100,velocity=80,channel=9)]))
    mf.save(path)
    m = tmp_path / 'meta.yaml'
    m.write_text('title: test\n')
    with pytest.raises(ValueError, match='Missing GM percussion mapping'):
        build_score(path, m, ROOT / 'configs/japanese-drums.yaml')


def test_retag_does_not_change_timing(tmp_path):
    from retag_gm_channel10 import retag
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
