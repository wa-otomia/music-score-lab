[日本語](metadata.md) | [简体中文](metadata.zh-CN.md) | [English](metadata.en.md)

# Song metadata (metadata.yaml)

Each song has one `scores/<slug>/metadata.yaml`, read by `scripts/build_score.py --metadata`.
For a new song, copy [templates/metadata.yaml](../templates/metadata.yaml).

- Only the fields listed in this document (including the "Legacy fields" at the end) are allowed at the top level. Any other field is an error, so a misspelled field name is never silently ignored.
- Every field is optional; when omitted, the value in the "Default" column is used.
- `midi`, `quantize`, `notation`, `dynamics` and `credits` also accept only the sub-fields listed below; a misspelling is an error here too.

## Credits and text

These fields only affect the title block, the running header and the MusicXML credits; they do not affect the notation. Values are output as written (Japanese is fine). The PDF does not insert spaces automatically between kanji, kana and Latin letters, so a space you write is printed as is (exception: a half-width space directly after a full-width punctuation mark, or between kana/kanji and a full-width parenthesis, is not printed, following Japanese typesetting rules). Only leading and trailing whitespace (including full-width spaces) is stripped, and runs of ASCII whitespace such as line breaks and tabs are collapsed into one half-width space.
When copying text: half-width spaces written between kanji/kana and Latin letters are preserved by both pdftotext and pdf.js. A full-width space (U+3000) prints fine, but pdftotext and pdf.js copy it out as a half-width space, whereas PyMuPDF keeps U+3000 (and PyMuPDF, conversely, drops half-width spaces next to kanji or kana).
MusicXML stores the original metadata values without the whitespace handling above.

| Field | Type | Default | Purpose | Example |
| --- | --- | --- | --- | --- |
| `title` | string | `Untitled` | Song title: PDF title, running header, PDF document title, MusicXML `work-title` and `movement-title` | `命に嫌われている。` |
| `subtitle` | string | none | A line under the title; MusicXML `work-number` (MuseScore 3 shows it as the subtitle) and the subtitle credit | `Self-cover ver.` |
| `artist` | string | none | Artist: title block and running header; used as the MusicXML subtitle credit when there is no `subtitle` | `カンザキイオリ` |
| `album` | string | none | Album: printed as `『…』` after the artist | `不器用な男` |
| `lyricist` | string | none | Lyricist (label `作詞`) | `カンザキイオリ` |
| `composer` | string | none | Composer (label `作曲`) | `カンザキイオリ` |
| `vocal` | string | none | Vocals (label `歌`) | `カンザキイオリ（セルフカバー）` |
| `transcriber` | string | none | Drum score transcription (label `ドラム採譜`); MusicXML credit of type `arranger` | `音宮` |
| `arranger` | string | none | Drum arrangement (label `ドラム編曲`) | `音宮` |
| `note` | string | none | Note (label `備考`), e.g. to say the score includes the transcriber's re-creation | `本譜には採譜者による再構成・創作を含みます。` |
| `copyright` | string | none | Printed at the bottom of the first page; MusicXML `rights` | `© 2026 …` |
| `credits` | mapping | none | Override the role labels, see below | `{arranger: アレンジ}` |
| `legend` | boolean | `false` | Whether to print the legend on the first page. Must be a YAML boolean; a quoted string such as `"false"` is an error | `false` |
| `slug` | string | none | For your records only (same as the directory name); the program does not use it | `inochi-ni-kirawareteiru` |

In MusicXML: `title` is written as `work-title` and `movement-title`; `subtitle` as `work-number` inside `<work>`;
`composer`, `lyricist` and `arranger` as `creator`; `artist`, `album`, `vocal`, `transcriber` and `note` as `miscellaneous-field` of the same name.
The `credit` elements on the first page: the title is centered; the subtitle (`subtitle`, or `artist` when there is none) is centered; `composer` is right-aligned;
`lyricist` is left-aligned; `transcriber` (credit type `arranger`) is left-aligned. Software that reads `credit` shows these credits.
MuseScore 3 does not read `credit`: after opening, it shows the title (from `movement-title`), the subtitle (from `work-number`, so only if `subtitle` is set), the composer and the lyricist, but not `artist` or `transcriber`.
PDF document properties: the title is `<title> ドラム譜`, the author is `transcriber` and `arranger`
(written once if they are the same), and the subject is `artist / album`.

