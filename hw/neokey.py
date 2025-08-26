"""NeoKey 1x4 (Seesaw) wrapper: debounced key events + NeoPixel control."""
from __future__ import annotations
import time
from typing import Dict, List, Tuple

import board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

from constants import (
    NEOKEY_ADDR,
    NEOKEY_DATA_PIN,
    NEOKEY_KEY_PINS,
    NEOKEY_BRIGHT,  # Add this import
    DEBOUNCE_MS,
)

class NeoKey:
    """
    - read_events() -> [("press"|"release", logical_index), ...]
    - read_pressed() -> [bool, bool, bool, bool]  (left→right)
    - set_pixel(i, (r,g,b)), fill(rgb), show(), clear()
    - set_backlight_enabled(bool), set_backlight_color(rgb)
    """
    def __init__(self, addr: int = NEOKEY_ADDR, data_pin: int = NEOKEY_DATA_PIN,
                 pixels: int = 4, brightness: float = NEOKEY_BRIGHT,  # Use the constant here
                 backlight_enabled: bool = True, backlight_color: tuple = (84, 255, 61)):
        self._ss = Seesaw(board.I2C(), addr=addr)

        # Logical order left→right is exactly NEOKEY_KEY_PINS
        self._logical: List[int] = list(NEOKEY_KEY_PINS)
        self._pin_to_idx: Dict[int, int] = {pin: i for i, pin in enumerate(self._logical)}

        # Configure key inputs with pull-ups (idle HIGH, pressed LOW)
        for p in self._logical:
            self._ss.pin_mode(p, self._ss.INPUT_PULLUP)

        # NeoPixels
        self._px = SSNeoPixel(self._ss, data_pin, pixels, auto_write=False)
        self._px.brightness = float(brightness)

        # LED backlight settings
        self._backlight_enabled = backlight_enabled
        self._backlight_color = tuple(backlight_color)
        
        # Set initial LED state
        self._update_backlights()

        # Debounce state
        self._debounce_s = DEBOUNCE_MS / 1000.0  # 2ms instead of 4ms
        now = time.monotonic()
        self._raw: Dict[int, bool] = {p: True for p in self._logical}    # True = unpressed (HIGH)
        self._stable: Dict[int, bool] = dict(self._raw)
        self._last_t: Dict[int, float] = {p: now for p in self._logical}

    # ------------- LEDs -------------
    def set_pixel(self, idx: int, rgb: Tuple[int, int, int]):
        self._px[idx] = rgb

    def fill(self, rgb: Tuple[int, int, int]):
        self._px.fill(rgb)

    def show(self):
        self._px.show()

    def clear(self):
        self._px.fill((0, 0, 0))
        self._px.show()

    def set_backlight_enabled(self, enabled: bool):
        """Enable or disable the default backlight."""
        self._backlight_enabled = enabled
        self._update_backlights()

    def set_backlight_color(self, rgb: Tuple[int, int, int]):
        """Set the backlight color."""
        self._backlight_color = tuple(rgb)
        if self._backlight_enabled:
            self._update_backlights()

    def get_backlight_enabled(self) -> bool:
        """Get current backlight enabled state."""
        return self._backlight_enabled

    def get_backlight_color(self) -> Tuple[int, int, int]:
        """Get current backlight color."""
        return self._backlight_color

    def _update_backlights(self):
        """Update the backlight LEDs based on current settings."""
        if self._backlight_enabled:
            self.fill(self._backlight_color)
        else:
            self.fill((0, 0, 0))
        self.show()

    # ------------- Keys -------------
    def _read_pin_level(self, p: int) -> bool:
        """Return True if HIGH (unpressed), False if LOW (pressed)."""
        try:
            return bool(self._ss.digital_read(p))
        except Exception:
            # If I2C hiccups, don't invent edges—stick with last raw
            return self._raw[p]

    def read_pressed(self) -> List[bool]:
        """Stable pressed booleans (left→right)."""
        self._scan_debounce()
        # Invert because stable True == unpressed
        return [not self._stable[p] for p in self._logical]

    def read_events(self) -> List[Tuple[str, int]]:
        """Return edge events since last call."""
        return self._scan_debounce()

    def _scan_debounce(self) -> List[Tuple[str, int]]:
        now = time.monotonic()
        events: List[Tuple[str, int]] = []

        for p in self._logical:
            cur = self._read_pin_level(p)
            if cur != self._raw[p]:
                # raw changed, start/refresh debounce timer
                self._raw[p] = cur
                self._last_t[p] = now
                # Uncomment for debugging:
                # print(f"Pin {p} raw change: {cur} at {now:.6f}")

            # Has the raw state stayed different long enough?
            if (self._stable[p] != self._raw[p]) and ((now - self._last_t[p]) >= self._debounce_s):
                self._stable[p] = self._raw[p]
                idx = self._pin_to_idx[p]
                event_type = "release" if self._stable[p] else "press"
                events.append((event_type, idx))
                # Better precision debugging:
                # print(f"Pin {p} -> {event_type} (idx {idx}) after {(now - self._last_t[p])*1000:.3f}ms")

        return events
