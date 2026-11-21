#!/usr/bin/env python3
"""一条命令：鼓 MIDI + 元数据 → score.musicxml + score.pdf，并逐项校验。

    python3 scripts/build_score.py song.mid --metadata metadata.yaml --out-dir build/song

输出目录里会有：
  score.musicxml   可编辑的 MusicXML 4.0（MuseScore 等可直接打开）
  score.pdf        打印用 A4 鼓谱（标题等文字可复制，谱面为矢量）
任何一步失败都以非零退出码结束，并说明需要改什么（MIDI、元数据或鼓映射）。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from score_core import ScoreError, build_score
import midi_to_musicxml
import render_score
import validate_score


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='鼓 MIDI + 元数据 → MusicXML + PDF（含校验）')
    parser.add_argument('midi', type=Path, help='鼓 MIDI 文件（FL Studio FPC 导出、GM 第 10 通道等均可）')
    parser.add_argument('--metadata', type=Path, required=True, help='曲目元数据 YAML，见 docs/metadata.md')
    parser.add_argument('--out-dir', type=Path, required=True, help='输出目录')
    parser.add_argument('--drum-map', help='覆盖元数据中的鼓映射：内置名（gm、fpc-default）或 YAML 路径')
    parser.add_argument('--track', action='append', help='只用名称包含该文字的轨道（可重复）')
    parser.add_argument('--channel', action='append', type=int, help='只用该 MIDI 通道 1–16（可重复）')
    parser.add_argument('--no-pdf', action='store_true', help='只生成 MusicXML（不需要 TeX 环境）')
    parser.add_argument('--work-dir', type=Path, help='保留 PDF 中间文件（TeX 源码、未合成的谱页）的目录')
    parser.add_argument('--xsd', type=Path, default=validate_score.default_xsd(),
                        help='MusicXML 4.0 XSD 路径（也可设环境变量 MUSICXML_XSD）；提供时做 schema 校验')
    args = parser.parse_args(argv)

    try:
        score = build_score(args.midi, args.metadata, args.drum_map,
                            cli={'tracks': args.track, 'channels': args.channel})
    except ScoreError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2
    for warning in score.warnings:
        print(f'提示：{warning}', file=sys.stderr)
    print(score.summary())

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    musicxml = out / 'score.musicxml'
    midi_to_musicxml.write(score, musicxml)
    pdf = out / 'score.pdf'
    try:
        if not args.no_pdf:
            if args.work_dir:
                args.work_dir.mkdir(parents=True, exist_ok=True)
                info = render_score.render(score, pdf, args.work_dir.resolve())
            else:
                with tempfile.TemporaryDirectory(prefix='drum-score-') as temp:
                    info = render_score.render(score, pdf, Path(temp))
            print(f'{pdf}: A4 {info["pages"]} 页')
        print(f'{musicxml}')
        print(validate_score.validate_musicxml(score, musicxml, args.xsd))
        if not args.no_pdf:
            print(validate_score.validate_pdf(score, pdf))
    except RuntimeError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return 2
    except validate_score.ValidationError as exc:
        print(f'校验失败：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
