"""Minimal MIDI adapter with real I/O, dedupe, and port reopen on selection."""
from typing import List, Optional
import mido

def _dedupe(seq):
    return list(dict.fromkeys(seq))  # preserves order

def _pick(candidates, want_substr):
    want = (want_substr or "").lower()
    for n in candidates:
        if want and want in n.lower():
            return n
    return candidates[0] if candidates else None

class Midi:
    def __init__(self, cfg: Optional[dict] = None):
        self._thru = bool((cfg or {}).get("thru", False))
        ins  = _dedupe(mido.get_input_names())
        outs = _dedupe(mido.get_output_names())
        want_in  = (cfg or {}).get("midi_in_substr",  "triggerio")
        want_out = (cfg or {}).get("midi_out_substr", "triggerio")
        self._in_name  = _pick(ins,  want_in)
        self._out_name = _pick(outs, want_out)
        self._in_port  = None
        self._out_port = None

    # ---------- Port management ----------
    def open_ports(self):
        """Open selected ports if not already open."""
        if self._in_name and self._in_port is None:
            try:
                self._in_port = mido.open_input(self._in_name)
            except Exception:
                self._in_port = None
        if self._out_name and self._out_port is None:
            try:
                self._out_port = mido.open_output(self._out_name)
            except Exception:
                self._out_port = None

    def close_ports(self):
        if self._in_port is not None:
            try: self._in_port.close()
            except Exception: pass
            self._in_port = None
        if self._out_port is not None:
            try: self._out_port.close()
            except Exception: pass
            self._out_port = None

    def reopen_ports(self):
        self.close_ports()
        self.open_ports()

    # ---------- Menu API (names & selection) ----------
    def get_inputs(self) -> List[str]:
        return _dedupe(mido.get_input_names())

    def get_outputs(self) -> List[str]:
        return _dedupe(mido.get_output_names())

    def get_selected_in(self) -> Optional[str]:
        return self._in_name

    def get_selected_out(self) -> Optional[str]:
        return self._out_name

    def set_in(self, name: str):
        self._in_name = name
        self.reopen_ports()

    def set_out(self, name: str):
        self._out_name = name
        self.reopen_ports()

    def get_thru(self) -> bool:
        return self._thru

    def set_thru(self, val: bool):
        self._thru = bool(val)

    # ---------- Runtime I/O ----------
    def iter_input(self):
        """Return pending input messages and optionally THRU them."""
        if self._in_port is None:
            return []
        msgs = list(self._in_port.iter_pending())
        if self._thru and self._out_port is not None:
            for m in msgs:
                try: self._out_port.send(m)
                except Exception: pass
        return msgs

    def send(self, msg):
        """Send a message to the selected output (if open)."""
        if self._out_port is None:
            return
        try:
            self._out_port.send(msg)
        except Exception:
            # If device disappeared, try reopening once
            self.reopen_ports()
            if self._out_port is not None:
                try: self._out_port.send(msg)
                except Exception: pass
