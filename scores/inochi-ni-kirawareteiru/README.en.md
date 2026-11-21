[日本語](README.md) | [简体中文](README.zh-CN.md) | [English](README.en.md)

# 命に嫌われている。 ドラム譜

| Item | Details |
| --- | --- |
| Title | 命に嫌われている。 |
| Credits | 作詞・作曲：カンザキイオリ　歌：カンザキイオリ（セルフカバー） |
| Album | 『不器用な男』 |
| Drum transcription and arrangement | 音宮 (printed on the score as 「ドラム採譜・編曲：音宮」) |
| Tempo / time signature | BPM 200. The 2 empty beats at the start are printed as a 2/4 pickup bar, followed by 4/4 |

本譜には採譜者による再構成・創作を含みます。 (This score contains the transcriber's reconstruction and original work.)

## Files and sources

| File | Source |
| --- | --- |
| `source.mid` | The original MIDI as provided: exported directly from FPC in FL Studio, notes on channel 1, track name `FPC 1`, with 4 empty beats at the start. **Do not modify** |
| `gm-channel10.mid` | Derived file: `source.mid` changed to GM channel 10 with the note timing unchanged, for software that only recognizes channel 10. The conversion itself does not need it |
| `metadata.yaml` | Credits and conversion settings: `drum_map: fpc-default`, `source_leading_beats: 4`, `pickup_beats: 2`, 16th-note grid |
| `score.musicxml` | Editable MusicXML 4.0 generated from `source.mid` |
| `score.pdf` | A4 printable drum score generated from `source.mid` and checked by eye |

Command that generates `gm-channel10.mid`:

```bash
python3 scripts/retag_gm_channel10.py scores/inochi-ni-kirawareteiru/source.mid \
  --out scores/inochi-ni-kirawareteiru/gm-channel10.mid
```

## Regenerating

Run from the repository root:

```bash
python3 scripts/build_score.py scores/inochi-ni-kirawareteiru/source.mid \
  --metadata scores/inochi-ni-kirawareteiru/metadata.yaml \
  --out-dir build/inochi
```

Using `gm-channel10.mid` as input gives the same result (each has only one track with notes, so it is selected automatically).
After confirming the exit code is 0 and checking every page of `build/inochi/score.pdf` by eye, copy `score.musicxml` and `score.pdf` into this directory.

## Notes

- This is a **fan transcription**, not an official score and not a publisher-licensed score. The score contains the transcriber's own re-creation and is not guaranteed to match the original recording note for note.
- The score is typeset automatically from the MIDI. Grace notes, the merging of duplicate triggers and similar choices are notation inferences and do not mean the score is equivalent to the MIDI note for note.

## Copyright

The copyright and related rights in the song belong to their respective owners. This repository's MIT license does not apply to this directory.
The credit and arrangement notes are **not** a distribution license: do not publish this score without the rights holders' permission.
