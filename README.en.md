[日本語](README.md) | [简体中文](README.zh-CN.md) | [English](README.en.md)

# music-score-lab

Converts drum MIDI and a per-song metadata file (YAML) into two deliverables:

- `score.musicxml`: editable MusicXML 4.0 that MuseScore and similar software can open directly for further editing.
- `score.pdf`: an A4 printable drum score in Japanese-style notation. The notation is vector graphics, and text such as the title can be selected, copied and searched.

This repository holds the source MIDI, metadata and deliverables for many songs. It is **not** dedicated to a single song.
Humans and coding agents (Claude Code, Codex, etc.) follow the same rules; see [AGENTS.md](AGENTS.md).

## Quick start

```bash
python3 scripts/build_score.py scores/inochi-ni-kirawareteiru/source.mid \
  --metadata scores/inochi-ni-kirawareteiru/metadata.yaml \
  --out-dir build/inochi
```

This single command reads the MIDI → quantizes and splits it into bars → writes `build/inochi/score.musicxml` → typesets `build/inochi/score.pdf`
→ validates both outputs. The screen shows one line of the form `"<title>": <summary>` with the number of bars, notes, grace notes and merged duplicate triggers, plus all notes (printed as `Note: …`).

| Exit code | Meaning |
| --- | --- |
| 0 | Generated and validated successfully |
| 1 | Validation failed: the output does not match the notation model (bad MusicXML content, or PDF text or fonts) |
| 2 | Problem with the input or environment: the MIDI / metadata is wrong or cannot be notated faithfully (unmapped notes, unsupported time signatures or rhythms, etc.), the title or other text cannot be printed or copied, an external command is missing, the XSD file is missing or cannot be read or parsed, or lxml is missing. The error message says what to fix |

Common options:

| Option | Effect |
| --- | --- |
| `--drum-map NAME_OR_PATH` | Overrides `drum_map` in the metadata (built-in `gm`, `fpc-default`, or a YAML path) |
| `--track TEXT` | Uses only tracks whose name contains the text (case-insensitive, repeatable) |
| `--channel N` | Uses only MIDI channel N (1–16, repeatable) |
| `--no-pdf` | Generates and validates only the MusicXML; no TeX environment needed |
| `--legend` / `--no-legend` | Prints / omits the instrument legend on the first page. If neither is given, the metadata `legend` applies; if the metadata does not set it either, no legend is printed |
| `--repeats MODE` | Sets repeat notation mode (`off`, `simile`, `full`); overrides `notation.repeats` in metadata (default: `simile`) |
| `--beam-eighths MODE` | Sets 8th-note beaming mode (`beat`, `half-bar`); overrides `notation.beam_eighths` in metadata (default: `beat`) |
| `--work-dir DIR` | Keeps the PDF intermediate files (TeX source, uncomposited score pages) for troubleshooting |
| `--xsd PATH` | Path to the MusicXML 4.0 `musicxml.xsd`; the environment variable `MUSICXML_XSD` also works. When given, an additional schema validation is run (requires lxml) |

## Requirements

- Python 3.10 or later. The Python packages are listed in `requirements.txt` (mido, PyYAML, PyMuPDF; lxml is needed only for XSD validation, and the tests use it too).
- Producing the PDF requires: MusiXTeX (including the musixper percussion noteheads), XeLaTeX + fontspec + xeCJK + pdfpages, Ghostscript,
  and the Noto Sans CJK JP font installed on the machine. The repository ships no font files.
- Optional: poppler-utils (`pdffonts` for font checks, `pdftoppm` for rendering previews), the MusicXML 4.0 XSD (schema validation), MuseScore (for editing MusicXML).

On Debian / Ubuntu:

```bash
sudo apt install texlive-music texlive-xetex texlive-lang-cjk texlive-latex-recommended \
  ghostscript poppler-utils fonts-noto-cjk python3-mido python3-yaml python3-pymupdf python3-lxml
# Running the tests also needs:
sudo apt install python3-pytest
```

