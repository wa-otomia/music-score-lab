import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from conftest import HH, HHO, KICK, RIDE, SNARE, build
import midi_to_musicxml
from midi_to_musicxml import convert, display_pitch, multi_rest_lengths
from validate_score import ValidationError, validate_musicxml

XSD = os.environ.get('MUSICXML_XSD')
needs_xsd = pytest.mark.skipif(not (XSD and Path(XSD).exists()), reason='set MUSICXML_XSD to the MusicXML 4.0 XSD')
FOUR_FOUR = {'sigs': [(0, 4, 4)]}

# note -> (expected MusicXML notehead, filled attribute)
HEADS = {38: ('normal', None), 42: ('x', None), 52: ('circle-x', None), 53: ('diamond', 'no'),
         56: ('triangle', None), 60: ('cross', None), 70: ('diamond', 'yes')}


def feature_hits():
    """A pickup, 16-8-16 beams, triplets, sextuplets, a flam, open hi-hat, empty bars, meter change."""
    hits = [(0, SNARE), (0.5, SNARE)]                                  # pickup (1 beat)
    o = 1
    hits += [(o + 0, KICK), (o + 0, 49), (o + 0, SNARE), (o + 0.25, SNARE), (o + 0.75, SNARE),
             (o + 1, HH), (o + 1.5, HHO), (o + 2 + 0, RIDE), (o + 2 + 1 / 3, RIDE), (o + 2 + 2 / 3, RIDE),
             (o + 2, KICK)] + [(o + 3 + i / 6, SNARE) for i in range(6)] + [(o + 3, 44)]
    o += 4
    hits += [(o + 1 - 40 / 480, SNARE, 40), (o + 1, SNARE, 110), (o, KICK)]    # flam
    hits += [(o + b, n) for b, n in zip(range(4), HEADS)]
    hits += [(o + 3.5, n) for n in list(HEADS)[4:]]
    o += 4
    o += 4 * 3                                                         # three empty bars
    hits += [(o, KICK), (o + 1, SNARE), (o + 2, KICK)]                 # 3/4 bar
    return hits


@pytest.fixture
def feature_score(tmp_path):
    sigs = [(0, 1, 4), (1, 4, 4), (21, 3, 4)]
    return build(tmp_path, feature_hits(), {'pickup_beats': 1, 'source_leading_beats': 1, 'title': '機能テスト',
                                            'composer': 'A', 'artist': 'B', 'transcriber': 'C'},
                 sigs=sigs, tempo=132, tempos=[(5, 150)])


def written(score, tmp_path) -> tuple[Path, ET.Element]:
    path = tmp_path / 'score.musicxml'
    midi_to_musicxml.write(score, path)
    return path, ET.parse(path).getroot()


def test_feature_score_shape(feature_score):
    bars = feature_score.bars
    assert [(b.number, b.beats) for b in bars] == [(0, 1), (1, 4), (2, 4), (3, 4), (4, 4), (5, 4), (6, 3)]
    assert feature_score.grace_hits == 1


def test_validate_musicxml_synthetic(feature_score, tmp_path):
    path, _root = written(feature_score, tmp_path)
    assert validate_musicxml(feature_score, path).startswith('MusicXML OK')


def test_validate_musicxml_repo_song(song, tmp_path):
    path, _root = written(song, tmp_path)
    msg = validate_musicxml(song, path)
    assert '202 bars' in msg and '1952 notes' in msg


@needs_xsd
def test_xsd_valid_synthetic(feature_score, tmp_path):
    path, _root = written(feature_score, tmp_path)
    validate_musicxml(feature_score, path, Path(XSD))


@needs_xsd
def test_xsd_valid_repo_song(song, tmp_path):
    path, _root = written(song, tmp_path)
    validate_musicxml(song, path, Path(XSD))


