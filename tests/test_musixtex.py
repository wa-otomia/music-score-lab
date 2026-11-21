import re

import pytest

from conftest import HH, HHO, KICK, RIDE, SNARE, build
from midi_to_musixtex import convert, legend_entries, legend_tex

FOUR_FOUR = {'sigs': [(0, 4, 4)]}


def bar_lines(tex: str, number: int) -> list[str]:
    """Lines of one bar (between its '% bar N' comment and the next bar separator)."""
    lines = tex.splitlines()
    start = next(i for i, l in enumerate(lines) if re.match(rf'% bar {number}\b', l))
    out = []
    for line in lines[start + 1:]:
        if line.startswith('% bar') or line in (r'\bar', r'\alaligne', r'\changecontext') \
                or line.startswith(r'\generalmeter') or line.startswith(r'\setdoubleBAR') or line == r'\endpiece':
            break
        out.append(line)
    return out


def tex_for(tmp_path, hits, meta=None, **kw):
    kw = kw or FOUR_FOUR
    return convert(build(tmp_path, hits, meta, **kw))


def test_16_8_16_hooks(tmp_path):
    tex = tex_for(tmp_path, [(0, SNARE), (0.25, SNARE), (0.75, SNARE), (2, KICK)])
    notes = bar_lines(tex, 1)[:3]
    assert r'\ibbu0{j}0\roff{\tbbu0}' in notes[0]
    assert r'\tbbu0' not in notes[1] and r'\ibbu0' not in notes[1]
    assert notes[2].index(r'\tbbu0') < notes[2].index(r'\@tqh0{j}')
    assert notes[2].endswith(r'\tbbu0\q@symbol\@tqh0{j}\en')


def test_four_sixteenths_double_beam(tmp_path):
    tex = tex_for(tmp_path, [(x / 4, HH) for x in range(4)] + [(2, KICK)])
    notes = bar_lines(tex, 1)[:4]
    assert r'\ibbu0{n}0' in notes[0] and r'\roff' not in notes[0]
    assert r'\@qb0{n}' in notes[1] and r'\@qb0{n}' in notes[2]
    assert r'\@tqh0{n}' in notes[3]


def test_foot_beams_use_beam_1_downwards(tmp_path):
    tex = tex_for(tmp_path, [(0, KICK), (0.25, KICK), (0.75, KICK), (2, SNARE)])
    notes = bar_lines(tex, 1)[:3]
    assert r'\ibbl1{f}0\roff{\tbbl1}' in notes[0]
    assert r'\tbbl1\q@symbol\@tqb1{f}' in notes[2]


def test_dots_precede_the_note(tmp_path):
    tex = tex_for(tmp_path, [(0, SNARE), (0.75, SNARE), (2, KICK)])
    first = bar_lines(tex, 1)[0]
    assert first.index(r'\pt{j}') < first.index(r'\ibu0{j}0') < first.index(r'\@qb0{j}')


def test_dotted_chord_dots_every_head(tmp_path):
    tex = tex_for(tmp_path, [(0, SNARE), (0, HH), (0.75, SNARE), (2, KICK)])
    first = bar_lines(tex, 1)[0]
    assert first.index(r'\pt{j}') < first.index(r'\@zq{j}')
    assert first.index(r'\pt{n}') < first.index(r'\@qb0{n}')


def test_measure_rest_uses_centerpause(tmp_path):
    tex = tex_for(tmp_path, [(0, KICK), (8, KICK)])
    lines = bar_lines(tex, 2)
    assert lines == [r'\vnotes7\elemskip\en', r'\def\atnextbar{\znotes\centerpause\en}']
    assert r'\centerHpause' not in tex


def test_multi_bar_rest_uses_centerhpause(tmp_path):
    tex = tex_for(tmp_path, [(0, KICK), (16, KICK)])
    assert '% bar 2-4' in tex
    assert r'\def\atnextbar{\znotes\centerHpause{3}\en}' in tex
    assert r'\global\advance\barno by 2' in tex
    assert r'\centerpause' not in tex


def test_pickup_sets_startbarno(tmp_path):
    tex = tex_for(tmp_path, [(0, SNARE), (1, KICK)], {'pickup_beats': 1, 'source_leading_beats': 1})
    assert r'\startbarno=0' in tex
    assert tex.index(r'\startbarno=0') < tex.index(r'\startpiece')
    assert r'\generalmeter{\meterfrac{1}{4}}' in tex
    assert '% bar 0 (pickup)' in tex
    assert r'\generalmeter{\meterfrac{4}{4}}' in tex
    no_pickup = tex_for(tmp_path, [(0, SNARE)])
    assert r'\startbarno' not in no_pickup


def test_silent_pickup_prints_rests(tmp_path):
    tex = tex_for(tmp_path, [(4, KICK)], {'pickup_beats': 2, 'source_leading_beats': 4})
    assert bar_lines(tex, 0) == [r"\vnotes5.00\elemskip\hpause\en"]


def test_meter_change_uses_changecontext(tmp_path):
    tex = tex_for(tmp_path, [(b, HH) for b in range(7)], sigs=[(0, 4, 4), (4, 3, 4)])
    assert '\\generalmeter{\\meterfrac{3}{4}}\n\\changecontext' in tex or \
        '\\generalmeter{\\meterfrac{3}{4}}\n\\alaligne' in tex


def test_triplet_label_and_open_hat(tmp_path):
    tex = tex_for(tmp_path, [(i / 3, RIDE) for i in range(3)] + [(1, HHO), (2, KICK)])
    notes = bar_lines(tex, 1)
    assert r'\def\txt{3}\butext0' in notes[1]
    assert r'\ccharnote{q}{$\circ$}' in notes[3]  # open mark three steps above the hi-hat space


def test_sextuplet_label(tmp_path):
    tex = tex_for(tmp_path, [(i / 6, SNARE) for i in range(6)] + [(2, KICK)])
    assert r'\def\txt{6}\butext0' in tex


def test_grace_ghost_accent(tmp_path):
    hits = [(0, KICK), (1 - 40 / 480, SNARE, 30), (1, SNARE, 90), (2, SNARE, 20), (3, SNARE, 127)]
    tex = tex_for(tmp_path, hits, {'dynamics': {'ghost_below': 40, 'accent_above': 110}})
    assert r'\notes\multnoteskip\smallvalue\smallnotesize\q@symbol\@grcu{j}\en' in tex
    assert r'\lpar{j}\rpar{j}' in tex
    assert r'\usf{' in tex


def test_output_is_ascii_and_complete(song):
    tex = convert(song)
    tex.encode('ascii')
    assert tex.startswith(r'\input musixtex')
    assert tex.rstrip().endswith(r'\bye')
    assert r'\startbarno=0' in tex
    assert tex.count('% bar ') <= len(song.bars)
    assert r'\generalmeter{\meterfrac{2}{4}}' in tex and r'\generalmeter{\meterfrac{4}{4}}' in tex


def test_header_space(song):
    assert r'\hbox{}\vskip123.4pt' in convert(song, header_space=123.4)


def test_legend(song):
    entries = legend_entries(song)
    tex = legend_tex(song)
    assert tex.count(r'\startpiece') == len(entries)
    ids = [inst.id for _notes, inst in entries]
    assert len(ids) == len(set(ids))
    # FPC 38/40 both print as the snare and are merged into one legend entry
    notes = {inst.id: n for n, inst in entries}
    assert 40 in notes['snare']
