# config.py
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any, Dict

from constants import ROOT

DEFAULTS: Dict[str, Any] = {
    # MIDI
    "midi_in_name": None,          # exact ALSA/Mido name to open
    "midi_out_name": None,         # exact ALSA/Mido name to open
    "midi_in_substr": "triggerio", # fallback matching if exact name not found
    "midi_out_substr": "triggerio",
    
    # ALSA Hardware Routing (replaces old midi_thru)
    "alsa_keyboard_thru": True,  # Keyboard → External devices
    "alsa_ddti_thru": True,       # DDTi → External devices (default ON)

    # UI / behavior
    "neokey_brightness": 0.5,
    "led_backlights_on": True,     # This controls the LED state
    "led_backlight_color": [84, 255, 61],  # Default sage green color
    "led_backlight_brightness": 1.0,  # Add this new setting (100%)
    "octave_down_lowest": False,
    "allow_duplicate_notes": False,
    "footswitch_capture_mode": "all",  # Add this new setting: "all" or "single"

    # Spiral animation settings for each capture mode
    "spiral_turns_4_note": 20,    # Default turns for 4-note capture
    "spiral_turns_single": 16,     # Default turns for single-note capture
    "spiral_turns_variable": 33,  # NEW: Default for variable trigger mode

    # Footswitch (so you can flip NO/NC without editing code)
    "footswitch_active_low": True,
}

class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or (ROOT / "config.json")
        self._data: Dict[str, Any] = dict(DEFAULTS)

    def load(self) -> "Config":
        try:
            if self.path.exists():
                on_disk = json.loads(self.path.read_text())
                if isinstance(on_disk, dict):
                    self._data.update(on_disk)
        except Exception:
            # Ignore corrupt JSON; keep defaults
            pass
        return self

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self._data, indent=2, sort_keys=True)
        # atomic write
        dirpath = str(self.path.parent)
        with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(self.path)
