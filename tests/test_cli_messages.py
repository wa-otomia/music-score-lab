"""CLI error output is English (spec cli/messages): key info present, exit code 2, no CJK."""
from __future__ import annotations

import re

import pytest
import yaml

from conftest import KICK, SNARE, make_midi
import build_score

CJK = re.compile(r'[⺀-⿿　-ヿ㐀-鿿豈-﫿＀-￯]')
FOUR = {'sigs': [(0, 4, 4)]}


def run(tmp_path, capsys, hits, meta, **midi_kw):
    midi = make_midi(tmp_path / 'in.mid', hits, **midi_kw)
    meta_path = tmp_path / 'meta.yaml'
    meta_path.write_text(yaml.safe_dump({'title': 'Test', **meta}, allow_unicode=True), encoding='utf-8')
    code = build_score.main([str(midi), '--metadata', str(meta_path), '--out-dir', str(tmp_path / 'out'), '--no-pdf'])
    return code, capsys.readouterr().err


CASES = [
    ('time_signature mismatch', [(0, KICK)], {'time_signature': '3/4'}, ['Error:', '3/4', '4/4', 'time_signature']),
    ('unmapped note', [(0, KICK), (1, 90)], {}, ['Error:', '90', 'beat 2', 'note_map: {90: hand-clap}']),
    ('unnotatable 32nd rhythm', [(0, SNARE), (0.125, SNARE), (1, KICK)], {},
     ['Error:', 'beat 1', 'hand voice', 'Quantize']),
    ('legend as string', [(0, KICK)], {'legend': 'yes'}, ['Error:', 'legend', 'true or false']),
]


@pytest.mark.parametrize('label, hits, meta, keywords', CASES, ids=[c[0] for c in CASES])
def test_bad_input_reports_english_error(tmp_path, capsys, label, hits, meta, keywords):
    code, err = run(tmp_path, capsys, hits, meta, **FOUR)
    assert code == 2
    for keyword in keywords:
        assert keyword in err, err
    assert not CJK.search(err), err


def test_user_data_is_quoted_verbatim(tmp_path, capsys):
    title = '命に嫌われている。'
    midi = make_midi(tmp_path / 'in.mid', [(0, KICK)], **FOUR)
    meta_path = tmp_path / 'meta.yaml'
    meta_path.write_text(yaml.safe_dump({'title': title}, allow_unicode=True), encoding='utf-8')
    code = build_score.main([str(midi), '--metadata', str(meta_path), '--out-dir', str(tmp_path / 'out'), '--no-pdf'])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert f'"{title}": 1 bar, 1 note engraved' in captured.out
    assert not CJK.search(captured.out.replace(title, '')) and not CJK.search(captured.err)


@pytest.mark.parametrize('script', ['build_score', 'render_score', 'midi_to_musicxml', 'midi_to_musixtex',
                                     'validate_score', 'retag_gm_channel10'])
def test_help_is_english(script, capsys):
    module = __import__(script)
    with pytest.raises(SystemExit) as exc:
        import sys
        old, sys.argv = sys.argv, [script, '--help']
        try:
            module.main()
        finally:
            sys.argv = old
    assert exc.value.code == 0
    assert not CJK.search(capsys.readouterr().out)
