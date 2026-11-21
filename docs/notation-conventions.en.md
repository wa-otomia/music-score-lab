[日本語](notation-conventions.md) | [简体中文](notation-conventions.zh-CN.md) | [English](notation-conventions.en.md)

# Notation Conventions

This document describes the Japanese-style drum notation that the converter **currently implements**. The PDF and the MusicXML come from the same notation model (`scripts/score_core.py`),
so rhythm, note values, beams and rests are identical. The only differences are the triplet brackets (see "Triplets and Sextuplets"), the merging of rests that are identical in both voices,
and the left/right offset of noteheads (a PDF layout detail).

## Staff and Voices

- One five-line staff with a percussion clef.
- **Upper voice (voice 1) = hands**: snare, toms, cymbals, hi-hat, auxiliary percussion. Stems point up.
- **Lower voice (voice 2) = feet**: bass drum, pedal hi-hat. Stems point down.
- Notes struck at the same time in one voice form a single chord and share one stem. When two noteheads in a chord are a second apart (adjacent positions), they are printed on opposite sides of the stem.
  The open/closed mark and the ghost-note parentheses of a notehead moved to the other side move with it. If a chord with its stem up has a dot, the dot is printed to the right of the displaced column.
- When hands and feet are struck at the same time and their noteheads are within a second of each other (adjacent, same position or crossed), the PDF shifts the noteheads of one voice sideways (the voice without a beam is moved first).
  If both voices have beams and cannot be shifted, a note is given that names the bar and beat.

## Positions and Noteheads

The tables below are generated from `configs/instruments.yaml` and `configs/drum-maps/gm.yaml`. Positions are read as in a treble clef.
"1st space above the staff" means the space between the 5th line and the 1st line above the staff; "1st space below the staff" means the space between the 1st line and the 1st line below the staff. For the meaning of the letters (such as `f`), see [drum-maps.en.md](drum-maps.en.md).

The main Japanese-style positions: bass drum in the 1st space, snare in the 3rd space, toms stepping down from the 5th line, hi-hat in the 1st space above the staff, crash cymbal on the 1st line above the staff,
and pedal hi-hat in the 1st space below the staff (x notehead, stem down). Positions are based on the PAS / Weinberg drum notation guide, with these Japanese-style positions kept.

### Drum Set

| Instrument ID | Legend name | Abbr. | Voice | Position | Notehead | Mark | GM note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `kick` | バスドラム | BD | feet | 1st space (`f`) | filled oval |  | 36 |
| `kick-2` | バスドラム2 | BD2 | feet | 1st line (`e`) | filled oval |  | 35 |
| `hihat-pedal` | ハイハット（ペダル） | HHp | feet | 1st space below the staff (`d`) | x |  | 44 |
| `hihat-foot-splash` | ハイハット（フットスプラッシュ） | HHs | feet | 1st space below the staff (`d`) | x | ○ | — |
| `snare` | スネア | SD | hands | 3rd space (`j`) | filled oval |  | 38, 40 |
| `side-stick` | サイドスティック | SS | hands | 3rd space (`j`) | x |  | 37 |
| `hand-clap` | ハンドクラップ | CL | hands | 3rd space (`j`) | triangle |  | 39 |
| `tom-high` | ハイタム | T1 | hands | 5th line (`m`) | filled oval |  | 50 |
| `tom-high-mid` | ハイミッドタム | T2 | hands | 4th space (`l`) | filled oval |  | 48 |
| `tom-low-mid` | ローミッドタム | T3 | hands | 4th line (`k`) | filled oval |  | 47 |
| `tom-low` | ロータム | T4 | hands | 3rd line (`i`) | filled oval |  | 45 |
| `tom-floor-high` | フロアタム | FT | hands | 2nd space (`h`) | filled oval |  | 43 |
| `tom-floor-low` | ロー・フロアタム | FT2 | hands | 2nd line (`g`) | filled oval |  | 41 |
| `hihat-closed` | ハイハット（クローズ） | HH | hands | 1st space above the staff (`n`) | x |  | 42 |
| `hihat-open` | ハイハット（オープン） | HHo | hands | 1st space above the staff (`n`) | x | ○ | 46 |
| `hihat-half-open` | ハイハット（ハーフオープン） | HHh | hands | 1st space above the staff (`n`) | x | ⊖ | — |
| `crash` | クラッシュ | CC | hands | 1st line above the staff (`o`) | x |  | 49 |
| `crash-2` | クラッシュ2 | CC2 | hands | 2nd line above the staff (`q`) | x |  | 57 |
| `splash` | スプラッシュ | SP | hands | 2nd space above the staff (`p`) | x |  | 55 |
| `china` | チャイナ | CH | hands | 2nd line above the staff (`q`) | circled x |  | 52 |
| `ride` | ライド | RC | hands | 5th line (`m`) | x |  | 51 |
| `ride-bell` | ライド（カップ） | RB | hands | 5th line (`m`) | open diamond |  | 53 |
| `ride-2` | ライド2 | RC2 | hands | 4th line (`k`) | x |  | 59 |

