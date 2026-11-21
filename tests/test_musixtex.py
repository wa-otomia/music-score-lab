import re

import pytest

from conftest import HAVE_PDF_TOOLS, HH, HHO, KICK, RIDE, SNARE, build, make_midi
import build_score
import midi_to_musixtex
from midi_to_musixtex import bar_number_pitch, convert, convert_with_layout, legend_entries, legend_tex
import render_score
from score_core import ScoreError
from validate_score import validate_pdf

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
    # cross heads use the arm-tip stem routines (\@xqb), see test_cross_head_stems_start_at_arm_tip
    assert r'\@xqb0{n}' in notes[1] and r'\@xqb0{n}' in notes[2]
    assert r'\@xtqh0{n}' in notes[3]


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
    # up-stem chords carry the stem on the lowest head; every head gets its own dot first
    assert first.index(r'\pt{n}') < first.index(r'\@zq{n}')
    assert first.index(r'\pt{j}') < first.index(r'\@qb0{j}')


def test_measure_rest_uses_centerpause(tmp_path):
    tex = tex_for(tmp_path, [(0, KICK), (8, KICK)])
    lines = bar_lines(tex, 2)
    assert lines == [r'\znotes\barnum{13}{2}\en', r'\vnotes7\elemskip\en', r'\def\atnextbar{\znotes\centerpause\en}']
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


def _groove_a(offset: float) -> list[tuple]:
    return [(offset + x / 2, HH) for x in range(8)] + [(offset, KICK), (offset + 1, SNARE), (offset + 3, SNARE)]


def _groove_b(offset: float) -> list[tuple]:
    return [(offset + x / 2, RIDE) for x in range(8)] + [(offset, KICK), (offset + 2, KICK), (offset + 1, SNARE), (offset + 3, SNARE)]


def test_mid_system_bar_numbers_all_unit_kinds_and_pickup(tmp_path):
    # Pickup bar 0 (system start), bar 1 after \changecontext, bar 2 (%), bar 3 (normal B),
    # bar 4 (normal A), bar 5 (normal B), bars 6-7 (simile-2 //), bars 8-10 (multi-rest),
    # bar 11 (HHO on beat 1 -> lifted pitch), bar 12 (empty single bar), bar 13 (normal A).
    hits = [(0, SNARE), (1, SNARE)]
    specs = [
        _groove_a, _groove_a, _groove_b, _groove_a, _groove_b, _groove_a, _groove_b,
        None, None, None,
        lambda o: [(o, HHO), (o + 1, SNARE), (o + 2, KICK), (o + 3, SNARE)],
        None,
        _groove_a,
    ]
    for i, fn in enumerate(specs):
        if fn is not None:
            hits.extend(fn(2 + 4 * i))
    score = build(tmp_path, hits, meta={'pickup_beats': 2, 'source_leading_beats': 2},
                  sigs=[(0, 2, 4), (2, 4, 4)])
    tex, systems = convert_with_layout(score)
    tex.encode('ascii')

    # Verify pickup 0 is system start (no \barnum) and bar 1 right after \changecontext has \barnum{...}{1}.
    assert systems[0][0].printed_start == 0
    assert systems[0][1].printed_start == 1
    assert r'\barnum' not in '\n'.join(bar_lines(tex, 0))
    assert any(re.fullmatch(r'\\znotes\\barnum\{\d+\}\{1\}\\en', l) for l in bar_lines(tex, 1))

    # Extract each '% bar ...' block from the score body and match 1-to-1 with flattened units.
    body = tex.split(r'\startpiece', 1)[1].split(r'\setdoubleBAR', 1)[0]
    raw_blocks = re.split(r'(?m)^(?=% bar )', body)[1:]
    flat_units = [u for sys_u in systems for u in sys_u]
    start_ids = {id(sys_u[0]) for sys_u in systems}
    assert len(raw_blocks) == len(flat_units)

    seen_kinds = set()
    for unit, blk in zip(flat_units, raw_blocks):
        seen_kinds.add(unit.kind)
        bn_matches = re.findall(r'\\barnum\{(\d+)\}\{(\d+)\}', blk)
        if id(unit) in start_ids:
            assert bn_matches == [], f'system-start unit {unit.printed_start} should not emit \\barnum'
        else:
            assert len(bn_matches) == 1, f'mid-system unit {unit.printed_start} ({unit.kind}) got {bn_matches}'
            assert int(bn_matches[0][1]) == unit.printed_start
        if unit.kind == 'simile-2':
            # Never print a bar number on the interior middle barline where \similetwo sits.
            after_interior = blk.split(r'\def\atnextbar{\znotes\similetwo\en}%', 1)[1]
            assert r'\barnum' not in after_interior

    assert {'bar', 'simile-1', 'simile-2', 'multi-rest'} <= seen_kinds

    # Bar 11 has open hi-hat on beat 1 with 2-digit number -> bar_number_pitch lifts clear of open mark.
    u11 = next(u for u in flat_units if u.printed_start == 11)
    assert bar_number_pitch(u11) >= 15


@pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs musixtex, etex, musixflx, dvipdfmx, xelatex, gs')
def test_pdf_mid_system_bar_numbers_validate_cleanly(tmp_path):
    # Mix pickup, normal bars, %, //, multi-rest, empty bar, and HHO; test both default and opt-in repeat_counters.
    hits = [(0, SNARE), (1, SNARE)]
    specs = [
        _groove_a, _groove_a, _groove_a, _groove_b,
        _groove_a, _groove_b, _groove_a, _groove_b,
        None, None, None,
        lambda o: [(o, HHO), (o + 1, SNARE), (o + 2, KICK), (o + 3, SNARE)],
        None,
        _groove_a,
    ]
    for i, fn in enumerate(specs):
        if fn is not None:
            hits.extend(fn(2 + 4 * i))
    for counters in (False, True):
        sub = tmp_path / f'cnt-{counters}'
        sub.mkdir()
        meta = {'title': f'Bar Numbers Check {counters}', 'pickup_beats': 2, 'source_leading_beats': 2,
                'notation': {'repeat_counters': counters}}
        score = build(sub, hits, meta=meta, sigs=[(0, 2, 4), (2, 4, 4)])
        out = sub / 'score.pdf'
        work = sub / 'work'
        work.mkdir()
        render_score.render(score, out, work)
        assert validate_pdf(score, out).startswith('PDF OK')
        log = (work / 'score.log').read_text(errors='replace')
        overfull = [float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
        assert not overfull or max(overfull) <= 4.0
        tex = (work / 'score.tex').read_text(encoding='ascii')
        assert r'\barnum{' in tex
        if counters:
            assert r'\csimile{' in tex.split(r'\startpiece', 1)[1]
        else:
            assert r'\csimile{' not in tex.split(r'\startpiece', 1)[1]


def test_system_spacing_tex_emission_and_cli(tmp_path):
    score_def = build(tmp_path, _groove_a(0), **FOUR_FOUR)
    tex_def = convert(score_def)
    tex_def.encode('ascii')
    pre_def = tex_def.split(r'\startpiece', 1)[0]
    assert r'\stafftopmarg=3.30\Interligne' in pre_def
    assert r'\staffbotmarg=3.30\Interligne' in pre_def
    assert r'\parskip=0.60\Interligne plus5\Interligne minus\Interligne' in pre_def

    # Stock 1.0 omits all three spacing macros verbatim.
    score_stock = build(tmp_path, _groove_a(0), meta={'notation': {'system_spacing': 1.0}}, **FOUR_FOUR)
    for tex_1 in (convert(score_stock), convert(score_def, system_spacing=1.0)):
        pre_1 = tex_1.split(r'\startpiece', 1)[0]
        assert r'\stafftopmarg' not in pre_1
        assert r'\staffbotmarg' not in pre_1
        assert r'\parskip' not in pre_1

    # Tight (< 1.0) clamps \parskip base to 0.00\Interligne; loose (> 1.0) expands margins and \parskip.
    pre_tight = convert(score_def, system_spacing=0.85).split(r'\startpiece', 1)[0]
    assert r'\stafftopmarg=2.55\Interligne' in pre_tight
    assert r'\staffbotmarg=2.55\Interligne' in pre_tight
    assert r'\parskip=0.00\Interligne plus5\Interligne minus\Interligne' in pre_tight

    pre_loose = convert(score_def, system_spacing=1.5).split(r'\startpiece', 1)[0]
    assert r'\stafftopmarg=4.50\Interligne' in pre_loose
    assert r'\staffbotmarg=4.50\Interligne' in pre_loose
    assert r'\parskip=3.00\Interligne plus5\Interligne minus\Interligne' in pre_loose

    with pytest.raises(ScoreError):
        convert(score_def, system_spacing=3.0)

    # CLI --system-spacing override on midi_to_musixtex and build_score.
    midi = make_midi(tmp_path / 'sp.mid', _groove_a(0), **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: Spacing CLI\nnotation:\n  system_spacing: 0.9\n', encoding='utf-8')

    out_tex = tmp_path / 'sp.tex'
    assert midi_to_musixtex.main([str(midi), '--metadata', str(meta), '--out', str(out_tex),
                                  '--system-spacing', '1.5']) == 0
    assert r'\stafftopmarg=4.50\Interligne' in out_tex.read_text(encoding='ascii')
    assert midi_to_musixtex.main([str(midi), '--metadata', str(meta), '--out', str(out_tex),
                                  '--system-spacing', '0.5']) == 2

    out_dir = tmp_path / 'build-sp'
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out_dir),
                             '--no-pdf', '--system-spacing', '1.4']) == 0
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out_dir),
                             '--no-pdf', '--system-spacing', 'bad']) == 2


