"""Shared helpers: build drum MIDI fixtures in code (no binary fixtures) and run the engine."""
from __future__ import annotations

import shutil
import sys
from fractions import Fraction
from pathlib import Path

import mido
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import score_core  # noqa: E402

SONG_DIR = ROOT / 'scores' / 'inochi-ni-kirawareteiru'
SONG_MIDI = SONG_DIR / 'source.mid'
SONG_META = SONG_DIR / 'metadata.yaml'

PDF_TOOLS = ('musixtex', 'etex', 'musixflx', 'dvipdfmx', 'xelatex', 'gs')
HAVE_PDF_TOOLS = all(shutil.which(t) for t in PDF_TOOLS)

KICK, SNARE, HH, HHO, CRASH, RIDE, TOM = 36, 38, 42, 46, 49, 51, 47


def _ticks(beat, tpq: int) -> int:
    return int(round(Fraction(beat) * tpq))


def make_midi(path: Path, hits=None, *, tpq: int = 480, channel: int = 10, name: str | None = 'Drums',
              tracks: list[dict] | None = None, sigs: list[tuple] | None = None,
              tempo: float | None = 120, tempos: list[tuple] | None = None,
              gate: int | None = None, charset: str = 'latin1') -> Path:
    """Write a type-1 MIDI file.

    ``hits``: list of ``(beat, note[, velocity[, channel]])``; beat in quarter notes
    (float, int or Fraction).  ``tracks``: list of ``{'hits', 'channel', 'name'}`` for
    multi-track files (replaces ``hits``).  ``channel`` is 1-based.  ``sigs``:
    ``[(beat, numerator, denominator)]``; ``tempos``: ``[(beat, bpm)]``.
    """
    mf = mido.MidiFile(type=1, ticks_per_beat=tpq, charset=charset)
    meta_events = []
    if tempo is not None:
        meta_events.append((0, mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(tempo))))
    for beat, bpm in tempos or []:
        meta_events.append((_ticks(beat, tpq), mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm))))
    for beat, n, d in sigs or []:
        meta_events.append((_ticks(beat, tpq), mido.MetaMessage('time_signature', numerator=n, denominator=d)))
    conductor = mido.MidiTrack()
    now = 0
    for t, msg in sorted(meta_events, key=lambda e: e[0]):
        msg.time = t - now
        now = t
        conductor.append(msg)
    mf.tracks.append(conductor)
    if tracks is None:
        tracks = [{'hits': hits or [], 'channel': channel, 'name': name}]
    gate = gate if gate is not None else max(1, tpq // 16)
    for spec in tracks:
        track = mido.MidiTrack()
        if spec.get('name'):
            track.append(mido.MetaMessage('track_name', name=spec['name'], time=0))
        ch = spec.get('channel', 10) - 1
        events = []
        for h in spec['hits']:
            beat, note = h[0], h[1]
            vel = h[2] if len(h) > 2 else 100
            hch = h[3] - 1 if len(h) > 3 else ch
            t = _ticks(beat, tpq)
            assert t >= 0, h
            events.append((t, 1, note, vel, hch))
            events.append((t + gate, 0, note, 0, hch))
        now = 0
        for t, on, note, vel, hch in sorted(events, key=lambda e: (e[0], e[1])):
            track.append(mido.Message('note_on' if on else 'note_off', note=note, velocity=vel,
                                      channel=hch, time=t - now))
            now = t
        mf.tracks.append(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    mf.save(path)
    return path


def build(tmp_path: Path, hits=None, meta: dict | None = None, *, cli: dict | None = None,
          drum_map=None, fname: str = 'test.mid', **midi_kw) -> score_core.Transcription:
    path = make_midi(tmp_path / fname, hits, **midi_kw)
    metadata = {'title': 'Test'}
    metadata.update(meta or {})
    return score_core.build_score(path, None, drum_map, metadata=metadata, cli=cli)


def events_at(bar: score_core.Bar) -> dict[int, list[int]]:
    """tick in bar → sorted MIDI notes."""
    return {t: sorted(h) for t, h in bar.events.items()}


def bar_of(beats_per_bar: int = 4):
    """Absolute beat offset helper: bar_of()(bar_index, beat) for 4/4."""
    return lambda bar, beat: bar * beats_per_bar + beat


@pytest.fixture(scope='session')
def song():
    return score_core.build_score(SONG_MIDI, SONG_META)
