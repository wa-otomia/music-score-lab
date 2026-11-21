# music-score-lab

A multi-song drum transcription archive and reproducible MIDI → MusicXML → PDF toolchain. Designed for use by humans and coding agents (Codex, Claude Code, Gemini CLI, etc.).

中文：这个仓库用于保存多首歌曲的鼓谱、原始 MIDI、可编辑 MusicXML、打印用 PDF，以及自动转谱脚本。**不是**某一首歌曲的专用仓库。

## Directory layout

```text
AGENTS.md                         Agent instructions (source of truth)
CLAUDE.md                         Imports AGENTS.md for Claude Code
configs/japanese-drums.yaml       Instrument note mapping and head style
scripts/                           Shared Python converters + validator
tests/                             Executable converter tests
docs/notation-conventions.md       Japanese-style percussion notation
scores/<song-slug>/                One folder for each arrangement
  metadata.yaml                   Credits, tempo, pickup and offsets
  source.mid                      Original user input
  score.musicxml                  Editable score
  score.pdf                       Print-ready PDF
```

## Example score

[命に嫌われている。](scores/inochi-ni-kirawareteiru/README.md) — original composition / vocals by カンザキイオリ; album『不器用な男』; drum transcription and arrangement by 音宮, containing reconstructed/original material. This is a user-created fan transcription, **not** an official score.

## Requirements

- Python 3.10+ and packages from `requirements.txt`
- [MusiXTeX](https://www.ctan.org/pkg/musixtex), including `musixtex` and `musixper` (part of the TeX Live music packages)
- Ghostscript (needed for the MusiXTeX PDF toolchain)
- XeLaTeX with `fontspec` / `xeCJK`, **Inkscape** CLI (`--export-text-to-path`), and locally installed **Noto Sans CJK JP** fonts
- Optional: MuseScore for manual editing of MusicXML

On Debian/Ubuntu, install the relevant packages (typically `texlive-music`, `texlive-xetex`, `texlive-lang-japanese`, `inkscape`, `ghostscript`, `fonts-noto-cjk`). Exact names may vary by distribution. No font binaries are shipped in this repository.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Reproduce / regenerate

```bash
SONG=scores/inochi-ni-kirawareteiru
mkdir -p build
python scripts/midi_to_musicxml.py "$SONG/gm-channel10.mid" \
  --metadata "$SONG/metadata.yaml" --out build/score.musicxml
python scripts/render_score.py "$SONG/gm-channel10.mid" \
  --metadata "$SONG/metadata.yaml" --out build/score.pdf
python scripts/validate_score.py "$SONG/gm-channel10.mid" \
  --metadata "$SONG/metadata.yaml" --musicxml build/score.musicxml --pdf build/score.pdf
python -m pytest -q tests
```

FL Studio/FPC may export on MIDI channel 1. For compatibility with players expecting General MIDI percussion on channel 10, optionally retag **a copy**:

```bash
python scripts/retag_gm_channel10.py "$SONG/source.mid" --out build/gm-channel10.mid
```

This does not move notes or modify the source file. The converters themselves do not require MIDI channel 10.

Japanese titles and credits are typeset using XeLaTeX then converted to **font-independent vector outlines** before they are merged with the MusiXTeX score. This avoids Japanese text corruption in browser PDF previews and Mac Preview; the notation itself stays vector. The opening silent bar is explicitly `2/4`, followed by `4/4`. Open hi-hat circles track their notehead positions.

Do not automatically replace checked-in arrangements with newly generated output: inspect rendered pages and compare the result first. The tools output new files to `build/` by default. `--keep-tex build/score.tex` retains editable TeX for debugging.

### Add a new song

Create `scores/<song-slug>/metadata.yaml` (copy one as a template), put the *original* MIDI in `source.mid`, update `configs/japanese-drums.yaml` for missing GM pitches, and run the tools above with that song's paths. Every source score has its own rights and attribution.

## How agents should work

Read [AGENTS.md](AGENTS.md) before changing any score or converter. Claude Code follows [CLAUDE.md](CLAUDE.md), which imports the same instructions; other agents may read `AGENTS.md` directly. All contributors must preserve file provenance, perform MusicXML validation and render/inspect PDF pages.

## Licensing and rights

The code/documentation in this repository can be reused under the MIT license (`LICENSE`). **That license excludes `scores/` and all third-party musical works.** Song copyrights and distribution rights remain with their respective rights holders. Transcribing or crediting a song is not authorization to publish it; confirm redistribution permission before making copyrighted scores publicly accessible. No assumption is made that any scores have been authorized for public redistribution.