### Auxiliary Percussion and Others

| Instrument ID | Legend name | Abbr. | Voice | Position | Notehead | Mark | GM note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `tambourine` | タンバリン | TB | hands | 4th space (`l`) | open diamond |  | 54 |
| `cowbell` | カウベル | CB | hands | 4th space (`l`) | triangle |  | 56 |
| `vibraslap` | ビブラスラップ | VS | hands | 2nd space (`h`) | open diamond |  | 58 |
| `bongo-high` | ハイボンゴ | BGh | hands | 4th space (`l`) | plus |  | 60 |
| `bongo-low` | ローボンゴ | BGl | hands | 4th line (`k`) | plus |  | 61 |
| `conga-high-mute` | ハイコンガ（ミュート） | CGm | hands | 4th line (`k`) | filled diamond | ＋ | 62 |
| `conga-high-open` | ハイコンガ（オープン） | CGo | hands | 4th line (`k`) | filled diamond | ○ | 63 |
| `conga-low` | ローコンガ | CGl | hands | 3rd line (`i`) | filled diamond |  | 64 |
| `timbale-high` | ハイティンバレス | TIh | hands | 5th line (`m`) | triangle |  | 65 |
| `timbale-low` | ローティンバレス | TIl | hands | 4th line (`k`) | triangle |  | 66 |
| `agogo-high` | ハイアゴゴ | AGh | hands | 1st line above the staff (`o`) | triangle |  | 67 |
| `agogo-low` | ローアゴゴ | AGl | hands | 1st space above the staff (`n`) | triangle |  | 68 |
| `cabasa` | カバサ | CA | hands | 3rd line (`i`) | x |  | 69 |
| `maracas` | マラカス | MA | hands | 2nd space (`h`) | filled diamond |  | 70 |
| `shaker` | シェイカー | SH | hands | 2nd line (`g`) | filled diamond |  | 82 |
| `whistle-short` | ホイッスル（ショート） | WSs | hands | 2nd space above the staff (`p`) | open diamond |  | 71 |
| `whistle-long` | ホイッスル（ロング） | WSl | hands | 2nd line above the staff (`q`) | open diamond |  | 72 |
| `guiro-short` | ギロ（ショート） | GUs | hands | 2nd space (`h`) | plus |  | 73 |
| `guiro-long` | ギロ（ロング） | GUl | hands | 2nd line (`g`) | plus |  | 74 |
| `claves` | クラベス | CV | hands | 3rd space (`j`) | filled diamond |  | 75 |
| `woodblock-high` | ハイウッドブロック | WBh | hands | 1st space above the staff (`n`) | plus |  | 76 |
| `woodblock-low` | ローウッドブロック | WBl | hands | 5th line (`m`) | plus |  | 77 |
| `cuica-mute` | クイーカ（ミュート） | CUm | hands | 1st line above the staff (`o`) | open diamond | ＋ | 78 |
| `cuica-open` | クイーカ（オープン） | CUo | hands | 1st line above the staff (`o`) | open diamond | ○ | 79 |
| `triangle-mute` | トライアングル（ミュート） | TRm | hands | 2nd line above the staff (`q`) | triangle | ＋ | 80 |
| `triangle-open` | トライアングル（オープン） | TRo | hands | 2nd line above the staff (`q`) | triangle | ○ | 81 |
| `jingle-bell` | ジングルベル | JB | hands | 1st space above the staff (`n`) | open diamond |  | 83 |
| `bell-tree` | ベルツリー | BT | hands | 1st line above the staff (`o`) | filled diamond |  | 84 |
| `castanets` | カスタネット | CS | hands | 5th line (`m`) | filled diamond |  | 85 |
| `surdo-mute` | スルド（ミュート） | SUm | hands | 1st line (`e`) | filled oval | ＋ | 86 |
| `surdo-open` | スルド（オープン） | SUo | hands | 1st line (`e`) | filled oval | ○ | 87 |
| `high-q` | ハイQ | HQ | hands | 3rd line (`i`) | plus |  | 27 |
| `slap` | スラップ | SL | hands | 3rd space (`j`) | plus |  | 28 |
| `scratch-push` | スクラッチ（プッシュ） | SCp | hands | 2nd line (`g`) | triangle |  | 29 |
| `scratch-pull` | スクラッチ（プル） | SCl | hands | 2nd line (`g`) | open diamond |  | 30 |
| `sticks` | スティック | ST | hands | 2nd space above the staff (`p`) | plus |  | 31 |
| `square-click` | スクエアクリック | SQ | hands | 1st line above the staff (`o`) | plus |  | 32 |
| `metronome-click` | メトロノーム（クリック） | MC | hands | 2nd line above the staff (`q`) | plus |  | 33 |
| `metronome-bell` | メトロノーム（ベル） | MB | hands | 3rd space above the staff (`r`) | plus |  | 34 |

