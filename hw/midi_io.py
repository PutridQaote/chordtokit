"""
MIDI input/output interface for ChordToKit.
Handles port selection, thru routing, and message filtering.
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
        self._thru = bool(cfg.get("midi_thru", False))
        self._thru_mode = cfg.get("midi_thru_mode", "all_except_main_out")
        
        # Port filtering configuration
        self._thru_include = cfg.get("midi_thru_include", [])
        self._thru_exclude_substr = cfg.get("midi_thru_exclude_substr", [
            "Midi Through", 
            "RtMidi",
            "through"
        ])

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
        self._thru_ports = []

    def open_ports(self):
        """Open MIDI input/output ports based on current settings."""
        self.close_ports()
        
        if self._in_name:
            try:
                self._in_port = mido.open_input(self._in_name)
                # print(f"Opened MIDI input: {self._in_name}")
            except Exception as e:
                print(f"Error opening MIDI input {self._in_name}: {e}")
                self._in_port = None
                
        if self._out_name:
            try:
                self._out_port = mido.open_output(self._out_name)
                # print(f"Opened MIDI output: {self._out_name}")
            except Exception as e:
                print(f"Error opening MIDI output {self._out_name}: {e}")
                self._out_port = None
                
        # Open thru ports (no threading needed)
        self.open_thru_ports()

    def open_thru_ports(self):
        """Open additional ports for MIDI thru routing based on thru mode."""
        self.close_thru_ports()
        
        if not self._thru:
            return
            
        # Get all available output ports, filtering out problematic ports
        all_outs = [name for name in _dedupe(mido.get_output_names()) 
                    if not _is_virtual_through(name)]
        
        ports_to_open = []
        
        if self._thru_include:
            ports_to_open = [name for name in all_outs if name in self._thru_include]
        else:
            for name in all_outs:
                if name == self._out_name or name == self._in_name:
                    continue
                    
                excluded = False
                for substr in self._thru_exclude_substr:
                    if substr.lower() in name.lower():
                        excluded = True
                        print(f"Excluding MIDI port from thru: {name} (matches '{substr}')")
                        break
                
                if not excluded:
                    ports_to_open.append(name)
        
        # Open the filtered port list
        for name in ports_to_open:
            try:
                port = mido.open_output(name)
                self._thru_ports.append((name, port))
                print(f"Opened MIDI thru output: {name}")
            except Exception as e:
                print(f"Error opening MIDI thru output {name}: {e}")

    def close_thru_ports(self):
        """Close all thru ports."""
        for name, port in self._thru_ports:
            try:
                port.close()
                print(f"Closed MIDI thru output: {name}")
            except Exception as e:
                print(f"Error closing MIDI thru output {name}: {e}")
        self._thru_ports = []

    def close_ports(self):
        """Close all MIDI ports."""
        self.close_thru_ports()  # This will stop the thru thread
        
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

    # ----- Menu API -----
    def get_inputs(self) -> List[str]:
        """Get filtered list of available MIDI inputs."""
        return [name for name in _dedupe(mido.get_input_names()) 
                if not _is_virtual_through(name)]
        
    def get_outputs(self) -> List[str]:
        """Get filtered list of available MIDI outputs."""
        return [name for name in _dedupe(mido.get_output_names()) 
                if not _is_virtual_through(name)]

    def get_selected_in(self) -> Optional[str]: return self._in_name
    def get_selected_out(self) -> Optional[str]: return self._out_name
    
    def set_in(self, name: Optional[str]):
        """Set and open input port by name."""
        self._in_name = name
        self.reopen_ports()
        
    def set_out(self, name: Optional[str]):
        """Set and open output port by name."""
        self._out_name = name
        self.reopen_ports()

    def get_thru(self) -> bool: return self._thru
    def set_thru(self, val: bool): 
        """Enable/disable MIDI thru routing."""
        self._thru = bool(val)
        if self._thru:
            self.open_thru_ports()
        else:
            self.close_thru_ports()

    def get_thru_mode(self) -> str: return self._thru_mode
    def set_thru_mode(self, mode: str):
        """Set MIDI thru routing mode and update ports.
        
        Args:
            mode: One of "all_except_main_out" or "all_devices"
        """
        if mode not in ["all_except_main_out", "all_devices"]:
            raise ValueError(f"Invalid thru mode: {mode}")
        self._thru_mode = mode
        self.open_thru_ports()

    # ----- Runtime I/O -----
    def iter_input(self):
        """Get pending MIDI input messages and handle thru routing inline."""
        if self._in_port is None:
            return []
        
        msgs = list(self._in_port.iter_pending())
        
        # Handle MIDI thru immediately - no threading conflicts
        if self._thru and msgs and self._thru_ports:
            for msg in msgs:
                for _, port in self._thru_ports:
                    try:
                        port.send(msg)
                    except Exception as e:
                        print(f"Error in MIDI thru: {e}")
        
        return msgs

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
