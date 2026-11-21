import pytest
import yaml

from conftest import KICK, SNARE, build, make_midi
from score_core import Instrument, ScoreError, build_score, load_drum_map, load_instruments

GM_RANGE = range(27, 88)


@pytest.mark.parametrize('name', ['gm', 'fpc-default'])
def test_every_gm_gs_note_resolves(name):
    dmap = load_drum_map(name)
    missing = [n for n in GM_RANGE if n not in dmap.notes]
    assert not missing
    for note in GM_RANGE:
        inst = dmap.notes[note]
        assert isinstance(inst, Instrument)
        assert inst.part in ('hand', 'foot')


def test_gm_core_assignments():
    notes = load_drum_map('gm').notes
    assert notes[36].id == 'kick' and notes[36].part == 'foot'
    assert notes[38].id == notes[40].id == 'snare'
    assert notes[42].id == 'hihat-closed' and notes[46].mark == 'open'
    assert notes[44].id == 'hihat-pedal' and notes[44].part == 'foot'
    assert notes[49].id == 'crash' and notes[51].id == 'ride'


def test_fpc_default_inherits_gm():
    gm, fpc = load_drum_map('gm'), load_drum_map('fpc-default')
    assert fpc.notes == gm.notes
    assert len(fpc.sources) == 2
    assert fpc.sources[0].endswith('gm.yaml') and fpc.sources[1].endswith('fpc-default.yaml')


def test_instrument_catalog_is_valid():
    instruments = load_instruments()
    assert {'kick', 'snare', 'hihat-closed', 'crash'} <= set(instruments)


def test_extends_inheritance_and_override(tmp_path):
    base = tmp_path / 'base.yaml'
    base.write_text(yaml.safe_dump({'name': 'base', 'extends': 'fpc-default', 'notes': {40: 'hand-clap'}}))
    child = tmp_path / 'child.yaml'
    child.write_text(yaml.safe_dump({'name': 'child', 'extends': 'base.yaml',
                                     'notes': {100: {'as': 'cowbell', 'staff': 'p'}}}))
    dmap = load_drum_map(child, relative_to=tmp_path)
    assert dmap.name == 'child'
    assert dmap.notes[40].id == 'hand-clap'      # from base
    assert dmap.notes[36].id == 'kick'           # from gm via fpc-default
    assert dmap.notes[100].staff == 'p' and dmap.notes[100].head == 'triangle'
    assert len(dmap.sources) == 4


def test_extends_cycle_is_an_error(tmp_path):
    (tmp_path / 'a.yaml').write_text(yaml.safe_dump({'extends': str(tmp_path / 'b.yaml'), 'notes': {}}))
    (tmp_path / 'b.yaml').write_text(yaml.safe_dump({'extends': str(tmp_path / 'a.yaml'), 'notes': {}}))
    with pytest.raises(ScoreError, match='cycle'):
        load_drum_map(tmp_path / 'a.yaml')


def test_drum_map_unknown_field(tmp_path):
    (tmp_path / 'm.yaml').write_text(yaml.safe_dump({'notes': {}, 'note': 'typo'}))
    with pytest.raises(ScoreError, match='unknown field'):
        load_drum_map(tmp_path / 'm.yaml')


def test_unknown_drum_map_name():
    with pytest.raises(ScoreError, match='gm'):
        load_drum_map('no-such-map')


def test_drum_map_path_relative_to_metadata(tmp_path):
    (tmp_path / 'kit.yaml').write_text(yaml.safe_dump({'extends': 'gm', 'notes': {38: 'side-stick'}}))
    midi = make_midi(tmp_path / 'a.mid', [(0, SNARE)], sigs=[(0, 4, 4)])
    meta = tmp_path / 'meta.yaml'
    meta.write_text(yaml.safe_dump({'title': 't', 'drum_map': 'kit.yaml'}))
    score = build_score(midi, meta)
    assert score.bars[0].events[0][SNARE].inst.id == 'side-stick'


def test_note_map_instrument_id(tmp_path):
    score = build(tmp_path, [(0, 40), (1, KICK)], {'drum_map': 'fpc-default', 'note_map': {40: 'hand-clap'}})
    assert score.bars[0].events[0][40].inst.id == 'hand-clap'
    assert score.bars[0].events[48][KICK].inst.id == 'kick'
    assert score.drum_map.name.endswith('+ note_map')


