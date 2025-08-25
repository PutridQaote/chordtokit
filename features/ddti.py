"""DDTi SysEx builder/sender extracted from your PoC.
- Loads baseline template bytes once (without F0/F7)
- Writes 4 note values at known offsets
- Returns a mido Message('sysex', data=payload) for sending
"""
from pathlib import Path
from typing import Iterable, List

from mido import Message

from constants import DDTI_TEMPLATE_PATH, DDTI_NOTE_OFFSETS

class DDTi:
    def __init__(self, template_path: Path = DDTI_TEMPLATE_PATH, note_offsets: List[int] = DDTI_NOTE_OFFSETS):
        self.template_path = Path(template_path)
        self.note_offsets = list(note_offsets)
        self._template = self._load_template()

    def _load_template(self) -> bytes:
        data = self.template_path.read_bytes()
        # Many dumps include extra bytes; your PoC used the first ~90.
        # Keep full buffer unless you know a strict length; the offsets are within it.
        return data

    @staticmethod
    def _validate_notes(notes: Iterable[int]) -> List[int]:
        ns = list(notes)
        if len(ns) != 4:
            raise ValueError("Need exactly 4 MIDI notes")
        for n in ns:
            if not (0 <= int(n) <= 127):
                raise ValueError(f"Bad MIDI note: {n}")
        return [int(n) & 0x7F for n in ns]

    def build_sysex(self, notes: Iterable[int]) -> Message:
        ns = self._validate_notes(notes)
        buf = bytearray(self._template)
        for i, off in enumerate(self.note_offsets):
            buf[off] = ns[i]
        # mido wraps data with F0 ... F7 when you create a sysex Message
        return Message('sysex', data=bytes(buf))

    def send_sysex(self, out_port, notes: Iterable[int]) -> None:
        msg = self.build_sysex(notes)
        out_port.send(msg)