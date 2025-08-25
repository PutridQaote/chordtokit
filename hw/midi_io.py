# hw/midi_io.py
from typing import List, Optional
import mido

def _dedupe(seq): return list(dict.fromkeys(seq))

def _pick_by_name(cands, name):
    if not name: return None
    for n in cands:
        if n == name:
            return n
    return None

def _pick_by_substr(cands, substr):
    want = (substr or "").lower()
    for n in cands:
        if want and want in n.lower():
            return n
    return cands[0] if cands else None

class Midi:
    def __init__(self, cfg: Optional[dict] = None):
        cfg = cfg or {}
        self._thru = bool(cfg.get("midi_thru", False))

        ins  = _dedupe(mido.get_input_names())
        outs = _dedupe(mido.get_output_names())

        exact_in  = _pick_by_name(ins,  cfg.get("midi_in_name"))
        exact_out = _pick_by_name(outs, cfg.get("midi_out_name"))

        self._in_name  = exact_in  or _pick_by_substr(ins,  cfg.get("midi_in_substr",  "triggerio"))
        self._out_name = exact_out or _pick_by_substr(outs, cfg.get("midi_out_substr", "triggerio"))

        self._in_port  = None
        self._out_port = None

    # ---------- Port management ----------
    def open_ports(self):
        if self._in_name and self._in_port is None:
            try: self._in_port = mido.open_input(self._in_name)
            except Exception: self._in_port = None
        if self._out_name and self._out_port is None:
            try: self._out_port = mido.open_output(self._out_name)
            except Exception: self._out_port = None

    def close_ports(self):
        if self._in_port:  
            try: self._in_port.close()
            except Exception: pass
            self._in_port = None
        if self._out_port:
            try: self._out_port.close()
            except Exception: pass
            self._out_port = None

    def reopen_ports(self):
        self.close_ports()
        self.open_ports()

    # ---------- Menu API (names & selection) ----------
    def get_inputs(self) -> List[str]:  return _dedupe(mido.get_input_names())
    def get_outputs(self) -> List[str]: return _dedupe(mido.get_output_names())
    def get_selected_in(self) -> Optional[str]:  return self._in_name
    def get_selected_out(self) -> Optional[str]: return self._out_name

    def set_in(self, name: str):
        self._in_name = name
        self.reopen_ports()

    def set_out(self, name: str):
        self._out_name = name
        self.reopen_ports()

    def get_thru(self) -> bool: return self._thru
    def set_thru(self, val: bool): self._thru = bool(val)

    # ---------- Runtime I/O ----------
    def iter_input(self):
        if self._in_port is None:
            return []
        msgs = list(self._in_port.iter_pending())
        if self._thru and self._out_port is not None:
            for m in msgs:
                try: self._out_port.send(m)
                except Exception: pass
        return msgs

    def send(self, msg):
        if self._out_port is None:
            return
        try:
            self._out_port.send(msg)
        except Exception:
            self.reopen_ports()
            if self._out_port:
                try: self._out_port.send(msg)
                except Exception: pass
