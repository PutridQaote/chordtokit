"""Minimal MIDI adapter for the Menu. Later we can expand to open ports and enable thru.
For now it exposes the query/setter surface that ui.menu.Menu expects.
"""
from typing import List, Optional
import mido

class Midi:
    def __init__(self, cfg: Optional[dict] = None):
        self._thru = bool(cfg.get("thru", False)) if cfg else False
        ins = self.get_inputs()
        outs = self.get_outputs()
        self._in_name = (cfg.get("midi_in") if cfg else None) or (ins[0] if ins else None)
        self._out_name = (cfg.get("midi_out") if cfg else None) or (outs[0] if outs else None)
        # We will open ports later; for the menu demo we only need names.

    # --- Menu API ---
    def get_inputs(self) -> List[str]:
        return mido.get_input_names()

    def get_outputs(self) -> List[str]:
        return mido.get_output_names()

    def get_selected_in(self) -> Optional[str]:
        return self._in_name

    def get_selected_out(self) -> Optional[str]:
        return self._out_name

    def set_in(self, name: str):
        self._in_name = name

    def set_out(self, name: str):
        self._out_name = name

    def get_thru(self) -> bool:
        return self._thru

    def set_thru(self, val: bool):
        self._thru = bool(val)

    # Stubs the app loop might call later
    def iter_input(self):
        return []

    def send(self, msg):
        pass