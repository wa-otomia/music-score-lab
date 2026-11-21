# Agent Operating Instructions

This document is the **single source of truth for autonomous agents** working in this repository. All new agents should read it before touching score assets, publishing PDFs or changing converters.

## Purpose and boundaries

- This is an extensible collection of *user-created drum transcriptions and arrangements*, not a repository dedicated to any one song.
- Maintain actual scores under `scores/<stable-ascii-song-slug>/` and reusable software under `scripts/`, `configs/`, `tests/` and `docs/`.
- Treat source `.mid` as immutable evidence. Never overwrite it with quantized, shifted or GM-channel-rewritten MIDI.
- `score.musicxml` is the editable score interchange format; `score.pdf` is the printable deliverable.
- Do not claim a score is an official transcription or a literal match to the source recording. Source material may be reconstructed or intentionally rearranged.
- **Do not upload copyrighted scores publicly without the rights-holder's authorization.** Attribution, notes about fan transcriptions and a software license are not substitutes for distribution permission. Escalate uncertainties to the user rather than assuming permission.

## Required per-song files

- `metadata.yaml`: original title, artist, composition/vocal credits, album where relevant, transcriber, arrangement disclosure, BPM, meter, and alignment/quantization settings.
- `source.mid`: unmodified source file. Optional clearly labeled derived MIDI such as `gm-channel10.mid`.
- `score.musicxml`: editable standard format, preserving percussion identifiers and separated upper hand/lower foot voices.
- `score.pdf`: visually inspected print-ready engraving with embedded Japanese glyphs.
- `README.md`: lineage and caveats specific to that score.

## Transformation architecture

1. Parse `.mid` using `mido`; follow `metadata.yaml` and map events with `configs/japanese-drums.yaml`.
2. Optionally use `scripts/retag_gm_channel10.py` to produce a GM channel-10 copy for other applications; do not replace original MIDI.
3. Use `scripts/midi_to_musicxml.py` for editable MusicXML (never fake a score via drawing primitives).
4. Use `scripts/render_score.py`: MusiXTeX engraves the notation, XeLaTeX/xeCJK typesets the Japanese credits, Inkscape converts those credits to **vector paths**, and PyMuPDF overlays them. Install CJK fonts locally; **never commit font binaries**. Do not revert to embedding FontTools-subset CJK fonts; they corrupted in some PDF viewers.
5. Run `scripts/validate_score.py` to check events, bar lengths, beam levels, voices, title and PDF integrity. Run `pytest` for converter changes.
6. Render the PDF to images and inspect first, densest, middle and last pages. Fix glyph substitutions, collisions, notehead style, beam counts and page breaks before publishing.

## Notation conventions

- Japanese-style drum notation: cymbal and hi-hat notes use an `×` notehead, regular drums use filled elliptical heads; open hi-hat includes a small `○` centered relative to the **actual notehead**, never an absolute staff height.
- Stems **up** for hands (snare/toms/hi-hat/crash), **down** for feet (kick/hi-hat pedal).
- A single beam represents eighths; two beams represent sixteenths. Do not let one beam span beyond its intended beat grouping.
- MusiXTeX cross-head **terminal sixteenth** must close its secondary beam (`\\tbbu0` + `\\dotqh0`, as implemented), not just a plain quaver-ending primitive.
- Opening meters are explicit: for the current song the first bar has two silent beats and is **visibly marked `2/4`**, followed by `4/4` at the next bar. `source_leading_beats` is the raw MIDI silent lead; `pickup_beats` is the abbreviated opening silence shown in print. Preserve the relative timing of sounding events. New meters need converter and test support, not a misleading 4/4 pickup.
- Preserve the GM pitch IDs even when the staff positions differ. MIDI channel 10 is conventional for GM drums; the converter must not require the input to already use channel 10.
- This converter assumes 4/4 and a quarter subdivision grid of 2 or 4. **Do not silently process tuplets, odd meters, or unmapped drums**; extend the engine/tests or stop with a clear error.
- The converter may collapse exact-time duplicates and represent close, weak pre-hits as grace notes; this is notation inference, not a claim of literal MIDI equivalence. Log the count.

## Contributor workflow

- Prefer small changes with an `Issue`/PR when changing shared converters; do not push generated output until tests and render verification pass.
- Run commands from the repository root (example for this score):

```bash
python -m pip install -r requirements.txt
python scripts/midi_to_musicxml.py scores/inochi-ni-kirawareteiru/gm-channel10.mid --metadata scores/inochi-ni-kirawareteiru/metadata.yaml --out build/score.musicxml
python scripts/render_score.py scores/inochi-ni-kirawareteiru/gm-channel10.mid --metadata scores/inochi-ni-kirawareteiru/metadata.yaml --out build/score.pdf
python scripts/validate_score.py scores/inochi-ni-kirawareteiru/gm-channel10.mid --metadata scores/inochi-ni-kirawareteiru/metadata.yaml --musicxml build/score.musicxml --pdf build/score.pdf
python -m pytest -q tests
```

- Verify diff against existing score before replacing a curated PDF/MusicXML. When regenerating, preserve attribution and comments in metadata.
- Do not add generated logs, TeX intermediates, temporary font subsets, temp PNGs, credentials, or unrelated project files.
- Explain what changed and whether score content or merely engraving/layout changed.

## Copyright and licensing

- The MIT license applies **only to original conversion code and project documentation**; it does **not** license the underlying songs, arrangement rights, contributed MIDI, MusicXML or PDF scores.
- For every contributed song, verify publishing authorization separately. If unclear, keep the assets private until resolved. No agent may reinterpret user consent to transcribe as a blanket license to distribute third-party compositions.
