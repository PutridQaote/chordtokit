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

class HomeScreen(Screen):
    def __init__(self):
        self.items = [
            "Capture 4 Notes (footswitch)",
            "MIDI Settings",
            "Utilities",
            "About",
        ]
        self.sel = 0

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

    def attach(self, midi_adapter):
        """Called by Menu when this screen becomes active."""
        self._midi = midi_adapter

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
    def __init__(self, midi_adapter=None, config=None):
        self._stack: List[Screen] = [HomeScreen()]
        self.dirty = True
        self.midi = midi_adapter
        self.cfg = config

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
        self._stack.append(screen)
        self.dirty = True

    def pop(self):
        if len(self._stack) > 1:
            self._stack.pop()
            self.dirty = True

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