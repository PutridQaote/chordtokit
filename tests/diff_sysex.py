#!/usr/bin/env python3
"""
Find the byte‑offsets that change when you tweak Triggers 2‑4 on the DDTi.

Usage:  python3 diff_sysex.py
Works in the current directory if the four .syx files are here.
"""
from pathlib import Path

FILES   = ['kit_baseline.syx', 'kit_t2.syx', 'kit_t3.syx', 'kit_t4.syx']
TARGETS = dict(zip(FILES, ['baseline', 'Trig‑2', 'Trig‑3', 'Trig‑4']))

def first_sysex_packet(raw: bytes) -> bytes:
    """Return bytes from the first F0 up to (and including) the next F7."""
    try:
        start = raw.index(0xF0)
        end   = raw.index(0xF7, start)     # first 0xF7 that follows
        return raw[start:end+1]
    except ValueError:
        raise RuntimeError("No complete F0…F7 packet found!")

# --- load packets ----------------------------------------------------------
packets = {name: first_sysex_packet(Path(name).read_bytes()) for name in FILES}
base    = packets['kit_baseline.syx']
print(f"Baseline packet length: {len(base)} bytes")

# --- diff each modified packet against baseline ---------------------------
for name, pkt in packets.items():
    if name == 'kit_baseline.syx':
        continue
    diffs = [i for i,(b,c) in enumerate(zip(base, pkt)) if b != c]
    print(f"{TARGETS[name]} → {len(diffs)} bytes differ; first indices: {diffs[:6]}")
