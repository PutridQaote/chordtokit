"""Menu system and core ScreenResult class."""
from dataclasses import dataclass
from typing import List, Optional
import time

from .utils import BUTTON_LEFT
from .screens.base_screens import Screen, ScreenResult
from .screens.settings_screens import MidiSettingsScreen, UtilitiesScreen
from .screens.chord_screens import ChordCaptureMenuScreen
from .screens.system_screens import HomeScreen, ShutdownConfirmScreen


class Menu:
    def __init__(self, midi_adapter=None, config=None, chord_capture=None, neokey=None, alsa_router=None):
        self._stack: List[Screen] = [HomeScreen()]
        self.dirty = True
        self.midi = midi_adapter
        self.cfg = config
        self.chord_capture = chord_capture
        self.neokey = neokey
        self.alsa_router = alsa_router
        
        # Long press detection for shutdown
        self._back_press_start = None
        self._back_long_press_threshold = 2.2  # 2.2 seconds of hold before it shuts down
        self._back_long_press_triggered = False
        
        # Set chord_capture reference for the home screen
        if chord_capture and isinstance(self._stack[0], HomeScreen):
            self._stack[0]._chord_capture = chord_capture

    # Map NeoKey logical indices → UI actions
    def _logical_to_action(self, idx: int) -> Optional[int]:
        from .utils import BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT
        mapping = {
            0: BUTTON_LEFT,   # leftmost
            1: BUTTON_UP,
            2: BUTTON_DOWN,
            3: BUTTON_SELECT, # rightmost
        }
        return mapping.get(idx)

    def _top(self) -> Screen:
        return self._stack[-1]

    def push(self, screen: Screen):
        if isinstance(screen, MidiSettingsScreen):
            screen.attach(self.midi, self.cfg, self.alsa_router)
        elif isinstance(screen, UtilitiesScreen):
            screen.attach(self.chord_capture, self.cfg, self.neokey)
        elif isinstance(screen, ChordCaptureMenuScreen):
            screen.attach(self.chord_capture, self.cfg, self.alsa_router)
        # REMOVED: DDTiSyncScreen attachment - no longer used in menus
        elif isinstance(screen, HomeScreen) and self.chord_capture:
            screen._chord_capture = self.chord_capture
        
        # NEW: Call activate if the screen has it
        if hasattr(screen, 'activate'):
            screen.activate()

        self._stack.append(screen)
        self.dirty = True

    def pop(self):
        if len(self._stack) > 1:
            # NEW: Call deactivate if the screen has it
            top = self._stack[-1]
            if hasattr(top, 'deactivate'):
                top.deactivate()
            self._stack.pop()
            self.dirty = True

    def handle_events(self, events):
        for event_type, key_idx in events:
            if event_type == "press":
                if key_idx == BUTTON_LEFT:
                    self._back_press_start = time.monotonic()
                    self._back_long_press_triggered = False
                
                result = self._top().on_key(key_idx)
                if result.push:
                    self.push(result.push)
                elif result.pop:
                    self.pop()
                if result.dirty:
                    self.dirty = True
            elif event_type == "release":
                if key_idx == BUTTON_LEFT:
                    self._back_press_start = None
                    self._back_long_press_triggered = False

    def update(self) -> bool:
        """Update active screen and check for long press. Return True if screen changed."""
        current_time = time.monotonic()
        
        # Check for back button long press
        if (self._back_press_start and 
            not self._back_long_press_triggered and
            (current_time - self._back_press_start) >= self._back_long_press_threshold):
            
            # Trigger shutdown confirmation - pass neokey reference
            self._back_long_press_triggered = True
            self.push(ShutdownConfirmScreen(neokey=self.neokey))
            return True
        
        top = self._top()
        
        # NEW: update any screen that implements update()
        if hasattr(top, "update"):
            try:
                result = top.update()
            except Exception as e:
                print(f"Screen update error ({top.__class__.__name__}): {e}")
                return False
            else:
                if isinstance(result, ScreenResult):
                    if result.pop:
                        self.pop()
                        return True
                    if result.dirty:
                        self.dirty = True
        
        return False

    def render_into(self, draw, w, h):
        self._top().render(draw, w, h)