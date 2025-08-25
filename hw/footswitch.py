"""Footswitch wrapper with debounce and edge detection.
Tries to use gpiozero; falls back to RPi.GPIO if needed.
"""
from typing import Optional
import time

from constants import FOOTSWITCH_GPIO, FOOTSWITCH_ACTIVE_LOW, FOOTSWITCH_DEBOUNCE_MS

class Footswitch:
    def __init__(self, pin: int = FOOTSWITCH_GPIO, active_low: bool = FOOTSWITCH_ACTIVE_LOW, debounce_ms: int = FOOTSWITCH_DEBOUNCE_MS):
        self.pin = pin
        self.active_low = bool(active_low)
        self.debounce_s = debounce_ms / 1000.0
        self._last_change = 0.0
        self._last = False
        self._impl = None
        self._using_gpiozero = False
        # Try gpiozero first
        try:
            from gpiozero import Button  # type: ignore
            self._impl = Button(pin, pull_up=True, bounce_time=self.debounce_s)
            self._using_gpiozero = True
        except Exception:
            # Fallback to RPi.GPIO
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self._impl = GPIO
            self._using_gpiozero = False

    def _read_raw(self) -> bool:
        """Return True if electrically at 1 (HIGH), False if 0 (LOW)."""
        if self._using_gpiozero:
            # gpiozero Button reports "pressed" when the input is active; with pull_up=True
            # that means grounded -> active -> pressed True. We want raw level here.
            # Button.is_pressed == (LOW if pull-up). So map to raw HIGH/LOW via property.
            btn = self._impl
            return not btn.is_pressed
        else:
            GPIO = self._impl
            return bool(GPIO.input(self.pin))

    def is_pressed(self) -> bool:
        # Convert raw level to logical pressed depending on active_low
        level_high = self._read_raw()
        pressed = (not level_high) if self.active_low else level_high
        return pressed

    def pressed_edge(self) -> bool:
        """Return True exactly once on a press (LOW→pressed for active_low).
        Debounced via GPIO lib (if gpiozero) and here via time window.
        """
        now = time.monotonic()
        cur = self.is_pressed()
        if cur != self._last and (now - self._last_change) >= self.debounce_s:
            self._last_change = now
            self._last = cur
            return cur  # only True on press edges
        self._last = cur
        return False