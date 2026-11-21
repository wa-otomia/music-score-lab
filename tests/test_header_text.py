"""Title-block text (render_score.header_text) as documented in docs/metadata.md; no TeX needed."""
import pytest

from conftest import KICK, build
from render_score import escape_tex, expected_page_text, header_text, merged_roles, ROLE_LABELS


@pytest.mark.parametrize('meta, roles, line', [
    ({'lyricist': 'A', 'composer': 'A', 'vocal': 'B'}, ['lyricist', 'composer', 'vocal'], '作詞・作曲：A　歌：B'),
    ({'lyricist': 'A', 'composer': 'B'}, ['lyricist', 'composer', 'vocal'], '作詞：A　作曲：B'),
    ({'transcriber': 'C', 'arranger': 'C'}, ['transcriber', 'arranger'], 'ドラム採譜・編曲：C'),
    ({'transcriber': 'C', 'arranger': 'D'}, ['transcriber', 'arranger'], 'ドラム採譜：C　ドラム編曲：D'),
    ({'transcriber': ' C ', 'arranger': 'C'}, ['transcriber', 'arranger'], 'ドラム採譜・編曲：C'),
    ({'vocal': 'A（セルフカバー）', 'composer': 'A'}, ['lyricist', 'composer', 'vocal'], '作曲：A　歌：A（セルフカバー）'),
])
def test_merged_roles(meta, roles, line):
    assert merged_roles(meta, roles, ROLE_LABELS) == line


def test_header_lines_and_credits(tmp_path):
    meta = {'title': 'T', 'subtitle': 'S', 'artist': 'A', 'album': 'X', 'lyricist': 'A', 'composer': 'A',
            'vocal': 'V', 'transcriber': 'C', 'note': 'N', 'credits': {'vocal': 'ボーカル', 'title': 'ignored'},
            'copyright': '© 2026'}
    score = build(tmp_path, [(0, KICK)], meta, sigs=[(0, 4, 4)], tempo=150)
    h = header_text(score)
    assert h.title == 'T'
    assert [t for _s, t in h.lines] == ['S', 'A　『X』', '作詞・作曲：A　ボーカル：V', 'ドラム採譜：C', '備考：N',
                                        'BPM 150　拍子 4/4　上声部（符尾上）＝手　下声部（符尾下）＝足']
    assert h.running == 'T　A　ドラム譜'
    assert h.footer_note == '© 2026'
    pages = expected_page_text(score, 2)
    assert pages[0][-2:] == ['1 / 2', '© 2026']
    assert '凡例' in pages[0]
    assert pages[1] == ['T　A　ドラム譜', '2 / 2']


def test_untitled_and_no_legend(tmp_path):
    score = build(tmp_path, [(0, KICK)], {'title': None, 'legend': False}, sigs=[(0, 4, 4)])
    h = header_text(score)
    assert h.title == 'Untitled' and h.running == 'Untitled　ドラム譜'
    assert '凡例' not in expected_page_text(score, 1)[0]


def test_meter_summary_with_pickup(song):
    assert header_text(song).lines[-1][1].startswith('BPM 200　拍子 2/4（弱起） → 4/4　')


def test_meter_summary_truncated(tmp_path):
    sigs = [(0, 4, 4), (4, 3, 4), (7, 2, 4), (9, 5, 4), (14, 4, 4)]
    score = build(tmp_path, [(b, KICK) for b in range(18)], sigs=sigs)
    assert '拍子 4/4 → 3/4 → 2/4 → …　' in header_text(score).lines[-1][1]


def test_escape_tex():
    assert escape_tex(r'50% & $5 #1 a_b {x} ~ ^ \ ') == \
        r'50\% \& \$5 \#1 a\_b \{x\} \textasciitilde{} \textasciicircum{} \textbackslash{}'


def test_escape_tex_collapses_line_breaks():
    # a blank line inside a TeX argument would end the paragraph and break the build
    assert escape_tex('Para\n\ntitle\t x') == 'Para title x'
    assert escape_tex('曲名　アーティスト') == '曲名　アーティスト'  # ideographic space is kept
