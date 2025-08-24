#!/usr/bin/env python3
import sys, pathlib

def load(name):
    return pathlib.Path(name).read_bytes()

BASE = load("kit0_clean.bin")

def positions(changed, old_val, new_val):
    """Return every index where BASE byte == old_val and changed byte == new_val."""
    return [i for i,(b,c) in enumerate(zip(BASE, changed)) if b == old_val and c == new_val]

tests = [
    ("kit_t2_clean.bin",  2, 60),   # Trig‑2 we set to MIDI 60
    ("kit_t3_clean.bin",  3, 70),   # Trig‑3 → 70
    ("kit_t4_clean.bin",  4, 80),   # Trig‑4 → 80
]

for fname, oldv, newv in tests:
    idxs = positions(load(fname), oldv, newv)
    print(f"{fname[:-10]} offsets → {idxs}")
