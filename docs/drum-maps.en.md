[日本語](drum-maps.md) | [简体中文](drum-maps.zh-CN.md) | [English](drum-maps.en.md)

# Instrument Catalog and Drum Maps

A drum in MIDI is just a note number (for example 36, 38, 42). Turning note numbers into noteheads on the score takes two layers of configuration:

1. **Instrument catalog** `configs/instruments.yaml`: where each instrument is printed, which notehead it uses, whether it has an open/closed mark, its Japanese name and its legend abbreviation.
2. **Drum map** `configs/drum-maps/*.yaml`: MIDI note number → instrument ID. The `note_map` in the song metadata can override the map note by note.

A note that is not in the map is an error; the tool never guesses. The error message lists those note numbers, says at which beat of the source MIDI the first one appears, and gives an example `note_map` entry using one of the note numbers.

## Instrument catalog fields

```yaml
hihat-open: {name: Open Hi-Hat, name_ja: ハイハット（オープン）, abbr: HHo, part: hand, staff: n, head: x, mark: open}
```

| Field | Required | Description |
| --- | --- | --- |
| (key) | yes | Instrument ID, used by maps and `note_map` to refer to the instrument |
| `name` | yes | English name, written to the MusicXML `instrument-name` (followed by the MIDI note number) |
| `name_ja` | no | Japanese name, printed in the legend (copyable text). A full-width parenthesis `（…）` and everything after it moves to a second line in the legend. Defaults to `name` |
| `abbr` | no | Legend abbreviation, 1–4 characters; only ASCII letters, digits and `. + -` are allowed. By default it is generated from the ASCII words in `name`: with several words, the capitalized initials (at most 4, e.g. `Hi Hat` → `HH`); with a single word, its first 3 characters; with no ASCII word, `X` |
| `part` | yes | `hand`: upper voice, stems up; `foot`: lower voice, stems down |
| `staff` | yes | Staff position, a single letter `a`–`s`; see the table below |
| `head` | yes | Notehead: `normal` filled oval, `x` x, `circle-x` circled x, `diamond` open diamond, `triangle` triangle, `plus` plus, `rhombus` filled diamond |
| `mark` | no | Mark: `open` small circle ○, `half-open` ⊖, `closed` ＋; none if omitted. Printed above the notehead (3 positions higher for hands, 2 for feet) |

### Staff position letters

The letters follow the MusiXTeX pitch letters and are read as positions on a treble clef; in MusicXML they are written as the matching `display-step` / `display-octave`.

| Letter | Position | MusicXML | | Letter | Position | MusicXML |
| --- | --- | --- | --- | --- | --- | --- |
| `a` | 2nd line below the staff | A3 | | `j` | 3rd space | C5 |
| `b` | 2nd space below the staff | B3 | | `k` | 4th line | D5 |
| `c` | 1st line below the staff | C4 | | `l` | 4th space | E5 |
| `d` | 1st space below the staff | D4 | | `m` | 5th line | F5 |
| `e` | 1st line | E4 | | `n` | 1st space above the staff | G5 |
| `f` | 1st space | F4 | | `o` | 1st line above the staff | A5 |
| `g` | 2nd line | G4 | | `p` | 2nd space above the staff | B5 |
| `h` | 2nd space | A4 | | `q` | 2nd line above the staff | C6 |
| `i` | 3rd line | B4 | | `r` | 3rd space above the staff | D6 |
| | | | | `s` | 3rd line above the staff | E6 |

("1st space above the staff" is the space between the 5th line and the 1st line above the staff; "1st space below the staff" is the space between the 1st line and the 1st line below the staff.)

For the position and notehead of each instrument in the bundled catalog, see [notation-conventions.en.md](notation-conventions.en.md).

## Bundled maps

### `gm` (default)

The General MIDI Level 1 percussion keys 35–81, plus the GS/GM2 extensions 27–34 and 82–87, 61 notes in total.
For the instrument of each note, see `configs/drum-maps/gm.yaml`; for the position and notehead of each instrument, see the summary table in notation-conventions.en.md. A few points to watch:

