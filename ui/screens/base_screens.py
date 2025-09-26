"""Base screen classes for the UI system."""
from dataclasses import dataclass
from typing import Optional
from PIL import ImageDraw
import time
import math

from ..utils import BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN


@dataclass
class ScreenResult:
    push: Optional["Screen"] = None
    pop: bool = False
    dirty: bool = True


class Screen:
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        pass
    def on_key(self, key: int) -> ScreenResult:
        return ScreenResult()


class BaseCaptureScreen(Screen):
    """Base class for chord capture screens with shared spiral and UI elements."""
    
    def __init__(self, chord_capture, turns=20, config_key=None, config=None):
        self.chord_capture = chord_capture
        self.active = False
        # Spiral animation state - EXACT values from test file
        self.start_time = 0.0
        self.speed = 3.33  # SPIRAL_SPEED
        
        # Turn management
        self.config_key = config_key  # e.g., "spiral_turns_4_note"
        self.config = config
        
        # Load turns from config or use default
        if config_key and config:
            self.turns = config.get(config_key, turns)
        else:
            self.turns = turns
            
        self.completion_time = None  # When capture was completed
        
    def activate(self):
        """Start capture mode - subclasses should override and call super()."""
        self.active = True
        self.start_time = time.monotonic()
        self.completion_time = None
        
    def deactivate(self):
        """Stop capture mode - subclasses should override and call super()."""
        self.active = False
    
    def on_key(self, key: int) -> ScreenResult:
        """Handle navigation and back button."""
        if key == BUTTON_LEFT:  # Back button - abort capture
            self.deactivate()
            return ScreenResult(pop=True)
        elif key == BUTTON_UP:  # Increase spiral turns
            self.turns = min(50, self.turns + 1)  # Cap at 50 turns
            self._save_turns_to_config()
            print(f"Spiral turns increased to {self.turns}")
            return ScreenResult(dirty=True)
        elif key == BUTTON_DOWN:  # Decrease spiral turns
            self.turns = max(1, self.turns - 1)  # Minimum 1 turn
            self._save_turns_to_config()
            print(f"Spiral turns decreased to {self.turns}")
            return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)
    
    def _save_turns_to_config(self):
        """Save current turns setting to config."""
        if self.config_key and self.config:
            self.config.set(self.config_key, self.turns)
            self.config.save()
    
    def _draw_spiral(self, draw, w, h, t):
        """Draw animated spiral - shared between both capture modes."""
        cx, cy = w // 2, h // 2
        radius = min(w, h) * 0.5 - 2
        
        # Archimedean spiral r = a + b*theta, animated by phase t
        turns = self.turns  # Use current turns setting
        theta_max = 2 * math.pi * turns
        a = 0.0
        b = radius / theta_max
        
        # Phase offset to animate
        phase = t * self.speed
        
        # Draw the spiral as connected short segments
        step = 0.03
        prev = None
        for k in range(int(theta_max / step) + 1):
            theta = k * step + phase
            r = a + b * (k * step)
            x = int(cx + r * math.cos(theta))
            y = int(cy + r * math.sin(theta))
            if prev is not None:
                try:
                    draw.line((prev[0], prev[1], x, y), fill=1)
                except:
                    pass  # Skip if out of bounds
            prev = (x, y)
    
    def _draw_listen_text(self, draw, w, h):
        """Draw 'LISTEN' text in center - shared between both capture modes."""
        listen_text = "LISTEN"
        bbox = draw.textbbox((0, 0), listen_text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    
        # Center the text
        text_x = (w - text_w) // 2
        text_y = (h - text_h) // 2
    
        # Draw "listen" in black with bold effect
        offsets = [
            (0, 0),    # original position
            (1, 0),    # right
            (0, 1),    # down
            (1, 1),    # diagonal
        ]
        
        for dx, dy in offsets:
            draw.text((text_x + dx, text_y + dy), listen_text, fill=0)
    
    def _render_base_frame(self, draw, w, h):
        """Render the basic frame and spiral - shared setup."""
        # Clear screen with border
        draw.rectangle((0, 0, w-1, h-1), outline=0, fill=0)
        draw.rectangle((0, 0, w-1, h-1), outline=1, fill=0)
    
        if not self.active:
            draw.text((4, h//2), "Capture inactive", fill=1)
            return False  # Don't continue rendering
    
        # Calculate time elapsed since start and draw spiral
        t = time.monotonic() - self.start_time
        self._draw_spiral(draw, w, h, t)
        return True  # Continue with specific rendering
    
    def update(self) -> ScreenResult:
        """Base update - subclasses should override."""
        if not self.active:
            return ScreenResult(dirty=False)
        
        # Check if we should exit after 1 second delay
        if self.completion_time and (time.monotonic() - self.completion_time) >= 1.0:
            self.deactivate()
            return ScreenResult(pop=True)
            
        return ScreenResult(dirty=True)