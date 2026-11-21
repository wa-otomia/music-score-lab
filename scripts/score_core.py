"""Common, deterministic FPC/GM percussion MIDI transcription model.

Designed for drum performances quantized to sixteenths. Not a general-purpose
music notation inference engine; unusual tuplets and sustained-note articulations
must be edited in MusicXML in a dedicated editor.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mido
import yaml


@dataclass
class Transcription:
    bars: list[dict[int, dict[int, dict[str, Any]]]]
    mapping: dict[int, dict[str, str]]
    metadata: dict[str, Any]
    tpq: int
    bar_ticks: int
    pickup_ticks: int
    grid: int
    source_hits: int
    grace_hits: int
    duplicate_hits: int


def read_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a map: {path}")
    return value


def build_score(midi_file: Path, metadata_file: Path, config_file: Path) -> Transcription:
    meta = read_yaml(metadata_file)
    mapping = {int(k): v for k, v in read_yaml(config_file).items()}
    for k, v in mapping.items():
        if v.get("part") not in ("hand", "foot") or v.get("kind") not in ("normal", "x", "open"):
            raise ValueError(f"Invalid drum map for MIDI note {k}")
        if not (isinstance(v.get("staff_pos"), str) and len(v["staff_pos"]) == 1):
            raise ValueError(f"Invalid staff_pos for MIDI note {k}")

    midi = mido.MidiFile(midi_file)
    tpq = midi.ticks_per_beat
    beats, beat_type = int(meta.get("beats", 4)), int(meta.get("beat_type", 4))
    if beat_type != 4 or beats != 4:
        raise ValueError("The current MusiXTeX converter supports 4/4 only; extend it for other meters")
    bar_ticks = beats * tpq
    subdivisions = int(meta.get("quantize_divisions_per_beat", 4))
    if subdivisions not in (2, 4) or tpq % subdivisions:
        raise ValueError("Quantization must divide ticks_per_beat (supports eighths and sixteenths)")
    grid = tpq // subdivisions
    pickup_beats = int(meta.get("pickup_beats", 0))
    source_leading_beats = int(meta.get("source_leading_beats", pickup_beats))
    if not 0 <= pickup_beats < beats or source_leading_beats < pickup_beats:
        raise ValueError("Invalid silent pickup or source leading-beat offset")
    pickup_ticks = pickup_beats * tpq
    shift = (source_leading_beats - pickup_beats) * tpq

    absolute_hits = []
    for track in midi.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                absolute_hits.append((tick, int(msg.note), int(msg.velocity)))
    if not absolute_hits:
        raise ValueError("No note-on events found")
    missing = sorted(set(note for _, note, _ in absolute_hits) - mapping.keys())
    if missing:
        raise ValueError(f"Missing GM percussion mapping for MIDI notes: {missing}; extend {config_file}")

    # Quantize to the nearest grid cell, preserving the original velocities.
    grouped: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for tick, pitch, velocity in absolute_hits:
        qt = round(tick / grid) * grid - shift
        if qt < pickup_ticks:
            raise ValueError("Found a note before the end of the silent pickup; this engraver handles silent pickups only")
        grouped[(qt, pitch)].append((tick, velocity))

    by_tick: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    grace_count = duplicate_count = 0
    for (tick, pitch), raw_hits in grouped.items():
        raw_hits.sort()
        main = max(raw_hits, key=lambda item: item[1])
        grace_hits = [x for x in raw_hits if x != main and x[0] < main[0] and
                      abs(x[0] - main[0]) <= grid // 2 and x[1] < main[1]]
        grace_count += len(grace_hits)
        duplicate_count += max(0, len(raw_hits) - 1 - len(grace_hits))
        by_tick[tick][pitch] = {"velocity": main[1], "grace": bool(grace_hits)}

    first_full = pickup_ticks
    n_full = 1 + (max(by_tick) - first_full) // bar_ticks
    bars = ([{}] if pickup_ticks else [])
    for n in range(n_full):
        start = first_full + n * bar_ticks
        bars.append(dict(sorted((tick - start, hits) for tick, hits in by_tick.items()
                                if start <= tick < start + bar_ticks)))
    return Transcription(bars, mapping, meta, tpq, bar_ticks, pickup_ticks, grid,
                         len(absolute_hits), grace_count, duplicate_count)


def voice_durations(bar: dict, score: Transcription) -> dict[tuple[int, str], int]:
    """Infer durations from drum onsets independently in hand and foot voices."""
    d = {}
    for voice in ("hand", "foot"):
        tt = sorted(t for t, ns in bar.items()
                    if any(score.mapping[p]["part"] == voice for p in ns))
        for i, t in enumerate(tt):
            gap = (tt[i + 1] if i + 1 < len(tt) else score.bar_ticks) - t
            unit = score.tpq // 4
            d[(t, voice)] = unit if gap < 1.5 * unit else 2 * unit if gap < 2.5 * unit else 3 * unit if gap < 3.5 * unit else 4 * unit
    return d


def hand_beams(bar: dict, score: Transcription) -> dict[int, tuple[str, int]]:
    """Beams are confined to individual quarter-note beats, not whole measures."""
    hand = set(t for t, ns in bar.items()
               if any(score.mapping[p]["part"] == "hand" for p in ns))
    beam = {}
    beat_ticks, small = score.tpq, score.tpq // 4
    for beat in range(0, score.bar_ticks, beat_ticks):
        four = [beat + i * small for i in range(4)]
        if all(t in hand for t in four):
            for i, t in enumerate(four):
                beam[t] = ("start" if i == 0 else "end" if i == 3 else "mid", 2)
            continue
        for sub in (beat, beat + beat_ticks // 2):
            pair = [sub, sub + small]
            if all(t in hand and t not in beam for t in pair):
                beam[pair[0]] = ("start", 2)
                beam[pair[1]] = ("end", 2)
        pair = [beat, beat + beat_ticks // 2]
        if all(t in hand and t not in beam for t in pair):
            beam[pair[0]] = ("start", 1)
            beam[pair[1]] = ("end", 1)
    return beam


def chunks(length: int, tpq: int) -> list[int]:
    result = []
    for unit in (2 * tpq, tpq, 3 * tpq // 4, tpq // 2, tpq // 4):
        while length >= unit:
            result.append(unit)
            length -= unit
    if length:
        raise ValueError(f"Cannot notate {length} ticks using sixteenth notes")
    return result
