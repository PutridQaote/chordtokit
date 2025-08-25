"""NeoKey 1x4 (Seesaw) wrapper: key reads (debounced) + NeoPixel control.
"""
import time
from typing import Dict, List, Tuple

import board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

from constants import (
    NEOKEY_ADDR,
    NEOKEY_DATA_PIN,
    NEOKEY_KEY_PINS,
    DEBOUNCE_MS,
)

class NeoKey:
    """High-level access to the 1×4 keypad + LEDs.

    - read_pressed(): stable pressed booleans in left→right order (len=4)
    - read_events():  list of (event, index) edges where index is 0..3 left→right
    - set_pixel(i, rgb), fill(rgb), show(), clear()
    """

    def __init__(self, addr: int = NEOKEY_ADDR, data_pin: int = NEOKEY_DATA_PIN, pixels: int = 4, brightness: float = 0.5):
        self._ss = Seesaw(board.I2C(), addr=addr)
        # Logical order (left→right) of the keys expressed as Seesaw pin numbers
        self._logical_order: List[int] = list(NEOKEY_KEY_PINS)
        # Map physical seesaw pin → logical index left→right
        self._pin_to_logical: Dict[int, int] = {pin: i for i, pin in enumerate(self._logical_order)}
        # For configuration & scanning we just iterate the unique set of pins
        self._phys_pins: List[int] = list(self._pin_to_logical.keys())

        # Configure inputs with pullups
        for p in self._phys_pins:
            self._ss.pin_mode(p, self._ss.INPUT_PULLUP)

        # NeoPixels on the seesaw
        self._px = SSNeoPixel(self._ss, data_pin, pixels, auto_write=False)
        self._px.brightness = brightness

        # Debounce state
        self._raw = {p: True for p in self._phys_pins}            # True == unpressed (pull-up)
        self._stable = {p: True for p in self._phys_pins}
        self._last_change = {p: 0.0 for p in self._phys_pins}
        self._debounce_s = DEBOUNCE_MS / 1000.0

    # -------------------- LEDs --------------------
    def set_pixel(self, idx: int, rgb: Tuple[int, int, int]):
        self._px[idx] = rgb

    def fill(self, rgb: Tuple[int, int, int]):
        self._px.fill(rgb)

    def show(self):
        self._px.show()

    def clear(self):
        self._px.fill((0, 0, 0))
        self._px.show()

    # -------------------- Keys --------------------
    def _read_phys(self, p: int) -> bool:
        """Return True if unpressed (pull-up HIGH), False if pressed (LOW)."""
        return bool(self._ss.digital_read(p))

    def read_pressed(self) -> List[bool]:
        """Stable pressed booleans in left→right order (index 0 == leftmost)."""
        self._update_debounce()
        # Convert stable phys to logical order and invert to pressed=True
        return [not self._stable[pin] for pin in self._logical_order]

    def read_events(self) -> List[Tuple[str, int]]:
        """Edge events since last call. ('press'|'release', logical_index)."""
        events: List[Tuple[str, int]] = []
        if self._update_debounce():
            for pin in self._phys_pins:
                # Compare stable vs raw already applied in _update_debounce
                pass
        # Build from transitions captured during debounce
        for pin, pending in getattr(self, "_pending_events", []).copy():
            events.append(pending)
        self._pending_events = []
        return events

    def _update_debounce(self) -> bool:
        now = time.monotonic()
        changed = False
        pending = []
        for p in self._phys_pins:
            cur = self._read_phys(p)
            if cur != self._raw[p]:
                self._raw[p] = cur
                self._last_change[p] = now
            # If stable long enough, register edge
            if self._stable[p] != self._raw[p] and (now - self._last_change[p]) >= self._debounce_s:
                self._stable[p] = self._raw[p]
                changed = True
                logical_idx = self._pin_to_logical[p]
                event = ("release" if self._stable[p] else "press", logical_idx)
                pending.append((p, event))
        self._pending_events = [(p, e) for p, e in pending]
        return changed