Notehead meanings: drums use a filled oval; cymbals and hi-hat use x; the china cymbal uses a circled x; the ride cymbal (bell) uses an open diamond;
auxiliary percussion uses triangles, plus signs and filled/open diamonds to distinguish it from the drum set.
For x and circled-x noteheads, the stem starts at the end of an arm of the x (the upper right for stem up, the lower left for stem down), not at the center of the x.

## Open/Closed Marks

| `mark` | PDF | MusicXML |
| --- | --- | --- |
| `open` | small circle ○ | `technical/open` |
| `half-open` | ⊖ | `technical/half-muted` |
| `closed` | ＋ | `technical/stopped` |

The mark is printed above the **actual notehead**: 3 positions high (one and a half line spaces) for hands, and 2 positions high (one line space, to avoid down stems and beams) for feet,
so it never drifts with the instrument's position. The score and the legend use the same placement. For example, the ○ of an open hi-hat (1st space above the staff) sits directly above its own x notehead.
When a notehead is moved to the other side of the stem because of a second, the mark moves with it.

## Note Values

Drum notation records only the moment of each strike and does not express MIDI note lengths. The value of each note is inferred as follows:

- A note lasts until the next note in the same voice, but not past the end of its beat, so the longest value is a quarter note.
- Values available in a straight beat: quarter, dotted eighth, eighth, sixteenth.
- The rest of the beat is filled with rests, so that every beat and every bar of every voice adds up exactly.

For example, if the feet play the bass drum only on beat 1, one quarter note is printed, followed by rests (see "Rests" for the PDF rules).

## Beams

- Beams are grouped by beat and **never cross a beat**.
- In each beat, the run of notes from the first note up to the first rest is joined by one primary beam; notes after a rest within the beat get their own flags.
- Eighth notes get one beam, sixteenth notes two. Adjacent sixteenths share the second beam. An isolated sixteenth in a beam group gets a short beam (hook):
  pointing right at the start of the group, left otherwise (for example "dotted eighth + sixteenth" and "sixteenth + eighth + sixteenth").
- A beat with only one note has no beam; eighths and sixteenths get flags.
- Beam height follows the outermost noteheads of the whole group, and a stem never passes through a notehead of a chord.

## Triplets and Sextuplets