| Note | GM name | Mapped to | Notes |
| --- | --- | --- | --- |
| 35 | Acoustic Bass Drum | `kick-2` (1st line) | If you use only 35 as the bass drum, use `note_map: {35: kick}` to print it in the usual 1st space |
| 36 | Bass Drum 1 | `kick` (1st space) | |
| 38, 40 | Acoustic / Electric Snare | both `snare` | Cannot be told apart on the score; to distinguish them, change the notehead of one |
| 44 | Pedal Hi-Hat | `hihat-pedal` (1st space below the staff, foot) | |
| 42, 46 | Closed / Open Hi-Hat | same position (1st space above the staff); 46 gets a ○ | |

### `fpc-default`

The default layout of FPC, the drum sampler in FL Studio. According to [the FPC page of the FL Studio online manual](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/FPC.htm) (paraphrased):

- Default in the layout menu is the same as the Akai MPC series layout (unless it has been overwritten by a layout you saved yourself);
- The names in parentheses next to the notes are the General MIDI standard names; in the blank preset every pad is already assigned to the matching General MIDI note;
- The trigger note of each pad can be changed in Play Key/Octave, and layouts can be saved.

In other words, with the default layout the note numbers FPC sends are the GM percussion numbers, so `fpc-default` simply uses `extends: gm` and changes no notes.
It differs from `gm` only in the description text; writing it in the metadata records that "this is an FPC export".

When FL Studio exports FPC directly, the notes are on MIDI channel 1 and the track name looks like `FPC 1`; the converter's automatic track selection picks it (see [metadata.en.md](metadata.en.md)).
**If you have changed a pad's sound or note**, the instrument actually on that note number is no longer the one the GM name suggests. You must override it with `note_map` or a custom map,
otherwise the score prints the wrong instrument.

## Overriding notes

### With `note_map` in the metadata

The keys of `note_map` are MIDI note numbers (0–127). A value can be written in three ways:

```yaml
note_map:
  # 1. Swap in another instrument from the catalog
  40: hand-clap

  # 2. Start from a catalog instrument and change a few fields
  38: {as: snare, head: circle-x, name_ja: スネア（リムショット）, abbr: RS}

  # 3. Define a new instrument in full (name, part, staff, head are required; id is optional)
  77: {id: block, name: Block, name_ja: ブロック, abbr: BL, part: hand, staff: r, head: triangle}
```

`note_map` overrides only the notes it lists; all others still follow `drum_map`.

### Writing your own map file

If you use an FPC kit or an electronic drum source often, a map file is more convenient.

```yaml
# For example scores/<slug>/my-kit.yaml or configs/drum-maps/my-kit.yaml
name: My FPC kit
description: Pad 40 of Bank A is changed to a hand clap, and pad 41 is a third floor tom
extends: fpc-default        # a bundled map name, or a path relative to the directory of this file
notes:
  40: hand-clap
  41: {as: tom-floor-low, abbr: FT3, name_ja: フロアタム3}
```

- Only `name`, `description`, `extends` and `notes` are allowed at the top level.
- `extends` can inherit through several levels; a child map overrides notes with the same number in its parent. An inheritance cycle is an error.
- The values in `notes` use the same three forms as `note_map`.
- In the metadata, write `drum_map: my-kit.yaml` (relative to the directory of the metadata file), or put the file in `configs/drum-maps/` and write `drum_map: my-kit`.

## Instruments with the same position and notehead

The score tells instruments apart only by position, notehead and mark. When two MIDI notes have the same **position, notehead, mark and voice** (for example GM 38 and 40 are both `snare`),
they cannot be told apart on the score and are merged into one legend entry, which prints only the abbreviation and Japanese name of the lower note number. If both are struck at the same time, the two noteheads are printed on top of each other, and the conversion prints a note (`Note: …`).
When two instruments at the same position but with different noteheads are struck together (for example ride and ride bell), a notehead-overlap note is also printed. The note names the bar and beat and shows how to change the position,
for example `40: {as: snare, staff: l}`.
In MusicXML they remain different instruments (each keeps its original MIDI note number, so playback is correct).

To tell them apart on the score, use `note_map` to give one of them a different notehead or position. No two instruments in the bundled instrument catalog share the same position, notehead, mark and voice.