You can also use a virtual environment: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt pytest`
(TeX, Ghostscript and the fonts still have to be installed as system packages).

The MusicXML 4.0 XSD is not in the repository. When you need schema validation, get `musicxml.xsd` from the W3C MusicXML 4.0 release package,
then `export MUSICXML_XSD=/path/to/musicxml.xsd`. When it is not set, schema validation is skipped and all other validation runs as usual.

## Directory layout

```text
AGENTS.md                      Rules for agents and contributors (CLAUDE.md is a single line, @AGENTS.md)
configs/instruments.yaml       Instrument catalog: staff position, notehead, open/closed marks, Japanese name, legend abbreviation
configs/drum-maps/gm.yaml      General MIDI / GS percussion map (note numbers 27–87)
configs/drum-maps/fpc-default.yaml  FL Studio FPC default layout (inherits gm)
docs/metadata.md               Metadata field reference
docs/drum-maps.md              Instrument catalog and drum map reference
docs/notation-conventions.md   The Japanese-style drum notation implemented by this repository
templates/metadata.yaml        Metadata template for a new song
scripts/build_score.py         Main entry point: MusicXML + PDF and validation in one command
scripts/score_core.py          Shared notation model: track selection, mapping, quantization, bars, voices, rests, beams
scripts/score_structure.py     Shared structural planning: multi-measure rests, repeats (% / // / |: :| / 1. 2.), section breaks
scripts/midi_to_musicxml.py    Model → MusicXML
scripts/midi_to_musixtex.py    Model → MusiXTeX source
scripts/render_score.py        MusiXTeX → Ghostscript outlining → XeLaTeX composition → PDF
scripts/pdf_tounicode.py       Fixes the PDF ToUnicode map so every reader copies the correct text
scripts/validate_score.py      Checks that the MusicXML / PDF is faithful to the model
scripts/retag_gm_channel10.py  Copies a MIDI file and retags it to channel 10 (not needed for the conversion itself)
tests/                         pytest tests
scores/<song slug>/            One directory per song (see below)
build/                         Local output directory, ignored by .gitignore
```

## What the PDF looks like

- The top of the first page is a Japanese title block: the song title, the subtitle, `アーティスト　『アルバム』`, `作詞・作曲：…　歌：…`,
  `ドラム採譜・編曲：…`, `備考：…`, and a last line with the tempo `BPM 200`.
  Several roles held by the same person are merged into one label; see [docs/metadata.en.md](docs/metadata.en.md) for the rules.
- **Legend** (not printed by default): with `legend: true` in the metadata or `--legend` on the command line, the instruments actually used in the song are printed below the title block.
  Each entry is a notehead on a short staff, with its abbreviation and Japanese name underneath. `--no-legend` turns it off temporarily when the metadata enables it.
- Continuation pages print `<song title>　<artist>　ドラム譜` at the top and the page number `n / N` at the bottom; if the metadata has `copyright`, it is printed at the bottom of the first page.
- The score (notes, rests, bar numbers, time signatures, tempo marks, repeat marks, boxed rehearsal marks) is entirely vector paths and stays sharp at any zoom. The **only** copyable text is the title block, the legend,
  the running header, the page number and the copyright line, in an embedded subset of Noto Sans CJK JP. No space is inserted automatically between kanji, kana and Latin letters; spaces written in the metadata are printed as they are (exception: a half-width space right after full-width punctuation such as 、。）」, or between kana/kanji and a full-width parenthesis, is neither printed nor copied, following Japanese typesetting rules):
  pdftotext and pdf.js keep these half-width spaces when copying, so the copied credits match the metadata. A full-width space (U+3000, including the full-width spaces separating the items in the title block),
  however, is copied as a half-width space by pdftotext and pdf.js; PyMuPDF keeps U+3000 but drops half-width spaces next to kanji and kana. Validation extracts the text both via ActualText (used by Poppler, MuPDF, Chrome's PDFium, etc.)
  and via ToUnicode (used by pdf.js, Preview, etc.) and compares it with the expected text (after NFC normalization and removal of all whitespace,
  so only characters and their order are checked, not spaces or line breaks).
- Line breaks use phrase-aligned optimization (preferring 4-bar phrases and section/repeat boundaries; when pickup bar 0 is present it stays with bars 1–4 on line 1, and the final line may also hold up to 5 bars; a multi-measure rest counts as 1 bar and a 2-bar simile `//` counts as 2 bars without splitting). Each system starts with its bar number (pickup is 0).

## Supported input

- **Track selection**: a direct FL Studio FPC export (channel 1, track names such as `FPC 1`), GM channel 10, and multi-track MIDI all work.
  Automatic selection order: if only one track/channel contains notes, it is used; otherwise all channel 10 data is used; otherwise tracks whose name contains
  `fpc`, `drum`, `perc`, `kit`, `ドラム` or `鼓` (case-insensitive) are used; if that still cannot decide, an error lists the tracks in the file.
  In that case, specify them with `midi.tracks` / `midi.channels` in the metadata or `--track` / `--channel` on the command line.
- **Drum map**: the built-in `gm` and `fpc-default` are available; you can change individual notes with `note_map` in the metadata, or write your own map file.
  A note missing from the map is an error; nothing is guessed. See [docs/drum-maps.en.md](docs/drum-maps.en.md) for details.
- **Time signatures**: 1/4 to 12/4, including time signature changes that fall on a barline, taken from the MIDI time signature events. When the MIDI has none, the metadata
  `time_signature` is used; when neither exists, 4/4 is assumed and a note is printed.
- **Rhythm grid**: 16th (default) or 8th. Each beat and each voice (hands/feet) is judged separately: where the straight grid does not fit but the triplet grid does,
  it is notated as a triplet automatically (an 8th-note triplet on the 8th grid; a triplet or sextuplet on the 16th grid). This is why combined rhythms such as hands in triplets
  over feet in straight 16ths can be notated. The triplet check is fairly strict (see "Quantization" in [docs/metadata.en.md](docs/metadata.en.md) for the rules): slight human deviations are recognized,
  but a deviation of more than 1/32 beat, or a note on a 64th position such as 3/16 beat, is an error; quantize in the DAW first.
- **Grace notes**: a weaker hit on the same pitch very shortly before a main note (within a 32nd note by default) is notated as a grace note (at most two per main note: one is printed as a small slashed 8th note = flam, two as two small 16th notes joined by a beam = drag).
- **Pickup**: `pickup_beats` gives the number of pickup beats. The pickup bar may contain notes or be completely empty; it is numbered 0 and prints its own time signature.
  `source_leading_beats` removes extra empty beats at the start of the source MIDI.
- **Tempo changes**: tempo changes in the MIDI are printed at the start of the bar they fall in (♩ = value) and written to the MusicXML as well; a tempo change in the middle of a bar produces a note.
- **Dynamics (optional)**: when `dynamics.ghost_below` / `dynamics.accent_above` are set, weak hand notes are printed with parenthesized noteheads (ghost notes)
  and strong ones get an accent mark `>`. Disabled by default.
- **Repeat marks and beaming**: 1-bar (`%`) and 2-bar (`//`) simile repeats are enabled by default (`notation.repeats: simile`); `full` also losslessly folds phrase-aligned `|: ... :|` repeats and 1st/2nd endings (`1.`/`2.`), and `off` writes every bar in full (overridable with `--repeats`). Optional 4/4 half-bar 4-eighth beaming can be enabled via `notation.beam_eighths: half-bar` (or `--beam-eighths half-bar`).
- **Sections (optional)**: the top-level `sections` mapping (`source bar number: ASCII label`) adds double barlines, boxed rehearsal marks, repeat/rest resets and section-aligned line breaks.

## Known limitations

- 32nd notes (and 64th positions such as 3/16 beat), other tuplets such as quintuplets, 16th notes mixed with triplets within the same beat of the same voice,
  and unquantized performances are not supported. All of them are reported as errors that name the beat and the voice; the rhythm is never changed silently and no note is dropped. On the 16th grid, 8th notes mixed with 8th-note triplets
  (for example at the beat head, 1/3 and 1/2 beat) fall on the sextuplet grid and can be notated as a sextuplet. Duplicate triggers of the same pitch are merged only when they are at most 1/48 beat apart
  (the count is given in a note).
- Compound meters such as 6/8 and 12/8, and time signatures whose denominator is not 4, are not supported; change them in the DAW to x/4 with triplets.
- Roll and tremolo marks are not notated, and neither is sticking.
- Auxiliary percussion such as hand claps, cowbell and shaker is printed on the **same staff** as the drum kit and distinguished by position and notehead; with the legend enabled (`legend: true` / `--legend`) they are listed.
- Rests: each of the two voices fills every beat on its own. Wherever either the hands or the feet voice has no note within a beat, a rest is printed (higher for the hands voice, lower for the feet voice);
  when both voices have a rest of the same length at the same moment, they are combined into one centered rest; when a voice has no notes for a whole bar, a whole-bar rest is printed. In the MusicXML, every voice likewise has complete rests.
- Note durations are inferred following drum-score convention: a note lasts until the next note in the same voice or the end of the beat, at most a quarter note; the note length in the MIDI is not expressed.
- Different MIDI notes mapped to the same position and the same notehead cannot be told apart on the score (for example GM 38 and 40 are both printed as snare); a note is printed when they appear at the same time.
- Title and other text must consist of characters that Noto Sans CJK JP can display: missing glyphs such as emoji are an error (exit code 2); two characters with the same glyph (such as 〜 and ～)
  printed in the same font weight are also an error, because the copied text could not tell them apart. The song title on the first page is bold and all other text (including the title in the running header) is regular,
  so a conflict arises only when they are mixed within the same weight.

## Adding a new song

1. Choose a stable ASCII slug and create `scores/<slug>/`.
2. Put the **original** MIDI as-is at `scores/<slug>/source.mid` and never modify it afterwards.
3. Copy [templates/metadata.yaml](templates/metadata.yaml) to `scores/<slug>/metadata.yaml` and fill in the credits, drum map, pickup and so on;
   see [docs/metadata.en.md](docs/metadata.en.md) for the fields.
4. Run `python3 scripts/build_score.py scores/<slug>/source.mid --metadata scores/<slug>/metadata.yaml --out-dir build/<slug>`
   and adjust the metadata according to the errors and notes (write unmapped notes into `note_map`, set `midi.tracks` etc. for multi-track files).
5. Render the PDF to images and check it page by page (for example `pdftoppm -r 100 -png build/<slug>/score.pdf build/<slug>/page`),
   and only when it is correct copy `score.musicxml` and `score.pdf` to `scores/<slug>/`.
6. Write `scores/<slug>/README.md`: source, derived files, how they were generated, transcription notes and copyright notes.

## Example song

[命に嫌われている。](scores/inochi-ni-kirawareteiru/README.en.md): 作詞・作曲：カンザキイオリ　歌：カンザキイオリ（セルフカバー）,
included in 『不器用な男』; ドラム採譜・編曲：音宮, including the transcriber's restructuring and original work. This is a fan transcription, **not** an official score.

## Step-by-step scripts

For everyday use, `build_score.py` is enough. To investigate a problem you can run the steps individually. The conversion and validation scripts all accept `--drum-map`, `--repeats` and `--beam-eighths`; `--track` and `--channel`
are accepted only by `midi_to_musicxml.py`, `render_score.py`, `validate_score.py` and `build_score.py` (`midi_to_musixtex.py` selects tracks from the metadata only).
`midi_to_musicxml.py`, `render_score.py` and `midi_to_musixtex.py` only convert, with exit code 0 or 2; the exit codes of `validate_score.py` are as in the table above,
and it also returns 2 when the input file is not found. `retag_gm_channel10.py` accepts only `source --out`; on error it raises a plain Python exception and does not distinguish 0/1/2 as above.

```bash
python3 scripts/midi_to_musicxml.py MIDI --metadata META --out OUT.musicxml
python3 scripts/render_score.py MIDI --metadata META --out OUT.pdf [--legend|--no-legend] [--keep-tex OUT.tex] [--work-dir DIR]
python3 scripts/validate_score.py MIDI --metadata META --musicxml OUT.musicxml --pdf OUT.pdf [--xsd XSD]
python3 scripts/midi_to_musixtex.py MIDI --metadata META --out OUT.tex     # view only the MusiXTeX source
python3 scripts/retag_gm_channel10.py source.mid --out build/gm-channel10.mid  # for software that only recognizes channel 10
python3 -m pytest -q tests
```

Optional environment variables for the tests: when `MUSICXML_XSD` points to `musicxml.xsd`, the XSD validation tests run; when `PDFJS_TEXT` points to a pdf.js text extraction script
(`node script file.pdf` prints `--- page N` for each page, followed by that page's text fragments joined with `|`) and `node` is available, the text copied by pdf.js is checked as well.
When they are not set these tests are skipped; without a TeX environment the PDF tests are skipped.

## License and copyright

- The **original code and documentation** of this repository are released under the MIT License (see `LICENSE`).
- The MIT License does **not apply** to the `scores/` directory or to any third-party musical work: songs, arrangements, lyrics, recordings, and the MIDI,
  MusicXML and PDF scores in the repository. The copyright and distribution rights of these belong to their respective rights holders.
- Transcribing a work or crediting its source is not the same as obtaining permission to distribute it. Do not publish copyrighted scores without the rights holder's permission.
  This repository does not assume that any score has been cleared for public redistribution.
