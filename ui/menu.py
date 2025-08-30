"""Minimal menu state machine (Home + MIDI Settings).

This module does not touch hardware directly; it expects small adapters:
- nk: object with read_events() returning [('press'|'release', idx), ...]
- oled: object with width, height, PIL Image + Draw helpers (e.g., .begin_frame() -> (img, draw), .show(img))
- midi: object with get_inputs(), get_outputs(), get_selected_in(), get_selected_out(), set_in(name), set_out(name), get_thru(), set_thru(bool)
- cfg: dict-like for persisted settings (octave_down_lowest, backlight, etc.)

You can swap in a real OLED wrapper later; for now this isolates UI logic.
"""
from dataclasses import dataclass
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
import math
import time
import subprocess
import os

BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT = 0, 1, 2, 3  # logical left→right indices

def note_to_name(midi_note):
    """Convert MIDI note number to note name like 'F#4'."""
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_note // 12) # removed -1 to match the ddti note numbers
    note = note_names[midi_note % 12]
    return f"{note}{octave}"

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

class ChordCaptureScreen(Screen):
    def __init__(self, chord_capture):
        self.chord_capture = chord_capture
        self.active = False
        # Spiral animation state - EXACT values from test file
        self.start_time = 0.0
        self.speed = 3.33  # SPIRAL_SPEED from test file
        self.turns = 20    # SPIRAL_TURNS from test file
        # Note display positions (corners)
        self.note_positions = [
            (4, 4),      # Top-left
            (4, 52),     # Bottom-left  
            (100, 52),   # Bottom-right
            (100, 4),    # Top-right
        ]
        self.completion_time = None  # When 4th note was captured
        self.captured_notes = []     # Store notes during completion delay
        
    def activate(self):
        """Start chord capture mode."""
        self.active = True
        self.start_time = time.monotonic()
        self.completion_time = None
        self.captured_notes = []
        self.chord_capture.activate()  # This will clear bucket and flush MIDI
        
    def deactivate(self):
        """Stop chord capture mode."""
        self.active = False
        self.captured_notes = []
        self.chord_capture.deactivate()
    
    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:  # Back button - abort capture
            self.deactivate()
            return ScreenResult(pop=True)
        return ScreenResult(dirty=False)
    
    def update(self) -> ScreenResult:
        """Check for captured chord. Call this from main loop."""
        if not self.active:
            return ScreenResult(dirty=False)
            
        captured_chord = self.chord_capture.process_midi_input()
        if captured_chord:
            # Chord was captured and sent - store notes and start 1 second countdown
            self.captured_notes = captured_chord[:]  # Store a copy
            self.completion_time = time.monotonic()
        
        # Call base class update for common completion logic
        return super().update()
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        # Use base class frame rendering
        if not self._render_base_frame(draw, w, h):
            return  # Inactive, base class handled it
    
        # Show captured notes in corners - specific to 4-note mode
        if self.completion_time:
            # During completion delay, show the captured notes
            notes = self.captured_notes
        else:
            # During capture, show current bucket status
            status = self.chord_capture.get_bucket_status()
            notes = status['notes']
    
        # Display up to 4 notes in the corner positions
        for i, note in enumerate(notes[:4]):
            if i < len(self.note_positions):
                x, y = self.note_positions[i]
                note_text = f"{note_to_name(note)}"
                draw.text((x, y), note_text, fill=1)
    
        # Show "LISTEN" if we haven't completed capture
        if not self.completion_time:
            self._draw_listen_text(draw, w, h)

class UtilitiesScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Allow Duplicate Notes", self._toggle_duplicates),
            ("LED Brightness", self._cycle_led_brightness),
            ("Back", None),
        ]
        self.sel = 0
        self._chord_capture = None
        self._cfg = None
        self._neokey = None

    def attach(self, chord_capture, config, neokey=None):
        self._chord_capture = chord_capture
        self._cfg = config
        self._neokey = neokey

    def _toggle_duplicates(self):
        if self._chord_capture and self._cfg:
            current = self._cfg.get("allow_duplicate_notes", False)
            new_val = not current
            self._cfg.set("allow_duplicate_notes", new_val)
            self._cfg.save()
            self._chord_capture.set_allow_duplicates(new_val)

    def _cycle_led_brightness(self):
        """Cycle through LED brightness levels: 100%, 75%, 50%, 25%, Off."""
        if not self._neokey or not self._cfg:
            return
            
        # Define brightness levels: Off, 25%, 50%, 75%, 100%
        brightness_levels = [0.0, 0.25, 0.5, 0.75, 1.0]
        brightness_labels = ["Off", "25%", "50%", "75%", "100%"]
        
        # Get current brightness
        current_brightness = self._cfg.get("led_backlight_brightness", 1.0)
        
        # Find current index (with tolerance for floating point comparison)
        current_index = 0
        for i, level in enumerate(brightness_levels):
            if abs(current_brightness - level) < 0.01:
                current_index = i
                break
        
        # Move to next level (cycle back to 0 after last)
        next_index = (current_index + 1) % len(brightness_levels)
        new_brightness = brightness_levels[next_index]
        
        # Update config
        self._cfg.set("led_backlight_brightness", new_brightness)
        self._cfg.set("led_backlights_on", new_brightness > 0.0)  # Auto-disable if brightness is 0
        self._cfg.save()
        
        # Update hardware
        self._neokey.set_backlight_brightness(new_brightness)
        self._neokey.set_backlight_enabled(new_brightness > 0.0)

    def _get_led_brightness_label(self) -> str:
        """Get the current LED brightness as a label."""
        if not self._cfg:
            return "100%"
            
        brightness = self._cfg.get("led_backlight_brightness", 1.0)
        
        # Map brightness to labels
        if brightness <= 0.0:
            return "Off"
        elif brightness <= 0.25:
            return "25%"
        elif brightness <= 0.5:
            return "50%"
        elif brightness <= 0.75:
            return "75%"
        else:
            return "100%"

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_UP:
            self.sel = (self.sel - 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN:
            self.sel = (self.sel + 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_SELECT:
            label, action = self.rows[self.sel]
            if label == "Back":
                return ScreenResult(pop=True)
            if action:
                action()
                return ScreenResult(dirty=True)
        if key == BUTTON_LEFT:
            return ScreenResult(pop=True)
        return ScreenResult(dirty=False)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4, 2), "Utilities", fill=1)
        
        allow_dupes = self._cfg.get("allow_duplicate_notes", False) if self._cfg else False
        led_brightness = self._get_led_brightness_label()
        
        body = [
            f"Duplicates: {'On' if allow_dupes else 'Off'}",
            f"LEDs: {led_brightness}",
            "Back",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

class HomeScreen(Screen):
    def __init__(self):
        self.items = [
            "Chord Capture",  # Changed from "Initiate Chord Capture"
            "MIDI Settings",
            "Utilities",
        ]
        self.sel = 0
        self._chord_capture = None  # Will be set by Menu

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_UP:
            self.sel = (self.sel - 1) % len(self.items)
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN:
            self.sel = (self.sel + 1) % len(self.items)
            return ScreenResult(dirty=True)
        if key == BUTTON_SELECT:
            label = self.items[self.sel]
            if label == "MIDI Settings":
                return ScreenResult(push=MidiSettingsScreen(), dirty=True)
            elif label == "Chord Capture":
                return ScreenResult(push=ChordCaptureMenuScreen(), dirty=True)
            elif label == "Utilities":
                return ScreenResult(push=UtilitiesScreen(), dirty=True)
            return ScreenResult(dirty=False)
        return ScreenResult(dirty=False)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        title = "ChordToKit"
        draw.text((4, 2), title, fill=1)
        y = 14
        for i, item in enumerate(self.items):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + item, fill=1)
            y += 12

class MidiSettingsScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Chord In", self._cycle_in),
            ("Chord Out", self._cycle_out),
            ("Keyboard Thru", self._toggle_keyboard_thru),
            ("DDTi Thru", self._toggle_ddti_thru),
            ("Back", None),
        ]
        self.sel = 0

    def attach(self, midi_adapter, config, alsa_router=None):
        self._midi = midi_adapter
        self._cfg = config
        self._router = alsa_router

    def _cycle_in(self):
        """Cycle through available MIDI input ports."""
        if not hasattr(self, "_midi") or not self._midi:
            return
        inputs = self._midi.get_inputs()
        if not inputs:
            return
        current = self._midi.get_selected_in()
        try:
            idx = inputs.index(current) if current in inputs else -1
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(inputs)
        new_input = inputs[next_idx]
        self._midi.set_in(new_input)
        # persist
        self._cfg.set("midi_in_name", new_input)
        self._cfg.save()

    def _cycle_out(self):
        """Cycle through available MIDI output ports."""
        if not hasattr(self, "_midi") or not self._midi:
            return
        outputs = self._midi.get_outputs()
        if not outputs:
            return
        current = self._midi.get_selected_out()
        try:
            idx = outputs.index(current) if current in outputs else -1
        except ValueError:
            idx = -1
        next_idx = (idx + 1) % len(outputs)
        new_output = outputs[next_idx]
        self._midi.set_out(new_output)
        # persist
        self._cfg.set("midi_out_name", new_output)
        self._cfg.save()

    def _toggle_keyboard_thru(self):
        """Toggle keyboard ALSA thru routing."""
        if not self._router or not self._cfg:
            return
        val = not self._router.get_keyboard_thru()
        self._router.set_keyboard_thru(val)
        self._cfg.set("alsa_keyboard_thru", val)
        self._cfg.save()

    def _toggle_ddti_thru(self):
        """Toggle DDTi ALSA thru routing."""
        if not self._router or not self._cfg:
            return
        val = not self._router.get_ddti_thru()
        self._router.set_ddti_thru(val)
        self._cfg.set("alsa_ddti_thru", val)
        self._cfg.save()

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_UP:
            self.sel = (self.sel - 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN:
            self.sel = (self.sel + 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_SELECT:
            _, action = self.rows[self.sel]
            if action is None:  # "Back"
                return ScreenResult(pop=True)
            else:
                action()  # call the function
                return ScreenResult(dirty=True)
        if key == BUTTON_LEFT:  # Back
            return ScreenResult(pop=True)
        return ScreenResult(dirty=False)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4, 2), "MIDI Settings", fill=1)
        midi = getattr(self, "_midi", None)
        router = getattr(self, "_router", None)
        
        cur_in = midi.get_selected_in() if midi else "-"
        cur_out = midi.get_selected_out() if midi else "-"
        kb_thru = router.get_keyboard_thru() if router else False
        ddti_thru = router.get_ddti_thru() if router else True
        
        body = [
            f"Chord In:  {cur_in if cur_in else '-'}",
            f"Chord Out: {cur_out if cur_out else '-'}",
            f"KB Thru:   {'On' if kb_thru else 'Off'}",
            f"DDTi Thru: {'On' if ddti_thru else 'Off'}",
            "Back",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

class ShutdownConfirmScreen(Screen):
    def __init__(self, neokey=None):
        self._neokey = neokey  # Store neokey reference
        
    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_SELECT:  # Enter key - confirm shutdown
            self._shutdown()
            return ScreenResult(dirty=False)  # App will exit
        if key == BUTTON_LEFT:  # Back button - cancel
            return ScreenResult(pop=True)
        return ScreenResult(dirty=False)
    
    def _shutdown(self):
        """Perform system shutdown."""
        try:
            print("Shutting down system...")
            
            # Turn off NeoKey LEDs first
            if self._neokey:
                self._neokey.clear()
                print("NeoKey LEDs turned off")
            
            # Clear screen and show "safe to unplug" message
            from hw.oled import Oled  # Import here to avoid circular imports
            oled = Oled()
            img, draw = oled.begin_frame()
            
            # Clear screen completely
            draw.rectangle((0, 0, oled.width-1, oled.height-1), outline=0, fill=0)
            
            # Center "safe to unplug" message
            message = "safe to unplug"
            bbox = draw.textbbox((0, 0), message)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = (oled.width - text_w) // 2
            y = (oled.height - text_h) // 2
            draw.text((x, y), message, fill=1)
            
            oled.show(img)
            
            # Use subprocess to run shutdown command
            subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=True)
        except Exception as e:
            print(f"Shutdown failed: {e}")
            # Could add error handling here if needed
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0, 0, w-1, h-1), outline=1, fill=0)
        
        # Simple shutdown question - centered
        question = "Shutdown?"
        bbox = draw.textbbox((0, 0), question)
        text_w = bbox[2] - bbox[0]
        draw.text(((w - text_w) // 2, h // 2 - 6), question, fill=1)

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
            screen.attach(self.chord_capture, self.cfg)
        elif isinstance(screen, HomeScreen) and self.chord_capture:
            screen._chord_capture = self.chord_capture
        self._stack.append(screen)
        self.dirty = True

    def pop(self):
        if len(self._stack) > 1:
            self._stack.pop()
            self.dirty = True

    def handle_events(self, key_events: List[tuple]):
        """Consume NeoKey events [('press'|'release', idx), ...]."""
        acted = False
        current_time = time.monotonic()
        
        for ev, idx in key_events:
            action = self._logical_to_action(idx)
            if action is None:
                continue
                
            # Handle back button long press for shutdown
            if action == BUTTON_LEFT:
                if ev == 'press':
                    self._back_press_start = current_time
                    self._back_long_press_triggered = False
                elif ev == 'release':
                    if self._back_press_start and not self._back_long_press_triggered:
                        # Normal short press - handle as usual
                        res = self._top().on_key(action)
                        if res.push:
                            self.push(res.push)
                        if res.pop:
                            self.pop()
                        if res.dirty:
                            acted = True
                    self._back_press_start = None
                    self._back_long_press_triggered = False
            elif ev == 'press':
                # Handle other button presses normally
                res = self._top().on_key(action)
                if res.push:
                    self.push(res.push)
                if res.pop:
                    self.pop()
                if res.dirty:
                    acted = True
                    
        if acted:
            self.dirty = True

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
        
        # Handle ChordCaptureScreen and SingleNoteCaptureScreen updates
        top = self._top()
        if isinstance(top, (ChordCaptureScreen, SingleNoteCaptureScreen)):
            result = top.update()
            if result.pop:
                self.pop()
                return True
            if result.dirty:
                self.dirty = True
                
        return False

    # --- Rendering helpers ---
    def render_into(self, draw: ImageDraw.ImageDraw, w: int, h: int):
        self._top().render(draw, w, h)

class ChordCaptureMenuScreen(Screen):
    def __init__(self):
        self.rows = [
            ("4-Note Capture", self._start_4_note_capture),
            ("Single Note Capture", self._start_single_note_capture),
            ("LoNote OctDown", self._toggle_octave_down),
            ("Back", None),
        ]
        self.sel = 0
        self._chord_capture = None
        self._cfg = None

    def attach(self, chord_capture, config):
        self._chord_capture = chord_capture
        self._cfg = config

    def _start_4_note_capture(self):
        """Start the traditional 4-note chord capture."""
        if self._chord_capture:
            print("Menu: Starting 4-note chord capture")
            screen = ChordCaptureScreen(self._chord_capture)
            screen.activate()
            return ScreenResult(push=screen, dirty=True)
        return ScreenResult(dirty=False)

    def _start_single_note_capture(self):
        """Start the new single-note capture mode."""
        if self._chord_capture:
            print("Menu: Starting single-note capture")
            screen = SingleNoteCaptureScreen(self._chord_capture)
            screen.activate()
            return ScreenResult(push=screen, dirty=True)
        return ScreenResult(dirty=False)

    def _toggle_octave_down(self):
        if self._chord_capture and self._cfg:
            current = self._cfg.get("octave_down_lowest", False)
            new_val = not current
            self._cfg.set("octave_down_lowest", new_val)
            self._cfg.save()
            self._chord_capture.set_octave_down_lowest(new_val)

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_UP:
            self.sel = (self.sel - 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN:
            self.sel = (self.sel + 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_SELECT:
            label, action = self.rows[self.sel]
            if label == "Back":
                return ScreenResult(pop=True)
            if action:
                result = action()
                if result:
                    return result
                return ScreenResult(dirty=True)
        if key == BUTTON_LEFT:
            return ScreenResult(pop=True)
        return ScreenResult(dirty=False)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4, 2), "Chord Capture", fill=1)
        
        octave_down = self._cfg.get("octave_down_lowest", False) if self._cfg else False
        
        body = [
            "4-Note Capture",
            "Single Note Capture", 
            f"LoNote OctDown: {'On' if octave_down else 'Off'}",
            "Back",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

class BaseCaptureScreen(Screen):
    """Base class for chord capture screens with shared spiral and UI elements."""
    
    def __init__(self, chord_capture, turns=20):
        self.chord_capture = chord_capture
        self.active = False
        # Spiral animation state
        self.start_time = 0.0
        self.speed = 3.33  # SPIRAL_SPEED
        self.turns = turns  # Configurable turns
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
        """Handle back button to abort capture."""
        if key == BUTTON_LEFT:  # Back button - abort capture
            self.deactivate()
            return ScreenResult(pop=True)
        return ScreenResult(dirty=False)
    
    def _draw_spiral(self, draw, w, h, t):
        """Draw animated spiral - shared between both capture modes."""
        cx, cy = w // 2, h // 2
        radius = min(w, h) * 0.5 - 2
        
        # Archimedean spiral r = a + b*theta, animated by phase t
        turns = self.turns
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

class SingleNoteCaptureScreen(BaseCaptureScreen):
    def __init__(self, chord_capture):
        super().__init__(chord_capture, turns=10)  # 10 turns for single-note mode
        
        # Note display positions - specific to single-note mode
        self.trigger_position = (118, 32)  # Far right, vertical middle
        self.keyboard_position = (4, 32)   # Far left, vertical middle
        
        # Single-note capture state
        self.captured_trigger_note = None  # Last DDTi trigger note
        self.captured_keyboard_note = None  # Keyboard note to send
        self.waiting_for_trigger = True    # True until we hear from DDTi
        
    def activate(self):
        """Start single note capture mode."""
        super().activate()
        self.captured_trigger_note = None
        self.captured_keyboard_note = None
        self.waiting_for_trigger = True
        
        # Flush any pending messages from both sources
        flushed_messages = list(self.chord_capture.midi.iter_input())
        if flushed_messages:
            print(f"Flushed {len(flushed_messages)} stale keyboard MIDI messages")
            
        # Also clear any DDTi tap messages
        if self.chord_capture.midi._ddti_tap:
            self.chord_capture.midi._ddti_tap.get_recent_notes(0.1)  # Clear recent messages
        
    def update(self) -> ScreenResult:
        """Check for captured notes from separate sources."""
        if not self.active:
            return ScreenResult(dirty=False)
        
        # Check for DDTi trigger notes (from DDTi output)
        if self.waiting_for_trigger:
            ddti_note = self.chord_capture.midi.get_ddti_latest_note()
            if ddti_note is not None:
                self.captured_trigger_note = ddti_note
                self.waiting_for_trigger = False
                print(f"Captured DDTi trigger note: {note_to_name(ddti_note)} ({ddti_note})")
        
        # Check for keyboard input notes (from keyboard input)
        if not self.waiting_for_trigger and self.captured_keyboard_note is None:
            keyboard_messages = list(self.chord_capture.midi.iter_input())
            for msg in keyboard_messages:
                if msg.type == 'note_on' and msg.velocity > 0:
                    self.captured_keyboard_note = msg.note
                    print(f"Captured keyboard note: {note_to_name(msg.note)} ({msg.note})")
                    
                    # Send the single note change
                    self._send_single_note_change()
                    
                    # Start completion timer
                    self.completion_time = time.monotonic()
                    break  # Only capture the first note
        
        # Call base class update for common completion logic
        return super().update()
    
    def _send_single_note_change(self):
        """Send SysEx to change just one trigger's note."""
        if self.captured_trigger_note is None or self.captured_keyboard_note is None:
            return
            
        try:
            # Map the trigger note to a trigger index (0-3)
            trigger_map = {
                36: 0,  # Kick
                38: 1,  # Snare  
                42: 2,  # Hi-hat
                49: 3,  # Crash
            }
            
            # Find which trigger to modify, default to trigger 0
            trigger_index = trigger_map.get(self.captured_trigger_note, 0)
            
            # Create a chord with the new note at the specified trigger position
            default_chord = [36, 38, 42, 49]  # Kick, snare, hi-hat, crash
            new_chord = default_chord.copy()
            new_chord[trigger_index] = self.captured_keyboard_note
            
            print(f"Changing trigger {trigger_index} from {note_to_name(self.captured_trigger_note)} to {note_to_name(self.captured_keyboard_note)}")
            
            # Send SysEx to DDTi
            sysex_msg = self.chord_capture.ddti.build_sysex(new_chord)
            self.chord_capture.midi.send(sysex_msg)
            print(f"Sent single-note SysEx: {len(sysex_msg.data)} bytes")
            
        except Exception as e:
            print(f"Error sending single-note SysEx: {e}")
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        # Use base class frame rendering
        if not self._render_base_frame(draw, w, h):
            return  # Inactive, base class handled it
    
        # Show trigger note on the right middle - specific to single-note mode
        if self.captured_trigger_note is not None:
            trigger_text = f"T:{note_to_name(self.captured_trigger_note)}"
            draw.text(self.trigger_position, trigger_text, fill=1)
        
        # Show keyboard note on the left middle - specific to single-note mode
        if self.captured_keyboard_note is not None:
            keyboard_text = f"K:{note_to_name(self.captured_keyboard_note)}"
            draw.text(self.keyboard_position, keyboard_text, fill=1)
    
        # Show "LISTEN" if we haven't completed capture
        if not self.completion_time:
            self._draw_listen_text(draw, w, h)