def test_validator_catches_tampering(feature_score, tmp_path):
    path, root = written(feature_score, tmp_path)
    note = next(n for n in root.iter('note') if n.find('unpitched') is not None and n.find('grace') is None)
    note.find('stem').text = 'down' if note.findtext('voice') == '1' else 'up'
    ET.ElementTree(root).write(path)
    with pytest.raises(ValidationError, match='stem'):
        validate_musicxml(feature_score, path)


def test_header_and_doctype(feature_score, tmp_path):
    path, root = written(feature_score, tmp_path)
    head = path.read_bytes()[:300]
    assert head.startswith(b'<?xml version="1.0" encoding="UTF-8"?>') and b'DOCTYPE score-partwise' in head
    assert root.get('version') == '4.0'
    assert root.findtext('work/work-title') == '機能テスト'
    assert root.find('identification/creator[@type="composer"]').text == 'A'
    assert root.findtext('part/measure/attributes/divisions') == '48'
    assert root.findtext('part/measure/attributes/clef/sign') == 'percussion'


def test_stems_by_voice(feature_score):
    root, _ = convert(feature_score)
    seen = set()
    for note in root.iter('note'):
        if note.find('rest') is not None:
            assert note.find('stem') is None
            continue
        voice = note.findtext('voice')
        assert note.findtext('stem') == {'1': 'up', '2': 'down'}[voice]
        inst = int(note.find('instrument').get('id').rsplit('I', 1)[1])
        assert voice == ('2' if inst in (KICK, 44) else '1')
        seen.add(voice)
    assert seen == {'1', '2'}


def test_noteheads(feature_score):
    root, _ = convert(feature_score)
    found = {}
    for note in root.iter('note'):
        if note.find('instrument') is None:
            continue
        n = int(note.find('instrument').get('id').rsplit('I', 1)[1])
        head = note.find('notehead')
        found[n] = (head.text, head.get('filled'))
    for n, want in HEADS.items():
        assert found[n] == want, n
    assert found[KICK] == ('normal', None)


def test_display_pitches():
    assert display_pitch('c') == ('C', '4')
    assert display_pitch('f') == ('F', '4')   # kick: first space
    assert display_pitch('j') == ('C', '5')   # snare: third space
    assert display_pitch('n') == ('G', '5')   # hi-hat: space above the staff
    assert display_pitch('o') == ('A', '5')   # crash: first ledger line


def test_midi_unpitched_is_note_plus_one(feature_score):
    root, _ = convert(feature_score)
    part = root.find('part-list/score-part')
    insts = {si.get('id'): si.findtext('instrument-name') for si in part.findall('score-instrument')}
    for mi in part.findall('midi-instrument'):
        note = int(mi.get('id').rsplit('I', 1)[1])
        assert int(mi.findtext('midi-unpitched')) == note + 1
        assert mi.findtext('midi-channel') == '10'
        assert insts[mi.get('id')].endswith(f'({note})')
    used = {n for n, _ in feature_score.instruments_used()}
    assert {int(i.rsplit('I', 1)[1]) for i in insts} == used


def test_multiple_rest_measure_style(feature_score):
    assert multi_rest_lengths(feature_score.bars) == {3: 3}
    root, _ = convert(feature_score)
    measures = root.findall('part/measure')
    assert measures[3].findtext('attributes/measure-style/multiple-rest') == '3'
    assert all(m.find('attributes/measure-style') is None for i, m in enumerate(measures) if i != 3)
    for m in measures[3:6]:
        rests = m.findall('note/rest')
        assert len(rests) == 2 and all(r.get('measure') == 'yes' for r in rests)
        assert all(n.find('type') is None for n in m.findall('note'))


def test_single_empty_bar_has_no_multiple_rest(tmp_path):
    score = build(tmp_path, [(0, KICK), (8, KICK)], **FOUR_FOUR)
    assert multi_rest_lengths(score.bars) == {}
    root, _ = convert(score)
    assert root.find('.//multiple-rest') is None