### How the title block is assembled

The first-page title block, from top to bottom:

1. `title` (large, bold)
2. `subtitle`
3. `artist　『album』`
4. Song credits: in the order `lyricist`, `composer`, `vocal`
5. Drum score credits: in the order `transcriber`, `arranger`
6. `備考：note`
7. `BPM <tempo>`
8. Legend (printed only with `legend: true` or the command-line `--legend`)

In lines 4 and 5, roles whose **values are exactly the same** (compared character by character after stripping leading and trailing whitespace) are merged under one label joined with `・`; different people are separated by a full-width space.
Whitespace inside the value is not collapsed for the comparison: `A  B` (two spaces) prints the same as `A B` but is not merged.

| Metadata | Printed line |
| --- | --- |
| `lyricist: A`, `composer: A`, `vocal: B` | `作詞・作曲：A　歌：B` |
| `lyricist: A`, `composer: B` | `作詞：A　作曲：B` |
| `transcriber: C`, `arranger: C` | `ドラム採譜・編曲：C` |
| `transcriber: C`, `arranger: D` | `ドラム採譜：C　ドラム編曲：D` |

When merging, if the first label starts with `ドラム`, the repeated `ドラム` at the start of the following labels is dropped, so the result is `ドラム採譜・編曲` rather than `ドラム採譜・ドラム編曲`. Names that are written even slightly differently (for example one with 「（セルフカバー）」 and one without) are not merged.

### credits: overriding labels

The keys of `credits` are role names and the values are the labels to print. Roles that can be overridden: `lyricist`, `composer`, `vocal`, `transcriber`, `arranger`, `note`.
`artist` and `album` are also accepted, but the title block prints no label for them, so they have no effect; any other key is an error.

```yaml
credits:
  vocal: ボーカル        # 「歌：…」 becomes 「ボーカル：…」
  arranger: アレンジ     # 「ドラム編曲：…」 becomes 「アレンジ：…」
```

## Drum map and track selection

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `drum_map` | string | `gm` | Bundled map name (`gm`, `fpc-default`) or the path of a map YAML. A relative path is looked up first relative to the directory of the metadata file, then relative to the current directory. The command-line `--drum-map` takes precedence |
| `note_map` | mapping | none | Override notes one by one on top of `drum_map`: `MIDI note number: instrument`. For the syntax see [drum-maps.en.md](drum-maps.en.md) |
| `midi.tracks` | list or single value | automatic | Use only these tracks. A string matches tracks whose name contains the text (case-insensitive); an integer is a track index (from 0; track 0 is usually the tempo track). The command-line `--track` (by name only) takes precedence |
| `midi.channels` | list or single integer | automatic | Use only these MIDI channels, numbered 1-16 (GM drums are 10; a direct FPC export is 1). The command-line `--channel` takes precedence |

When `tracks` and `channels` are both given, both conditions must hold. When neither is given, selection is automatic: if only one track/channel in the file contains notes, it is used;
otherwise all channel-10 notes are used; otherwise tracks whose name contains `fpc`, `drum`, `perc`, `kit`, `ドラム` or `鼓` are used; if it is still unclear, the program reports an error and lists the tracks.

```yaml
drum_map: fpc-default
note_map:
  40: hand-clap          # this FPC kit puts the hand clap on pad 40
midi:
  tracks: [FPC]          # or [1] (by index), or channels: [10]
```

## Quantization

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `quantize.subdivision` | integer | `4` | Straight grid: `4` = 16th notes, `2` = 8th notes. Only these two values are allowed |
| `quantize.tuplets` | string | `auto` | `auto`: decide beat by beat and voice by voice whether to write triplets; `off`: never write triplets (a triplet is an error). An unquoted `off` is read by YAML as false and is treated as `off` all the same |
| `quantize.flam_window` | number | `1/8` | Grace-note window in quarter notes (`1/8` is a 32nd note). You can write `1/16`, `0.125` and so on; `0` turns grace-note detection off |

