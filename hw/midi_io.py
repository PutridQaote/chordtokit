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

    def reopen_ports(self):
        """Close and reopen all ports."""
        self.close_ports()
        self.open_ports()

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
