#!/usr/bin/env python3
"""Retag drum MIDI channel events to GM percussion channel 10, without moving notes.

Never overwrites its source. Channel numbering is 1-based for musicians but
mido uses zero-based channel=9 for GM channel 10.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import mido


def retag(source: Path, output: Path):
    if source.resolve() == output.resolve():
        raise ValueError('Output must differ from original source')
    midi = mido.MidiFile(source)
    touched = 0
    for track in midi.tracks:
        for msg in track:
            if hasattr(msg, 'channel'):
                if msg.channel != 9:
                    touched += 1
                msg.channel = 9
    output.parent.mkdir(parents=True, exist_ok=True)
    midi.save(output)
    return touched


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    count = retag(args.source, args.out)
    print(f'Wrote {args.out}; {count} channel events retagged as GM Channel 10')

if __name__ == '__main__': main()
