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

BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT = 0, 1, 2, 3  # logical left→right indices

def note_to_name(midi_note):
    """Convert MIDI note number to note name like 'F#4'."""
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_note // 12) - 1
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
        # Spiral animation state
        self.start_time = 0.0
        self.speed = 3.33  # Hard-coded as in test file
        self.turns = 20   # Hard-coded as in test file
        # Note display positions (corners)
        self.note_positions = [
            (4, 4),      # Top-left
            (4, 52),     # Bottom-left  
            (100, 52),   # Bottom-right
            (100, 4),    # Top-right
        ]
        self.completion_time = None  # When 4th note was captured
        
    def activate(self):
        """Start chord capture mode."""
        self.active = True
        self.start_time = time.monotonic()
        self.completion_time = None
        self.chord_capture.activate()  # This will clear bucket and flush MIDI
        
    def deactivate(self):
        """Stop chord capture mode."""
        self.active = False
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
            # Chord was captured and sent - start 1 second countdown
            self.completion_time = time.monotonic()
            
        # Check if we should exit after 1 second delay
        if self.completion_time and (time.monotonic() - self.completion_time) >= 1.0:
            self.deactivate()
            return ScreenResult(pop=True)
            
        return ScreenResult(dirty=True)  # Always dirty to show live updates
    
    def _draw_spiral(self, draw, center_x, center_y, max_radius):
        """Draw animated spiral based on test_spiral_oled_neokeyHits.py"""
        now = time.monotonic()
        elapsed = now - self.start_time
        
        # Animate the spiral
        angle_offset = elapsed * self.speed * 2 * math.pi
        
        points = []
        steps = 100  # Number of points to draw
        
        for i in range(steps):
            t = i / steps
            angle = t * self.turns * 2 * math.pi + angle_offset
            radius = t * max_radius
            
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            points.append((int(x), int(y)))
        
        # Draw the spiral as connected line segments
        for i in range(len(points) - 1):
            try:
                draw.line([points[i], points[i + 1]], fill=1, width=1)
            except:
                pass  # Skip if points are out of bounds
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0, 0, w-1, h-1), outline=1, fill=0)
        
        if not self.active:
            draw.text((4, h//2), "Chord capture inactive", fill=1)
            return
        
        # Draw animated spiral in center
        center_x, center_y = w // 2, h // 2
        max_radius = min(w, h) // 4  # Adjust size to fit screen
        self._draw_spiral(draw, center_x, center_y, max_radius)
        
        # Show captured notes in corners
        status = self.chord_capture.get_bucket_status()
        notes = status['notes']
        
        # Display up to 4 notes in the corner positions
        for i, note in enumerate(notes[:4]):
            if i < len(self.note_positions):
                x, y = self.note_positions[i]
                note_text = f"{note_to_name(note)}"
                draw.text((x, y), note_text, fill=1)
        
        # Show completion message if chord was captured
        if self.completion_time:
            # Flash "Complete!" message
            elapsed_since_complete = time.monotonic() - self.completion_time
            if int(elapsed_since_complete * 4) % 2:  # Blink 4 times per second
                complete_text = "Complete!"
                bbox = draw.textbbox((0, 0), complete_text)
                text_w = bbox[2] - bbox[0]
                draw.text(((w - text_w) // 2, h - 16), complete_text, fill=1)


class UtilitiesScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Allow Duplicate Notes", self._toggle_duplicates),
            ("Back", None),
        ]
        self.sel = 0
        self._chord_capture = None
        self._cfg = None

    def attach(self, chord_capture, config):
        self._chord_capture = chord_capture
        self._cfg = config

    def _toggle_duplicates(self):
        if self._chord_capture and self._cfg:
            current = self._cfg.get("allow_duplicate_notes", False)
            new_val = not current
            self._cfg.set("allow_duplicate_notes", new_val)
            self._cfg.save()
            self._chord_capture.set_allow_duplicates(new_val)

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
        
        body = [
            f"Duplicates: {'On' if allow_dupes else 'Off'}",
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
            "Initiate Chord Capture",
            "MIDI Settings",
            "Utilities",
            "About",
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
            elif label == "Initiate Chord Capture":
                # Create and activate chord capture screen
                if self._chord_capture:
                    print("Menu: Starting chord capture")
                    screen = ChordCaptureScreen(self._chord_capture)
                    screen.activate()  # This will clear bucket and flush MIDI
                    return ScreenResult(push=screen, dirty=True)
            elif label == "Utilities":
                return ScreenResult(push=UtilitiesScreen(), dirty=True)
            # Other screens can be added similarly
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
            ("Input Port", self._cycle_in),
            ("Output Port", self._cycle_out),
            ("Thru", self._toggle_thru),
            ("Back", None),
        ]
        self.sel = 0
        # The actual port lists are fetched from the midi adapter lazily in render

    def attach(self, midi_adapter, config):
        self._midi = midi_adapter
        self._cfg = config

    def _cycle_in(self):
        midi = self._midi
        ins = midi.get_inputs()
        if not ins: return
        cur = midi.get_selected_in()
        idx = (ins.index(cur) + 1) % len(ins) if cur in ins else 0
        chosen = ins[idx]
        midi.set_in(chosen)
        # persist
        self._cfg.set("midi_in_name", chosen)
        self._cfg.save()

    def _cycle_out(self):
        midi = self._midi
        outs = midi.get_outputs()
        if not outs: return
        cur = midi.get_selected_out()
        idx = (outs.index(cur) + 1) % len(outs) if cur in outs else 0
        chosen = outs[idx]
        midi.set_out(chosen)
        # persist
        self._cfg.set("midi_out_name", chosen)
        self._cfg.save()

    def _toggle_thru(self):
        midi = self._midi
        new_val = not midi.get_thru()
        midi.set_thru(new_val)
        # persist
        self._cfg.set("midi_thru", new_val)
        self._cfg.save()

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
        draw.text((4, 2), "MIDI Settings", fill=1)
        midi = getattr(self, "_midi", None)
        ins = midi.get_inputs() if midi else []
        outs = midi.get_outputs() if midi else []
        cur_in = midi.get_selected_in() if midi else "-"
        cur_out = midi.get_selected_out() if midi else "-"
        thru = midi.get_thru() if midi else False
        body = [
            f"In Port:  {cur_in if cur_in else '-'}",
            f"OutPort: {cur_out if cur_out else '-'}",
            f"Thru:        {'On' if thru else 'Off'}",
            "Back",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

class Menu:
    def __init__(self, midi_adapter=None, config=None, chord_capture=None):
        self._stack: List[Screen] = [HomeScreen()]
        self.dirty = True
        self.midi = midi_adapter
        self.cfg = config
        self.chord_capture = chord_capture
        
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
        if isinstance(screen, MidiSettingsScreen) and self.midi is not None:
            screen.attach(self.midi, self.cfg)
        elif isinstance(screen, UtilitiesScreen) and self.chord_capture is not None:
            screen.attach(self.chord_capture, self.cfg)
        elif isinstance(screen, HomeScreen) and self.chord_capture:
            screen._chord_capture = self.chord_capture
        self._stack.append(screen)
        self.dirty = True

    def pop(self):
        if len(self._stack) > 1:
            self._stack.pop()
            self.dirty = True

    def update(self) -> bool:
        """Update active screen and return True if screen changed."""
        top = self._top()
        if isinstance(top, ChordCaptureScreen):
            result = top.update()
            if result.pop:
                self.pop()
                return True
            if result.dirty:
                self.dirty = True
        return False

    def handle_events(self, key_events: List[tuple]):
        """Consume NeoKey events [('press'|'release', idx), ...]."""
        acted = False
        for ev, idx in key_events:
            if ev != 'press':
                continue
            action = self._logical_to_action(idx)
            if action is None:
                continue
            res = self._top().on_key(action)
            if res.push:
                self.push(res.push)
            if res.pop:
                self.pop()
            if res.dirty:
                acted = True
        if acted:
            self.dirty = True

    # --- Rendering helpers ---
    def render_into(self, draw: ImageDraw.ImageDraw, w: int, h: int):
        self._top().render(draw, w, h)