Decision rules (made separately for the hand voice and the foot voice of each beat):

- If every note of this voice in this beat is within 1/24 beat of the straight grid: write it straight.
- Otherwise, if `tuplets: auto` and every note is within 1/32 beat of the triplet grid: write it as a triplet
  (with `subdivision: 4` the grid is 1/6 beat, which can express triplets and 16th-note sextuplets; with `subdivision: 2` the grid is 1/3 beat).
  Slight human deviation (about ±0.015-0.025 beat) is generally recognized; triplets that deviate by more than 1/32 beat are an error, so quantize them in the DAW first.
- Exception: if a note is within 1/192 beat of a 64th-note position that is not a triplet position (for example exactly at 3/16 beat),
  it is not written as a triplet; an error says this is a 32nd/64th-note rhythm. The same error occurs when human deviation happens to push a note near such a position
  (for example a note at 1/3 beat that is about 0.02 beat early lands near 5/16 beat).
- With `subdivision: 4`, an 8th note and an 8th-note triplet in the same beat (at the beat start, 1/3 and 1/2 beat) fall exactly on the sextuplet grid and are written as a sextuplet;
  a 16th note and a triplet in the same beat (e.g. at 1/4 and 1/3 beat) fit neither grid and are an error.
- If none of these applies: an error that names the beat (counted from the start of the score) and the voice. The program never forces a "roughly fitting" grid.
- In a beat written as a triplet, a voice whose notes are all on straight 16th-note positions (for example the other voice playing quarter or 16th notes with the feet) is written straight as usual, without a triplet mark.
- The main note of a flam is naturally late, so its tolerance is widened to 1/16 beat (and it is not subject to the 64th-note-position exception above); when the grace note sits on the grid, the grace note's position can also be used to locate it.

Grace notes and duplicate triggers (the same MIDI note):

- A hit within 1/48 beat of the first hit is treated as the same hit (a duplicate trigger); the one with the highest velocity is kept, and the count is given in a note (printed as `Note: …`).
- A weaker hit within `flam_window` before a hit is written as its grace note; a main note takes at most two grace notes: one is a flam (a small 8th note with a slash), two are a drag (two small beamed 16th notes).
  Fast hits with a continuous crescendo are not treated as grace notes and are reported as 32nd notes.
- In any other case, two hits quantized to the same position are an error; neither is dropped.
- Grace-note detection is not done between different notes.

## Time signature, tempo, pickup

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `time_signature` | string `"n/4"` | none | Used when the MIDI has no time signature event. When the MIDI has one, it must equal the first MIDI time signature, otherwise it is an error; later time signature changes always come from the MIDI. If neither exists, 4/4 is used with a note. Only 1/4-12/4 is supported |
| `tempo_bpm` | number | The MIDI tempo in effect at the start of the score (after the extra leading beats are removed); if there is no tempo event before the start, the first one; if the MIDI has no tempo event, 120 | The title block `BPM` and the tempo of MusicXML bar 1. Range 10-400. A note is given when it differs from the MIDI; the score follows the metadata. Later tempo changes in the MIDI are still printed |
| `pickup_beats` | integer | `0` | Number of beats (quarter notes) in the pickup bar. The pickup bar is numbered 0, prints its own time signature (e.g. `2/4`) and may contain notes |
| `source_leading_beats` | integer | equal to `pickup_beats` | Where bar 1 (the first full bar after the pickup) starts in the source MIDI, in beats (quarter notes). Requires `0 ≤ pickup_beats ≤ source_leading_beats` |

The score starts at beat `source_leading_beats − pickup_beats` of the source MIDI (anything before it is discarded); a note that falls in the discarded part is an error. Example: if the source MIDI begins with a whole bar (4 beats) of
silence and you want the score to keep only 2 beats of it, printed as a 2/4 pickup, write `source_leading_beats: 4` and `pickup_beats: 2`.
The barlines after the pickup bar follow the MIDI time signature; time signature changes in the MIDI must fall exactly on these barlines, otherwise it is an error.