- Whether a beat is written as a triplet is decided independently for each beat and each voice (see "Quantization" in [metadata.en.md](metadata.en.md) for the rules). A triplet applies only within the beat it was detected in.
- A voice that uses only eighth-triplet positions gets the numeral **3** (3:2); a voice that uses sixteenth-sextuplet positions gets **6** (6:4).
- When the whole group is joined by one beam, the numeral is printed on the beam and MusicXML uses `bracket="no"`.
- When the group contains a rest (for example a shuffle's "note, rest, note") or notes with flags so that it is not one beam, the PDF prints the numeral above the group (hands) or below it (feet)
  without a bracket; MusicXML uses `bracket="yes"`. The same applies when the group starts with a rest.
- In a triplet beat, if all notes of a voice fall on straight sixteenth positions (on the beat, at 1/4, 1/2 and 3/4 of the beat), that voice is written as a straight beat as usual,
  without a triplet mark (for example hands playing a triplet while the feet play quarter or sixteenth notes).
- On the sixteenth grid, when eighth notes and eighth triplets are mixed in the same voice in the same beat (on the beat, at 1/3 and 1/2 of the beat), they fall on the sextuplet grid and are written as a sextuplet;
  mixing sixteenth notes with triplets (for example at 1/4 and 1/3 of the beat) is an error. On the eighth grid only eighth triplets exist, so both kinds of mixing are errors.
- When a triplet beat has several notes, each note is written as at most an eighth triplet and the remainder is filled with rests.
- Rests inside a triplet group are printed per voice like other rests (see "Rests").

## Grace Notes

- A weaker strike of the same MIDI note very close before the main note (by default within a thirty-second note) is written as a grace note before the main note.
  One grace note (flam): in the PDF, a small eighth grace note with a slash; in MusicXML, an eighth note with `<grace slash="yes"/>`.
  Two grace notes (drag): in the PDF, two smaller sixteenth grace notes joined by two beams; in MusicXML, two sixteenth `<grace/>` elements with beams and no slash.
- Grace notes take no time value. A DAW sometimes puts the grace note and sometimes the main note on the grid, so quantization takes whichever of the two is closer to the grid as the position of the main note.

## Ghost Notes and Accents

Enabled only when the metadata sets `dynamics.ghost_below` / `dynamics.accent_above`, and applied to the hands only:

- ghost note: the notehead gets parentheses (MusicXML `notehead parentheses="yes"`);
- accent: a `>` above the notehead (MusicXML `articulations/accent`).

## Rests

- **MusicXML**: every voice has complete rests. Rests inside a beat are filled with sixteenth / eighth / dotted-eighth rests (a dot only at the start of a beat);
  a whole-beat rest is a quarter rest, a two-beat gap starting on beat 1 or beat 3 of a 4/4 bar is a half rest, and a voice that is empty for the whole bar gets a whole-bar rest.
- **PDF**: as in MusicXML, **each voice fills every beat on its own** (the convention in drum notation): rests of the hand voice are printed higher, those of the foot voice lower.
  When both voices have a rest of the same length at the same time (and both are straight or both are triplet), they are merged into one rest printed at the center of the staff.
  When a voice has no notes in a whole bar, that voice's whole-bar rest is printed in the middle of the bar; a bar where neither voice has notes gets one centered whole-bar rest.
- A completely empty pickup bar: if its length is exactly one note value (1, 2, 3 or 4 beats), one rest is printed; if it is longer (5 beats or more), several quarter rests are printed.

## Empty Bars and Multi-Measure Rests

- A single empty bar gets a whole-bar rest.
- Two or more consecutive empty bars are merged into a multi-measure rest (a thick bar with the number of bars in the PDF, `multiple-rest` in MusicXML).
  Counting restarts at a bar with a time signature change or a tempo change; pickup bars are not merged.

## Time Signatures, Pickups and Tempo

- The time signature is printed in the first bar; after that, a new one is printed only in bars where it changes. A time signature change can only fall on a barline.
- A pickup bar is numbered 0 (MusicXML `implicit="yes"`) and prints its own time signature (for example 2/4); the following bars are numbered from 1.
- The starting tempo is printed as `BPM` in the title block; later tempo changes in the MIDI are printed as `♩ = value` at the start of the bar they fall in (a change in the middle of a bar is also marked at the start of that bar).

## Layout

- A4 portrait; each system holds at most 4 bars (a multi-measure rest counts as one), with line breaks according to content width. If the last system is very short, it is merged into the previous one
  so that a single bar is not stretched across a whole line, so a merged system has at most 5 bars. A final barline is printed at the end of the piece.
- The bar number is printed at the start of each system.
- The top of the first page is the title block (followed by the legend when the legend is enabled); continuation pages have `<song title>　<artist>　ドラム譜` at the top; every page has its page number `n / N` at the bottom.

## Legend

- Not printed by default. With the metadata `legend: true` or the command-line `--legend`, it is printed below the title block on the first page; `--no-legend` takes precedence over the metadata.
- It lists only the instruments **actually used** in the piece: hands first, then feet, each from high to low.
- Each entry is a notehead on a short staff (with its open/closed mark), and below it the abbreviation and the Japanese name (copyable text); in a Japanese name, the part starting at a full-width parenthesis `（…）` moves to a second line.
  The staff lines of all entries are aligned vertically.
- Instruments with the same position, notehead, mark and voice cannot be told apart on the score, so the legend merges them into one entry (see [drum-maps.en.md](drum-maps.en.md)).

## What Is Not Done

- Roll and tremolo marks are not notated, and neither is sticking (left/right hand order), because the MIDI contains no such information.
- Thirty-second notes, other tuplets such as quintuplets, and compound meters (6/8, 12/8) are not supported; such input is an error rather than being approximated.
- Auxiliary percussion does not get a separate staff.
