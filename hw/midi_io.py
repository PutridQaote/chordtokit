"""
MIDI input/output interface for ChordToKit.
Handles port selection and message filtering.
"""
import re
from typing import List, Optional, Tuple, Dict, Any
import mido

def _dedupe(names: List[str]) -> List[str]:
    """Remove duplicate port names."""
    return list(dict.fromkeys(names))

def _pick_by_name(names: List[str], target: Optional[str]) -> Optional[str]:
    """Find exact match in port names."""
    if not target:
        return None
    for n in names:
        if n == target:
            return n
    return None

def _pick_by_substr(names: List[str], substr: Optional[str]) -> Optional[str]:
    """Find first name containing substring."""
    if not substr:
        return None
    for n in names:
        if substr.lower() in n.lower():
            return n
    return None

def _is_virtual_through(name: str) -> bool:
    """Check if port is an ALSA virtual through port or RtMidi port."""
    patterns = [
        r'midi\s+through',      # "Midi Through Port-0"
        r'rtmidi',              # "RtMidiIn Client", "RtMidiOut Client"
        r'through',             # Generic "through" ports
    ]
    return any(re.search(pattern, name, re.IGNORECASE) for pattern in patterns)

class MidiTap:
    """A MIDI input monitor that doesn't interfere with normal operations."""
    
    def __init__(self, port_name: str):
        self.port_name = port_name
        self.port = None
        self._last_messages = []
        
    def open(self) -> bool:
        """Open the tap port for monitoring."""
        try:
            self.port = mido.open_input(self.port_name)
            print(f"Opened MIDI tap: {self.port_name}")
            return True
        except Exception as e:
            print(f"Error opening MIDI tap {self.port_name}: {e}")
            return False
    
    def close(self):
        """Close the tap port."""
        if self.port:
            try:
                self.port.close()
                print(f"Closed MIDI tap: {self.port_name}")
            except Exception:
                pass
            self.port = None
    
    def get_recent_notes(self, max_age_seconds: float = 2.0) -> List[int]:
        """Get note_on messages from the last few seconds."""
        if not self.port:
            return []
            
        import time
        current_time = time.monotonic()
        
        # Read new messages
        for msg in self.port.iter_pending():
            if msg.type == 'note_on' and msg.velocity > 0:
                self._last_messages.append((current_time, msg.note))
        
        # Clean old messages
        cutoff_time = current_time - max_age_seconds
        self._last_messages = [(t, note) for t, note in self._last_messages if t > cutoff_time]
        
        # Return just the note numbers
        return [note for _, note in self._last_messages]
    
    def get_latest_note(self) -> Optional[int]:
        """Get the most recent note, if any."""
        recent_notes = self.get_recent_notes()
        return recent_notes[-1] if recent_notes else None

class Midi:
    def __init__(self, cfg: Optional[dict] = None):
        cfg = cfg or {}
        
        # Get port lists, filtering out problematic ports
        all_ins = mido.get_input_names()
        all_outs = mido.get_output_names()
        
        ins = [name for name in _dedupe(all_ins) if not _is_virtual_through(name)]
        outs = [name for name in _dedupe(all_outs) if not _is_virtual_through(name)]

        exact_in = _pick_by_name(ins, cfg.get("midi_in_name"))
        exact_out = _pick_by_name(outs, cfg.get("midi_out_name"))

        self._in_name = exact_in or _pick_by_substr(ins, cfg.get("midi_in_substr", "triggerio"))
        self._out_name = exact_out or _pick_by_substr(outs, cfg.get("midi_out_substr", "triggerio"))

        self._in_port = None
        self._out_port = None

        # DDTi output tap for monitoring what the DDTi is sending
        self._ddti_tap = None
        self._setup_ddti_tap()

    def open_ports(self):
        """Open MIDI input/output ports based on current settings."""
        self.close_ports()
        
        if self._in_name:
            try:
                self._in_port = mido.open_input(self._in_name)
                print(f"Opened MIDI input: {self._in_name}")
            except Exception as e:
                print(f"Error opening MIDI input {self._in_name}: {e}")
                self._in_port = None
                
        if self._out_name:
            try:
                self._out_port = mido.open_output(self._out_name)
                print(f"Opened MIDI output: {self._out_name}")
            except Exception as e:
                print(f"Error opening MIDI output {self._out_name}: {e}")
                self._out_port = None

    def close_ports(self):
        """Close all MIDI ports."""
        if self._in_port:
            try:
                self._in_port.close()
                print(f"Closed MIDI input: {self._in_name}")
            except Exception:
                pass
            self._in_port = None
            
        if self._out_port:
            try:
                self._out_port.close()
                print(f"Closed MIDI output: {self._out_name}")
            except Exception:
                pass
            self._out_port = None

        # Close DDTi tap
        if self._ddti_tap:
            self._ddti_tap.close()
            self._ddti_tap = None

    def reopen_ports(self):
        """Close and reopen all ports."""
        self.close_ports()
        self.open_ports()

    def _setup_ddti_tap(self):
        """Set up a tap to monitor DDTi output."""
        # Look for DDTi output port (different from input port we send to)
        all_ins = mido.get_input_names()
        ddti_out_port = None
        
        # The DDTi typically has both input and output ports
        # We send TO the DDTi input, but we want to monitor the DDTi output
        for name in all_ins:
            if any(pattern in name.lower() for pattern in ["triggerio", "ddti", "ddrum"]):
                # Look for output-like naming patterns
                if any(out_pattern in name.lower() for out_pattern in ["out", "output", "midi out"]):
                    ddti_out_port = name
                    break
        
        if ddti_out_port:
            self._ddti_tap = MidiTap(ddti_out_port)
            if not self._ddti_tap.open():
                self._ddti_tap = None
        else:
            print("No DDTi output port found for monitoring")

    # ----- Menu API (for settings screen) -----
    def get_inputs(self) -> List[str]:
        """Get list of available input port names."""
        all_ins = mido.get_input_names()
        return [name for name in _dedupe(all_ins) if not _is_virtual_through(name)]

    def get_outputs(self) -> List[str]:
        """Get list of available output port names."""
        all_outs = mido.get_output_names()
        return [name for name in _dedupe(all_outs) if not _is_virtual_through(name)]

    def get_selected_in(self) -> Optional[str]:
        """Get currently selected input port name."""
        return self._in_name

    def get_selected_out(self) -> Optional[str]:
        """Get currently selected output port name."""
        return self._out_name

    def set_in(self, name: str):
        """Set input port by name and reopen."""
        self._in_name = name
        self.reopen_ports()

    def set_out(self, name: str):
        """Set output port by name and reopen."""
        self._out_name = name
        self.reopen_ports()

    # ----- Runtime I/O -----
    def iter_input(self):
        """Get pending MIDI input messages (no thru handling)."""
        if self._in_port is None:
            return []
        return list(self._in_port.iter_pending())

    def send(self, msg):
        """Send a MIDI message to the main output port (DDTi)."""
        if self._out_port is None:
            return False
        try:
            self._out_port.send(msg)
            return True
        except Exception as e:
            print(f"Error sending MIDI: {e}")
            return False

    def get_ddti_latest_note(self) -> Optional[int]:
        """Get the latest note from DDTi output."""
        if self._ddti_tap:
            return self._ddti_tap.get_latest_note()
        return None