def test_multiple_rest_split_by_tempo_change(tmp_path):
    score = build(tmp_path, [(0, KICK), (20, KICK)], sigs=[(0, 4, 4)], tempo=120, tempos=[(12, 90)])
    assert multi_rest_lengths(score.bars) == {1: 2, 3: 2}


def test_pickup_and_meter_attributes(feature_score):
    root, _ = convert(feature_score)
    measures = root.findall('part/measure')
    assert measures[0].get('number') == '0' and measures[0].get('implicit') == 'yes'
    assert measures[0].findtext('attributes/time/beats') == '1'
    assert measures[1].get('implicit') is None and measures[1].findtext('attributes/time/beats') == '4'
    assert measures[2].find('attributes/time') is None
    assert measures[6].findtext('attributes/time/beats') == '3'
    assert measures[-1].findtext('barline/bar-style') == 'light-heavy'


def test_tempo_directions(feature_score):
    root, _ = convert(feature_score)
    measures = root.findall('part/measure')
    assert measures[0].find('direction/sound').get('tempo') == '132'
    assert measures[2].findtext('direction/direction-type/metronome/per-minute') == '150'
    assert measures[1].find('direction') is None


def test_beams_16_8_16_in_xml(feature_score):
    root, _ = convert(feature_score)
    bar1 = root.findall('part/measure')[1]
    snares = [n for n in bar1.findall('note') if n.findtext('voice') == '1' and n.find('chord') is None][:3]
    beams = [[(b.get('number'), b.text) for b in n.findall('beam')] for n in snares]
    assert beams == [[('1', 'begin'), ('2', 'forward hook')], [('1', 'continue')],
                     [('1', 'end'), ('2', 'backward hook')]]
    assert [n.findtext('type') for n in snares] == ['16th', 'eighth', '16th']


def test_chord_notes_carry_beams_only_once(feature_score):
    root, _ = convert(feature_score)
    for note in root.iter('note'):
        if note.find('chord') is not None:
            assert note.find('beam') is None


def test_tuplets_in_xml(feature_score):
    root, _ = convert(feature_score)
    bar1 = root.findall('part/measure')[1]
    voice1 = [n for n in bar1.findall('note') if n.findtext('voice') == '1' and n.find('chord') is None]
    mods = [(n.findtext('time-modification/actual-notes'), n.findtext('time-modification/normal-notes'))
            for n in voice1]
    assert mods.count(('3', '2')) == 3
    assert mods.count(('6', '4')) == 6
    starts = [t for n in voice1 for t in n.findall('notations/tuplet') if t.get('type') == 'start']
    stops = [t for n in voice1 for t in n.findall('notations/tuplet') if t.get('type') == 'stop']
    assert len(starts) == len(stops) == 2
    assert all(t.get('bracket') == 'no' for t in starts)


def test_grace_and_technical(feature_score):
    root, _ = convert(feature_score)
    graces = [n for n in root.iter('note') if n.find('grace') is not None]
    assert len(graces) == 1
    g = graces[0]
    assert g.find('grace').get('slash') == 'yes' and g.find('duration') is None
    assert g.findtext('type') == 'eighth'
    opens = [n for n in root.iter('note') if n.find('notations/technical/open') is not None]
    assert len(opens) == 1 and opens[0].find('instrument').get('id').endswith(f'I{HHO}')


def test_ghost_and_accent_in_xml(tmp_path):
    score = build(tmp_path, [(0, SNARE, 20), (1, SNARE, 127), (0, KICK)],
                  {'dynamics': {'ghost_below': 40, 'accent_above': 110}}, **FOUR_FOUR)
    root, _ = convert(score)
    snares = [n for n in root.iter('note') if n.find('instrument') is not None
              and n.find('instrument').get('id').endswith('I38')]
    assert snares[0].find('notehead').get('parentheses') == 'yes'
    assert snares[1].find('notations/articulations/accent') is not None


def test_engraved_count_returned(feature_score):
    _root, count = convert(feature_score)
    assert count == feature_score.engraved_hits
