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

        # Keyboard input (for note capture)
        exact_in = _pick_by_name(ins, cfg.get("midi_in_name"))
        self._in_name = exact_in or _pick_by_substr(ins, cfg.get("midi_in_substr", "keyStep"))
        
        # DDTi output (for sending SysEx)
        exact_out = _pick_by_name(outs, cfg.get("midi_out_name"))
        self._out_name = exact_out or _pick_by_substr(outs, cfg.get("midi_out_substr", "triggerio"))
        
        # NEW: DDTi input (for receiving SysEx dumps)
        exact_ddti_in = _pick_by_name(ins, cfg.get("ddti_in_name"))
        self._ddti_in_name = exact_ddti_in or _pick_by_substr(ins, cfg.get("ddti_in_substr", "triggerio"))

        self._in_port = None
        self._out_port = None
        self._ddti_in_port = None  # NEW: Dedicated DDTi input port

    def open_ports(self):
        """Open MIDI input/output ports based on current settings."""
        self.close_ports()
        
        # Main keyboard input
        if self._in_name:
            try:
                self._in_port = mido.open_input(self._in_name)
                print(f"Opened MIDI input: {self._in_name}")
            except Exception as e:
                print(f"Error opening MIDI input {self._in_name}: {e}")
                self._in_port = None
                
        # DDTi output (to send SysEx)
        if self._out_name:
            try:
                self._out_port = mido.open_output(self._out_name)
                print(f"Opened MIDI output: {self._out_name}")
            except Exception as e:
                print(f"Error opening MIDI output {self._out_name}: {e}")
                self._out_port = None
        
        # NEW: Dedicated DDTi input (for dumps)
        if self._ddti_in_name:
            # Share if same as main input
            if self._ddti_in_name == self._in_name and self._in_port:
                self._ddti_in_port = self._in_port
                print(f"DDTi SysEx input shares main input: {self._ddti_in_name}")
            else:
                try:
                    self._ddti_in_port = mido.open_input(self._ddti_in_name)
                    print(f"Opened DDTi SysEx input: {self._ddti_in_name}")
                except Exception as e:
                    print(f"Error opening DDTi SysEx input {self._ddti_in_name}: {e}")
                    self._ddti_in_port = None

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
        
        # NEW: Close DDTi input (but not if it's shared with main input)
        if self._ddti_in_port and self._ddti_in_port is not self._in_port:
            try:
                self._ddti_in_port.close()
                print(f"Closed DDTi SysEx input: {self._ddti_in_name}")
            except Exception:
                pass
        self._ddti_in_port = None

    def reopen_ports(self):
        """Close and reopen all ports."""
        self.close_ports()
        self.open_ports()

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
    
    # NEW: DDTi input management
    def set_ddti_in(self, name: str):
        """Set dedicated DDTi SysEx input port and reopen."""
        self._ddti_in_name = name
        self.reopen_ports()

    # ----- Runtime I/O -----
    def iter_input(self):
        """Get pending MIDI input messages from keyboard (no thru handling)."""
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

    # NEW: DDTi SysEx input iterator
    def iter_ddti_sysex(self):
        """Yield pending SysEx messages from dedicated DDTi input."""
        if not self._ddti_in_port:
            return []
        return [m for m in self._ddti_in_port.iter_pending() if m.type == 'sysex']

    def get_in_port_name(self) -> Optional[str]:
        # Currently-open keyboard input (if any)
        try:
            return getattr(self._in_port, "name", None)
        except Exception:
            return None

    def get_out_port_name(self) -> Optional[str]:
        # Currently-open DDTi output (if any)
        try:
            return getattr(self._out_port, "name", None)
        except Exception:
            return None
    
    # NEW: Get DDTi input port name
    def get_ddti_in_port_name(self) -> Optional[str]:
        try:
            return getattr(self._ddti_in_port, "name", None)
        except Exception:
            return None
