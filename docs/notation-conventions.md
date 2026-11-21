# Japanese-style drum notation

This project uses conventional five-line drumset notation:

| Instrument | GM note | Shape | Voice |
| --- | ---: | --- | --- |
| Bass drum | 36 | Filled | Feet / down-stem |
| Pedal hi-hat | 44 | × | Feet / down-stem |
| Snare (electric) | 40 | Filled | Hands / up-stem |
| Side stick | 37 | × | Hands / up-stem |
| Closed hi-hat | 42 | × | Hands / up-stem |
| Open hi-hat | 46 | × with ○ | Hands / up-stem |
| Crash cymbal | 49 | × | Hands / up-stem |
| Splash cymbal | 55 | × | Hands / up-stem |

Additional tom pitches 43, 47 and 48 use filled noteheads in the upper voice. GM note 40 means **Electric Snare** (38 would mean Acoustic Snare), so conversion must not silently remap pitch 40.

Beam rules: 8ths have one beam, 16ths two beams; beam groups are anchored to a quarter-note beat. The original bug produced one beam for dense 16th-note groups because the cross-head closing macro had the wrong primitive. The current script defines a proper terminal cross-head note.

**Known limits**: 4/4 meter, 8th/16th quantization, silent pickup only, manually configured drum map. Non-quantized material, rolls, flams, non-GM percussion and odd meters require human review or converter extension. Velocity remains in the original MIDI; notation does not claim to preserve every performance nuance. No tool can infer right/left sticking from MIDI alone.
