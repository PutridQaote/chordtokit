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
        
    def activate(self):
        """Start chord capture mode."""
        print(f"ChordCaptureScreen.activate() called")
        print(f"Activating chord capture screen with chord_capture: {id(self.chord_capture)}")
        print(f"chord_capture.active before: {self.chord_capture.active}")
        self.active = True
        self.chord_capture.activate()  # Make sure this calls the ChordCapture.activate()
        self.chord_capture.clear_bucket()
        print(f"chord_capture.active after: {self.chord_capture.active}")
        
    def deactivate(self):
        """Stop chord capture mode."""
        print(f"ChordCaptureScreen.deactivate() called")
        self.active = False
        self.chord_capture.deactivate()  # Make sure this calls the ChordCapture.deactivate()
        self.chord_capture.clear_bucket()
    
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
            # Chord was captured and sent - exit screen
            self.deactivate()
            return ScreenResult(pop=True)
            
        return ScreenResult(dirty=True)  # Always dirty to show live updates
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0, 0, w-1, h-1), outline=1, fill=0)
        
        if not self.active:
            draw.text((4, h//2), "Chord capture inactive", fill=1)
            return
            
        # Title
        title = "Listening for 4 notes..."
        bbox = draw.textbbox((0, 0), title)
        title_w = bbox[2] - bbox[0]
        draw.text(((w - title_w) // 2, 10), title, fill=1)
        
        # Show current notes
        status = self.chord_capture.get_bucket_status()
        notes = status['notes']
        
        y = 28
        if notes:
            note_line = " ".join([f"{note_to_name(note)}({note})" for note in notes[-4:]])
            draw.text((4, y), note_line, fill=1)
            y += 12
            
        # Progress indicator
        progress = f"{len(set(notes))}/4 unique notes"
        draw.text((4, y), progress, fill=1)
        
        # Instructions
        draw.text((4, h-24), "LEFT key to cancel", fill=1)

class HomeScreen(Screen):
    def __init__(self):
        self.items = [
            "Capture 4 Notes (footswitch)",
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
            elif label == "Capture 4 Notes (footswitch)":
                # Create and activate chord capture screen
                if self._chord_capture:
                    screen = ChordCaptureScreen(self._chord_capture)
                    screen.activate()
                    return ScreenResult(push=screen, dirty=True)
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