def test_note_map_as_with_overrides(tmp_path):
    score = build(tmp_path, [(0, 40)], {'note_map': {40: {'as': 'snare', 'head': 'x', 'abbr': 'ES'}}})
    inst = score.bars[0].events[0][40].inst
    assert inst.id == 'snare@40'
    assert (inst.head, inst.staff, inst.part, inst.abbr, inst.name_ja) == ('x', 'j', 'hand', 'ES', 'スネア')


def test_note_map_as_without_overrides_keeps_id(tmp_path):
    score = build(tmp_path, [(0, 40)], {'note_map': {40: {'as': 'hand-clap'}}})
    assert score.bars[0].events[0][40].inst.id == 'hand-clap'


def test_note_map_full_inline_definition(tmp_path):
    spec = {'name': 'Gong', 'name_ja': 'ドラ', 'abbr': 'GG', 'part': 'hand', 'staff': 'p', 'head': 'circle-x'}
    score = build(tmp_path, [(0, 100)], {'note_map': {100: spec}})
    inst = score.bars[0].events[0][100].inst
    assert inst.id == 'note-100'
    assert (inst.name, inst.name_ja, inst.staff, inst.head) == ('Gong', 'ドラ', 'p', 'circle-x')


def test_note_map_inline_with_explicit_id_and_defaults(tmp_path):
    score = build(tmp_path, [(0, 101)], {'note_map': {101: {'id': 'block', 'name': 'Block', 'part': 'foot',
                                                              'staff': 'e', 'head': 'plus'}}})
    inst = score.bars[0].events[0][101].inst
    assert inst.id == 'block' and inst.name_ja == 'Block' and inst.abbr == 'Blo'


@pytest.mark.parametrize('spec, pattern', [
    ({'name': 'X', 'part': 'hand', 'staff': 'j'}, 'head'),
    ({'name': 'X', 'part': 'arm', 'staff': 'j', 'head': 'x'}, 'part'),
    ({'name': 'X', 'part': 'hand', 'staff': 'z', 'head': 'x'}, 'staff'),
    ({'name': 'X', 'part': 'hand', 'staff': 'j', 'head': 'star'}, 'head'),
    ({'name': 'X', 'part': 'hand', 'staff': 'j', 'head': 'x', 'abbr': 'ドラ'}, 'abbr'),
    ({'name': 'X', 'part': 'hand', 'staff': 'j', 'head': 'x', 'colour': 'red'}, 'unknown field'),
])
def test_note_map_inline_validation(tmp_path, spec, pattern):
    with pytest.raises(ScoreError, match=pattern):
        build(tmp_path, [(0, 100)], {'note_map': {100: spec}})


def test_note_map_unknown_instrument(tmp_path):
    with pytest.raises(ScoreError, match='instruments.yaml') as exc:
        build(tmp_path, [(0, 40)], {'note_map': {40: 'hand-clapp'}})
    assert 'hand-clapp' in str(exc.value)
    with pytest.raises(ScoreError, match='nope'):
        build(tmp_path, [(0, 40)], {'note_map': {40: {'as': 'nope'}}})


def test_note_map_bad_note_number(tmp_path):
    with pytest.raises(ScoreError, match='0 and 127'):
        build(tmp_path, [(0, 40)], {'note_map': {200: 'snare'}})


def test_unmapped_note_error_mentions_note_map(tmp_path):
    with pytest.raises(ScoreError) as exc:
        build(tmp_path, [(0, KICK), (1, 100), (2, 26)], {'drum_map': 'fpc-default'})
    msg = str(exc.value)
    assert 'note_map' in msg
    assert '[26, 100]' in msg
    assert 'instruments.yaml' in msg


def test_cli_drum_map_overrides_metadata(tmp_path):
    (tmp_path / 'kit.yaml').write_text(yaml.safe_dump({'extends': 'gm', 'notes': {38: 'hand-clap'}}))
    score = build(tmp_path, [(0, SNARE)], {'drum_map': 'gm'}, drum_map=tmp_path / 'kit.yaml')
    assert score.bars[0].events[0][SNARE].inst.id == 'hand-clap'
