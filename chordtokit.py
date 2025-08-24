#!/usr/bin/env python3
import mido, time
from collections import OrderedDict

with open('/home/mty/data/kit0_clean.bin', 'rb') as f:
    SYSEX_TEMPLATE = list(f.read()) # 90 bytes (no F0/F7)

# Note-value byte offsets (zero-based)
# trigger-1 value byte = 11 (found with cmp between two sysex dumps where kit0 trigger1 was the only note that chagned
# subsequent triggers =  +15 each (5 tuples * 3 bytes)
NOTE_OFFSETS = [11, 17, 23, 29]

def build_sysex(notes):
    data = SYSEX_TEMPLATE[:]
    for pos, note in zip(NOTE_OFFSETS, notes):
        data[pos] = note & 0x7F
    return bytes(data)

def main():
    in_name  = 'Arturia KeyStep 32 MIDI 1'
    out_name = 'TriggerIO TriggerIO MIDI In'

    in_port  = mido.open_input(in_name)
    out_port = mido.open_output(out_name)

    print("Chord‑to‑Kit ready — play four different notes…\n")
    bucket = []

    while True:
        bucket.extend(
            msg.note for msg in in_port.iter_pending()
            if msg.type == 'note_on' and msg.velocity
        )

        if len(bucket) >= 4:
            chord = sorted(list(OrderedDict.fromkeys(bucket)))[:4]
            if len(chord) == 4:
                print("Captured:", chord, "→ sending SysEx")
                data = build_sysex(chord)
                print("Len:", len(data), "\nSysEx bytes:", list(data))
                out_port.send(mido.Message('sysex', data=data))
            else:
                print("Need 4 distinct notes; got", chord)
            bucket.clear()

        time.sleep(0.01)

if __name__ == '__main__':
    main()
