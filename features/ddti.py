"""DDTi SysEx builder/sender extracted from your PoC.
- Loads baseline template bytes once (without F0/F7)
- Writes 4 note values at known offsets
- Returns a mido Message('sysex', data=payload) for sending
"""
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from dataclasses import dataclass
import time

from mido import Message

from constants import DDTI_TEMPLATE_PATH, DDTI_NOTE_OFFSETS

@dataclass
class _Kit0Cache:
    bulk: Optional[bytes] = None      # 76-byte frame (opcode 70 / kit index 0)
    param: Optional[bytes] = None     # 16-byte frame (opcode 10 / kit index 0)
    notes: Optional[List[int]] = None
    ts: Optional[float] = None

class DDTi:
    def __init__(self, template_path: Path = DDTI_TEMPLATE_PATH, note_offsets: List[int] = DDTI_NOTE_OFFSETS):
        self.template_path = Path(template_path)
        self.note_offsets = list(note_offsets)
        self._template = self._load_template()
        
        # Track current DDTi state for partial updates
        self._current_state: Optional[List[int]] = None
        
        # Session-only kit0 cache (fresh each boot)
        self._kit0 = _Kit0Cache()
        self._bulk_note_offsets = [11,17,23,29]  # verify against 76-byte frame

    def set_current_state(self, notes: List[int]):
        """Explicitly set the known current state of the DDTi."""
        if len(notes) != len(self.note_offsets):
            raise ValueError(f"Need exactly {len(self.note_offsets)} notes")
        self._current_state = list(notes)
    
    def get_current_state(self) -> Optional[List[int]]:
        """Get the last known DDTi state."""
        return self._current_state[:] if self._current_state else None
    
    def _load_template(self) -> bytes:
        data = self.template_path.read_bytes()
        # Many dumps include extra bytes; your PoC used the first ~90.
        # Keep full buffer unless you know a strict length; the offsets are within it.
        return data

    @staticmethod
    def _validate_notes(notes: Iterable[int], expected_count: int) -> List[int]:
        ns = list(notes)
        if len(ns) != expected_count:
            raise ValueError(f"Need exactly {expected_count} MIDI notes, got {len(ns)}")
        for n in ns:
            if not (0 <= int(n) <= 127):
                raise ValueError(f"Bad MIDI note: {n}")
        return [int(n) & 0x7F for n in ns]

    def build_full_sysex(self, notes: Iterable[int]) -> Message:
        """Build SysEx for all 4 triggers (current behavior)."""
        ns = self._validate_notes(notes, expected_count=len(self.note_offsets))
        buf = bytearray(self._template)
        for i, off in enumerate(self.note_offsets):
            buf[off] = ns[i]
        
        # Update our state tracking
        self._current_state = list(ns)
        return Message('sysex', data=bytes(buf))
    
    def build_partial_sysex(self, trigger_notes: Dict[int, int]) -> Message:
        """Build SysEx for specific triggers only.
        
        Args:
            trigger_notes: Dict mapping trigger_index -> new_note_value
                          e.g., {0: 36, 2: 42} changes triggers 0 and 2
        
        Returns:
            Message with SysEx that updates only specified triggers
            
        Raises:
            ValueError: If current state is unknown or invalid trigger indices
        """
        if self._current_state is None:
            raise ValueError("Cannot do partial update: current DDTi state unknown. "
                           "Call set_current_state() or build_full_sysex() first.")
        
        # Validate trigger indices
        for trigger_idx in trigger_notes.keys():
            if not (0 <= trigger_idx < len(self.note_offsets)):
                raise ValueError(f"Invalid trigger index: {trigger_idx}")
        
        # Start with current state
        new_state = list(self._current_state)
        
        # Apply partial changes
        for trigger_idx, new_note in trigger_notes.items():
            if not (0 <= new_note <= 127):
                raise ValueError(f"Invalid MIDI note: {new_note}")
            new_state[trigger_idx] = new_note
        
        # Build SysEx with the updated state
        buf = bytearray(self._template)
        for i, off in enumerate(self.note_offsets):
            buf[off] = new_state[i]
        
        # Update our state tracking
        self._current_state = new_state
        return Message('sysex', data=bytes(buf))
    
    def build_trigger_change_sysex(self, captured_triggers: List[int], new_notes: List[int]) -> Message:
        """Build SysEx for variable-trigger mode.
        
        Args:
            captured_triggers: List of DDTi note values that were hit
            new_notes: List of keyboard notes to assign (same length)
            
        Returns:
            Message with SysEx that updates only the captured triggers
        """
        if len(captured_triggers) != len(new_notes):
            raise ValueError("captured_triggers and new_notes must have same length")
        
        if self._current_state is None:
            raise ValueError("Cannot do variable-trigger update: current DDTi state unknown")
        
        # Map captured trigger notes to trigger indices
        trigger_updates = {}
        default_mapping = {36: 0, 38: 1, 42: 2, 49: 3}  # Default trigger note -> index
        
        for trigger_note, new_note in zip(captured_triggers, new_notes):
            # Find which trigger index this note corresponds to
            trigger_idx = None
            
            # First try to find it in current state
            try:
                trigger_idx = self._current_state.index(trigger_note)
            except ValueError:
                # Fall back to default mapping
                trigger_idx = default_mapping.get(trigger_note)
                
            if trigger_idx is None:
                print(f"Warning: Cannot map trigger note {trigger_note} to trigger index")
                continue
                
            trigger_updates[trigger_idx] = new_note
        
        return self.build_partial_sysex(trigger_updates)
    
    # Keep existing method for backward compatibility
    def build_sysex(self, notes: Iterable[int]) -> Message:
        """Legacy method - delegates to build_full_sysex."""
        return self.build_full_sysex(notes)
    
    def send_sysex(self, out_port, notes: Iterable[int]) -> None:
        msg = self.build_sysex(notes)
        out_port.send(msg)

    # --- Kit0 ingestion / stateless single-note support (session only) ---
    def ingest_sysex_frame(self, data: bytes):
        """
        Call this for every incoming SysEx from the DDTi IN port.
        Captures kit0 bank frames (bulk 76B or param 16B). No persistence.
        """
        ln = len(data)
        if ln == 76 and ln > 10 and data[7] == 70 and data[8] == 1 and data[9] == 0:
            self._kit0.bulk = bytes(data)
            self._kit0.notes = None
            self._kit0.ts = time.time()
            print("DDTi: Ingested kit0 bulk frame")
        elif ln == 16 and ln > 10 and data[7] == 10 and data[8] == 2 and data[9] == 0:
            self._kit0.param = bytes(data)
            # param optional; do not reset notes
            print("DDTi: Ingested kit0 param frame")

    def have_kit0_bulk(self) -> bool:
        return self._kit0.bulk is not None

    def kit0_age_seconds(self) -> Optional[float]:
        return (time.time() - self._kit0.ts) if self._kit0.ts else None

    def extract_kit0_notes(self) -> Optional[List[int]]:
        if not self._kit0.bulk:
            return None
        if self._kit0.notes is not None:
            return list(self._kit0.notes)
        if max(self._bulk_note_offsets) >= len(self._kit0.bulk):
            print("DDTi: bulk frame too short for note offsets")
            return None
        self._kit0.notes = [self._kit0.bulk[o] & 0x7F for o in self._bulk_note_offsets]
        return list(self._kit0.notes)

    def build_kit0_single_note_patch(self, old_note: int, new_note: int) -> Optional[Message]:
        """
        Replace ALL occurrences of old_note with new_note in cached kit0 bulk frame.
        Returns full 76-byte kit0 frame Message or None if unavailable / no change.
        """
        if not self.have_kit0_bulk():
            print("DDTi: No kit0 bulk cached (press DUMP on module)")
            return None
        notes = self.extract_kit0_notes()
        if notes is None:
            return None
        matches = [i for i,n in enumerate(notes) if n == old_note]
        if not matches:
            print(f"DDTi: old_note {old_note} not found in kit0 notes {notes}")
            return None
        if old_note == new_note:
            print("DDTi: old and new note identical; skipping")
            return None
        buf = bytearray(self._kit0.bulk)
        for idx in matches:
            off = self._bulk_note_offsets[idx]
            buf[off] = new_note & 0x7F
            notes[idx] = new_note & 0x7F
        self._kit0.bulk = bytes(buf)
        self._kit0.notes = notes
        print(f"DDTi: Patched kit0 {old_note}->{new_note} at indices {matches}; new notes {notes}")
        return Message('sysex', data=bytes(buf))