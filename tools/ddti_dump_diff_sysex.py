#!/usr/bin/env python3
import mido, pathlib

files = ['kit_baseline.syx', 'kit_t2.syx', 'kit_t3.syx', 'kit_t4.syx']
msgs  = {f: mido.read_syx_file(f)[0].data for f in files}   # first SysEx msg

base  = msgs['kit_baseline.syx']
print(f"Baseline length: {len(base)} bytes")                # should be 96

for name, data in msgs.items():
    if name == 'kit_baseline.syx':
        continue
    diffs = [i for i,(b,c) in enumerate(zip(base, data)) if b != c]
    print(f"{name}: {len(diffs)} bytes differ → first 8 diffs: {diffs[:8]}")