## Dynamics

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `dynamics.ghost_below` | integer | none (disabled) | Hand notes with velocity **below** this value are written as ghost notes: parenthesized notehead in the PDF, `notehead parentheses="yes"` in MusicXML |
| `dynamics.accent_above` | integer | none (disabled) | Hand notes with velocity **above** this value get an accent mark `>` (MusicXML `accent`) |

Feet (bass drum, pedal hi-hat) get no ghost / accent marks.

## Notation

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `notation.repeats` | string | `simile` | Controls repeat notation mode. `simile`: enables 1-bar (`%`) and 2-bar (`//`) simile repeats (default); `full`: adds phrase-aligned section repeats (`|: ... :|`) and 1st/2nd ending voltas (`1.`/`2.`) on top of `%`/`//`; `off`: disables all repeats and writes out every non-empty bar in full. An unquoted `off` is read by YAML as false and is treated as `off` all the same. The command-line `--repeats` takes precedence |
| `notation.repeat_counters` | boolean | `false` | Whether to print repeat-run numbers (`2`, `3`, `4`, …) above each `%` when 2 or more 1-bar `%` bars occur in a row (3 or more identical bars consecutively). Off by default (`false`); set to `true` to enable. Must be a YAML boolean; a quoted string such as `"true"` is an error |
| `notation.beam_eighths` | string | `beat` | Controls 8th-note beaming. `beat`: grouped per beat, never crossing a beat (default); `half-bar`: in non-pickup 4/4 bars, beams 4 consecutive plain straight 8th notes per half-bar (beats 1–2 and beats 3–4), decided independently for each voice. The command-line `--beam-eighths` takes precedence |
| `notation.system_spacing` | number | `1.1` | Scale factor for PDF vertical spacing between systems (`0.7`–`2.5`). `1.0` is the compact MusiXTeX default; values `< 1.0` tighten spacing and values `> 1.0` add room. Affects PDF layout only (does not affect MusicXML). The command-line `--system-spacing` takes precedence |

By default, no `2`, `3`, `4`, … counters are printed above `%` bars; set `notation.repeat_counters: true` to enable them for runs of 2 or more consecutive `%` bars (an isolated single `%`, i.e. 2 identical bars in a row, is still left unnumbered). A 2-bar `//` repeat always carries `2` as part of the symbol itself and is not affected by `repeat_counters`. For the matching rules, page-break handling and beaming rules, see "Repeat (Simile) Marks" and "Beams" in [notation-conventions.en.md](notation-conventions.en.md).

```yaml
notation:
  repeats: simile         # simile (default), full or off (command-line --repeats takes precedence)
  repeat_counters: false  # false (default); set to true to print count numbers (2, 3, 4…) above consecutive % bars
  beam_eighths: beat      # beat (default) or half-bar (command-line --beam-eighths takes precedence)
  system_spacing: 1.1     # PDF vertical system-spacing scale (0.7–2.5, default 1.1, 1.0 = compact; --system-spacing takes precedence)
```

## Sections

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `sections` | mapping | none | Top-level `bar_number: rehearsal label` mapping. Each key must be an integer `>= 1` within the score's bar range (pickup bar 0 is not allowed; regardless of `notation.repeats`, keys always refer to source unfolded bar numbers); each value must be 1–24 printable ASCII characters after trimming (non-ASCII characters or empty strings are an error) |

Each section start gets a double barline before it (except at the start of the piece, immediately after a pickup bar, or where a repeat barline `|:` / `:|` already stands) and a boxed rehearsal mark above the bar. A section boundary also splits multi-measure rests, resets 1-bar (`%`) and 2-bar (`//`) simile repeats, and encourages starting a new system on that bar. For details see "Sections and Rehearsal Marks" in [notation-conventions.en.md](notation-conventions.en.md).

```yaml
sections:
  1: Intro
  9: A
  25: Chorus
```

## Legacy fields

Fields from early metadata files can still be read, but new files should use the new spelling:

| Legacy field | New spelling | Description |
| --- | --- | --- |
| `beats`, `beat_type` | `time_signature: "4/4"` | If only one of them is written, the other is taken as 4; when `time_signature` is also present, it wins |
| `quantize_divisions_per_beat` | `quantize.subdivision` | When both are present, `quantize.subdivision` wins |