@pytest.mark.skipif(not HAVE_PDF_TOOLS, reason='needs musixtex, etex, musixflx, dvipdfmx, xelatex, gs')
def test_pdf_system_spacing_tight_vs_loose_and_cli(tmp_path):
    import pymupdf

    # 44 distinct-enough bars (~11 systems): 0.85 fits on 1 page while 1.5 expands spacing & spills to 2 pages.
    hits: list[tuple] = []
    for i in range(44):
        fn = _groove_a if i % 2 == 0 else _groove_b
        hits.extend(fn(4 * i))
    midi = make_midi(tmp_path / 'sp44.mid', hits, **FOUR_FOUR)
    meta = tmp_path / 'meta.yaml'
    meta.write_text('title: System Spacing PDF Test\n', encoding='utf-8')

    def measure_pdf(pdf_path):
        gaps: list[float] = []
        with pymupdf.open(pdf_path) as doc:
            pages = len(doc)
            for page in doc:
                ys = sorted(set(round(d['rect'].y0, 2) for d in page.get_drawings()
                                if d['rect'].width > 400 and d['rect'].height < 1.5))
                groups: list[list[float]] = []
                for y in ys:
                    if not groups or y - groups[-1][-1] > 10.0:
                        groups.append([y])
                    else:
                        groups[-1].append(y)
                staves = [g for g in groups if len(g) >= 4]
                for a, b in zip(staves, staves[1:]):
                    gaps.append(b[0] - a[-1])
        return pages, sum(gaps) / len(gaps)

    pdf_tight = tmp_path / 'tight.pdf'
    work_tight = tmp_path / 'work-tight'
    assert render_score.main([str(midi), '--metadata', str(meta), '--out', str(pdf_tight),
                              '--work-dir', str(work_tight), '--system-spacing', '0.85']) == 0
    s_tight = build_score.build_score(midi, meta, cli={'system_spacing': '0.85'})
    assert validate_pdf(s_tight, pdf_tight).startswith('PDF OK')

    out_loose = tmp_path / 'build-loose'
    work_loose = tmp_path / 'work-loose'
    assert build_score.main([str(midi), '--metadata', str(meta), '--out-dir', str(out_loose),
                             '--work-dir', str(work_loose), '--system-spacing', '1.5']) == 0
    pdf_loose = out_loose / 'score.pdf'
    s_loose = build_score.build_score(midi, meta, cli={'system_spacing': '1.5'})
    assert validate_pdf(s_loose, pdf_loose).startswith('PDF OK')

    for wdir in (work_tight, work_loose):
        log = (wdir / 'score.log').read_text(errors='replace')
        overfull = [float(x) for x in re.findall(r'Overfull \\hbox \(([\d.]+)pt too wide\)', log)]
        assert not overfull or max(overfull) <= 4.0

    pages_tight, gap_tight = measure_pdf(pdf_tight)
    pages_loose, gap_loose = measure_pdf(pdf_loose)
    assert pages_loose > pages_tight
    assert gap_loose > gap_tight + 10.0
