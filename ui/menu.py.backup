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
import mido

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

class ChordCaptureMenuScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Full Chord Capture", self._start_4_note_capture),
            ("Learn Mapping", self._start_learn_mapping),
            ("Single Note Capture", self._start_single_note_capture),
            ("Footswitch Mode", self._toggle_footswitch_mode),
        ]
        self.sel = 0
        self._chord_capture = None
        self._cfg = None
        self._alsa_router = None

    def attach(self, chord_capture, config, alsa_router=None):
        self._chord_capture = chord_capture
        self._cfg = config
        self._alsa_router = alsa_router

    def _start_4_note_capture(self):
        """Start the traditional 4-note chord capture."""
        if self._chord_capture:
            print("Menu: Starting 4-note chord capture")
            screen = ChordCaptureScreen(self._chord_capture, config=self._cfg)  # Pass config
            screen.activate()
            return ScreenResult(push=screen, dirty=True)
        return ScreenResult(dirty=False)

    def _start_single_note_capture(self):
        """Start the new single-note capture mode."""
        if self._chord_capture:
            # Check if we have a learned mapping
            if not self._chord_capture.has_learned_mapping():
                print("Menu: No learned mapping, starting Learn Mapping first")
                screen = LearnMappingScreen(self._chord_capture, config=self._cfg, auto_continue_to_single=True)
                if self._alsa_router:
                    screen.set_alsa_router(self._alsa_router)
                screen.activate()
                return ScreenResult(push=screen, dirty=True)
            else:
                print("Menu: Starting single-note capture")
                screen = SingleNoteCaptureScreen(self._chord_capture, config=self._cfg)  # Pass config
                if self._alsa_router:
                    screen.set_alsa_router(self._alsa_router)
                screen.activate()
                return ScreenResult(push=screen, dirty=True)
        return ScreenResult(dirty=False)
    
    def _start_learn_mapping(self):
        """Start the learn mapping mode."""
        if self._chord_capture:
            print("Menu: Starting learn mapping")
            screen = LearnMappingScreen(self._chord_capture, config=self._cfg)
            if self._alsa_router:
                screen.set_alsa_router(self._alsa_router)
            screen.activate()
            return ScreenResult(push=screen, dirty=True)
        return ScreenResult(dirty=False)

    def _toggle_footswitch_mode(self):
        """Toggle footswitch mode between 'all' (4-note) and 'single' (1-note)."""
        if self._cfg:
            current = self._cfg.get("footswitch_capture_mode", "all")  # Default to "all"
            new_mode = "single" if current == "all" else "all"
            self._cfg.set("footswitch_capture_mode", new_mode)
            self._cfg.save()
            print(f"Footswitch mode changed to: {new_mode}")

    def _get_footswitch_mode_label(self) -> str:
        """Get the current footswitch mode as a label."""
        if not self._cfg:
            return "All"
        mode = self._cfg.get("footswitch_capture_mode", "all")
        return "All" if mode == "all" else "1 Note"

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_UP:
            self.sel = (self.sel - 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN:
            self.sel = (self.sel + 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_SELECT:
            label, action = self.rows[self.sel]
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
        
        footswitch_mode = self._get_footswitch_mode_label()
        
        body = [
            "Full Chord Capture",
            "Learn Mapping",
            "Single Note Capture",
            f"Footswitch: {footswitch_mode}",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

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

class LearnMappingScreen(BaseCaptureScreen):
    """Screen for learning the 4 trigger mappings in order: KICK, SNARE, HI-HAT, RIDE."""
    
    def __init__(self, chord_capture, config=None, auto_continue_to_single=False):
        super().__init__(chord_capture, turns=10, 
                        config_key="spiral_turns_learn", config=config)
        
        self.trigger_names = ["KICK", "SNARE", "HI-HAT", "RIDE"]
        self.current_trigger = 0  # Index into trigger_names
        self.learned_notes = []   # Notes we've captured
        self.auto_continue_to_single = auto_continue_to_single  # Auto-launch single capture when done
        
        # ALSA router reference
        self.alsa_router = None
        self._last_hit_ts = 0.0
        self._debounce_s = 0.12
        self._min_vel = 8
        
    def set_alsa_router(self, router):
        """Set the ALSA router reference."""
        self.alsa_router = router
        
    def activate(self):
        """Start learn mapping mode."""
        super().activate()
        self.current_trigger = 0
        self.learned_notes = []
        self._activation_guard_until = time.monotonic() + 0.04  # 40ms ignore window
        
        # Drain any stale MIDI
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"LearnMapping: Activated (drained {drained} stale msgs)")
        
    def deactivate(self):
        """Stop learn mapping mode."""
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"LearnMapping: Deactivated (drained {drained} msgs on exit)")
        super().deactivate()
        
    def update(self) -> ScreenResult:
        if not self.active:
            return ScreenResult(dirty=False)
            
        now = time.monotonic()
        midi = self.chord_capture.midi
        
        # Only capture after guard window
        capture_enabled = now >= getattr(self, "_activation_guard_until", 0)
        
        if capture_enabled and self.current_trigger < len(self.trigger_names):
            # Listen for DDTi trigger hits
            for msg in midi.iter_ddti_all():
                if (msg.type == 'note_on' and msg.velocity >= self._min_vel):
                    if now - self._last_hit_ts >= self._debounce_s:
                        self._last_hit_ts = now
                        
                        # Check if this note is already learned
                        if msg.note not in self.learned_notes:
                            trigger_name = self.trigger_names[self.current_trigger]
                            self.learned_notes.append(msg.note)
                            print(f"LearnMapping: {trigger_name} = {note_to_name(msg.note)} ({msg.note})")
                            
                            self.current_trigger += 1
                            
                            # Check if we're done learning all 4
                            if self.current_trigger >= len(self.trigger_names):
                                print(f"LearnMapping: Complete! Learned: {self.learned_notes}")
                                self._complete_learning()
                                return ScreenResult(dirty=True)
                                
                            return ScreenResult(dirty=True)
                        else:
                            print(f"LearnMapping: Note {msg.note} already learned, skipping")
        
        # Check for completion and auto-continue
        if self.completion_time and (time.monotonic() - self.completion_time) >= 1.0:
            self.deactivate()
            
            if self.auto_continue_to_single:
                # Auto-launch single note capture
                screen = SingleNoteCaptureScreen(self.chord_capture, config=self.config)
                if self.alsa_router:
                    screen.set_alsa_router(self.alsa_router)
                screen.activate()
                return ScreenResult(push=screen, pop=True, dirty=True)
            else:
                return ScreenResult(pop=True, dirty=True)
                
        return ScreenResult(dirty=True) if self.active else ScreenResult(dirty=False)
        
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        if not self._render_base_frame(draw, w, h):
            return
            
        # Show which trigger we're learning
        if self.current_trigger < len(self.trigger_names):
            trigger_name = self.trigger_names[self.current_trigger]
            step_text = f"{trigger_name} ({self.current_trigger + 1})"
            
            # Center the trigger name at top
            bbox = draw.textbbox((0, 0), step_text)
            text_w = bbox[2] - bbox[0]
            text_x = (w - text_w) // 2
            draw.text((text_x, 4), step_text, fill=1)
            
            # Show instruction
            instruction = "Hit the trigger"
            bbox = draw.textbbox((0, 0), instruction)
            text_w = bbox[2] - bbox[0]
            text_x = (w - text_w) // 2
            draw.text((text_x, h - 15), instruction, fill=1)
        else:
            # Learning complete
            complete_text = "Mapping Complete!"
            bbox = draw.textbbox((0, 0), complete_text)
            text_w = bbox[2] - bbox[0]
            text_x = (w - text_w) // 2
            draw.text((text_x, h // 2), complete_text, fill=1)
            
        # Show learned notes on the left side
        for i, note in enumerate(self.learned_notes):
            if i < len(self.trigger_names):
                trigger_name = self.trigger_names[i]
                note_text = f"{trigger_name[:4]}: {note_to_name(note)}"
                draw.text((4, 16 + i * 10), note_text, fill=1)

class ChordCaptureScreen(BaseCaptureScreen):
    def __init__(self, chord_capture, config=None):
        # Call parent with config settings for 4-note mode
        super().__init__(chord_capture, turns=20, 
                        config_key="spiral_turns_4_note", config=config)
        
        # Note display positions (corners)
        self.note_positions = [
            (4, 4),      # Top-left
            (4, 52),     # Bottom-left  
            (100, 52),   # Bottom-right
            (100, 4),    # Top-right
        ]
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

class SingleNoteCaptureScreen(BaseCaptureScreen):
    def __init__(self, chord_capture, config=None):
        # Call parent with config settings for single-note mode
        super().__init__(chord_capture, turns=5, 
                        config_key="spiral_turns_single", config=config)
        
        # Note display positions - specific to single-note mode
        self.trigger_position = (105, 32)  # Far right, vertical middle
        self.keyboard_position = (4, 32)   # Far left, vertical middle
        
        # Single-note capture state
        self.captured_trigger_note = None
        self.captured_keyboard_note = None
        self.waiting_for_trigger = True
        
        # ALSA router reference
        self.alsa_router = None
        self._original_keyboard_routing = False
        self._ddti_in = None
        self._prev_kb_thru = None
        self._last_ddti_hit_ts = 0.0
        self._debounce_s = 0.12
        self._min_vel = 8
    
    def set_alsa_router(self, router):
        """Set the ALSA router reference."""
        self.alsa_router = router
        
    def activate(self):
        """Start single note capture mode."""
        super().activate()
        # Reset state
        self.captured_trigger_note = None
        self.captured_keyboard_note = None
        self.waiting_for_trigger = True
        self._activation_guard_until = time.monotonic() + 0.04  # 40ms ignore window
        # Drain any stale MIDI so we start clean
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"SingleNote: Activated (drained {drained} stale msgs)")

    def deactivate(self):
        """Stop single note capture mode."""
        # Drain again so we don't leave residuals for the next mode
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"SingleNote: Deactivated (drained {drained} msgs on exit)")
        super().deactivate()

    def update(self) -> ScreenResult:
        if not self.active:
            return ScreenResult(dirty=False)

        now = time.monotonic()
        midi = self.chord_capture.midi

        # Only capture after guard window
        capture_enabled = now >= getattr(self, "_activation_guard_until", 0)

        # Listen for DDTi trigger hits to select which note to change
        for msg in midi.iter_ddti_all():
            if (capture_enabled and
                msg.type == 'note_on' and msg.velocity > 0 and
                self.captured_keyboard_note is None):
                
                # Check if this trigger note is in our learned mapping
                learned_mapping = self.chord_capture.get_learned_mapping()
                if learned_mapping and msg.note in learned_mapping:
                    self.captured_trigger_note = msg.note
                    self.waiting_for_trigger = False
                    print(f"SingleNote: Selected trigger note {note_to_name(msg.note)} ({msg.note})")
                else:
                    print(f"SingleNote: Note {msg.note} not in learned mapping, ignoring")

        # Listen for keyboard notes to replace the selected trigger
        if (capture_enabled and
            self.captured_trigger_note is not None and
            self.captured_keyboard_note is None):
            
            for msg in midi.iter_input():
                if msg.type == 'note_on' and getattr(msg, 'velocity', 0) > 0:
                    self.captured_keyboard_note = msg.note
                    print(f"SingleNote: Captured keyboard note {note_to_name(msg.note)} ({msg.note})")
                    self._send_single_note_change()
                    # Drain immediately after sending so no cascade into next screen
                    midi.drain_all_inputs()
                    self.completion_time = time.monotonic()
                    break

        return super().update()

    def _send_single_note_change(self):
        """Send SysEx to change one note in the learned mapping."""
        if self.captured_trigger_note is None or self.captured_keyboard_note is None:
            return
            
        old_note = self.captured_trigger_note
        new_note = self.captured_keyboard_note
        
        # Get current learned mapping
        learned_mapping = self.chord_capture.get_learned_mapping()
        if not learned_mapping:
            print("SingleNote: No learned mapping available")
            return
            
        # Find the index of the old note and replace it
        try:
            index = learned_mapping.index(old_note)
            new_mapping = learned_mapping[:]
            new_mapping[index] = new_note
            
            # Record current state for undo
            self.chord_capture.record_current_state_for_undo()
            
            # Send the updated mapping
            sysex_msg = self.chord_capture.ddti.build_full_sysex(new_mapping)
            sent = self.chord_capture.midi.send(sysex_msg)
            
            if sent:
                print(f"SingleNote: Changed {note_to_name(old_note)} -> {note_to_name(new_note)}")
                # Update the learned mapping
                self.chord_capture.set_learned_mapping(new_mapping)
            else:
                print("SingleNote: MIDI send failed")
                
        except ValueError:
            print(f"SingleNote: Note {old_note} not found in learned mapping")

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:
            self.deactivate()
            return ScreenResult(pop=True)
        elif key == BUTTON_UP:
            self.turns = min(50, self.turns + 1)
            self._save_turns_to_config()
            return ScreenResult(dirty=True)
        elif key == BUTTON_DOWN:
            self.turns = max(1, self.turns - 1)
            self._save_turns_to_config()
            return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        if not self._render_base_frame(draw, w, h):
            return
            
        # Check if we have a learned mapping
        if not self.chord_capture.has_learned_mapping():
            draw.text((4, 4), "Need Learn Mapping", fill=1)
            return

        if self.captured_trigger_note is not None:
            draw.text(self.trigger_position,
                      f"{note_to_name(self.captured_trigger_note)}", fill=1)
        if self.captured_keyboard_note is not None:
            draw.text(self.keyboard_position,
                      f"{note_to_name(self.captured_keyboard_note)}", fill=1)
        if not self.completion_time:
            self._draw_listen_text(draw, w, h)

class UtilitiesScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Allow Duplicate Notes", self._toggle_duplicates),
            ("LoNote OctDown", self._toggle_octave_down),
            ("Undo Mapping", self._undo_mapping),
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

    def _toggle_octave_down(self):
        """Toggle octave down for lowest note."""
        if self._chord_capture and self._cfg:
            current = self._cfg.get("octave_down_lowest", False)
            new_val = not current
            self._cfg.set("octave_down_lowest", new_val)
            self._cfg.save()
            self._chord_capture.set_octave_down_lowest(new_val)

    def _undo_mapping(self):
        """Undo the most recent mapping change."""
        if self._chord_capture:
            ok = self._chord_capture.undo_last_mapping()
            if not ok:
                print("Utilities: Undo failed or no history")
        return ScreenResult(dirty=True)

    def _cycle_led_brightness(self):
        """Cycle through LED brightness levels: 100%, 75%, 50%, 25%, Off."""
        if self._cfg and self._neokey:
            current = self._cfg.get("led_backlight_brightness", 1.0)
            levels = [1.0, 0.75, 0.5, 0.25, 0.0]
            try:
                current_index = levels.index(current)
                new_index = (current_index + 1) % len(levels)
            except ValueError:
                new_index = 0  # Default to 100% if current value not in list
            
            new_brightness = levels[new_index]
            self._cfg.set("led_backlight_brightness", new_brightness)
            self._cfg.save()
            
            # Update NeoKey brightness immediately
            self._neokey.set_brightness(new_brightness)
            
            print(f"LED brightness set to {int(new_brightness * 100)}%")

    def _get_led_brightness_label(self) -> str:
        """Get the current LED brightness as a label."""
        if not self._cfg:
            return "100%"
        brightness = self._cfg.get("led_backlight_brightness", 1.0)
        if brightness == 0.0:
            return "Off"
        return f"{int(brightness * 100)}%"

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_UP:
            self.sel = (self.sel - 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN:
            self.sel = (self.sel + 1) % len(self.rows)
            return ScreenResult(dirty=True)
        if key == BUTTON_SELECT:
            label, action = self.rows[self.sel]
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
        draw.text((4, 2), "Utilities", fill=1)
        
        allow_dupes = self._cfg.get("allow_duplicate_notes", False) if self._cfg else False
        octave_down = self._cfg.get("octave_down_lowest", False) if self._cfg else False
        led_brightness = self._get_led_brightness_label()
        
        body = [
            f"Duplicates: {'On' if allow_dupes else 'Off'}",
            f"LoNote OctDown: {'On' if octave_down else 'Off'}",
            "Undo Mapping",
            f"LEDs: {led_brightness}",
            "Back",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

class ShutdownConfirmScreen(Screen):
    def __init__(self, neokey=None):
        self.neokey = neokey
        self.sel = 0  # 0 = Cancel, 1 = Shutdown
        
    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:  # Cancel
            return ScreenResult(pop=True)
        elif key == BUTTON_UP or key == BUTTON_DOWN:
            self.sel = 1 - self.sel  # Toggle between 0 and 1
            return ScreenResult(dirty=True)
        elif key == BUTTON_SELECT:
            if self.sel == 0:  # Cancel
                return ScreenResult(pop=True)
            else:  # Shutdown
                self._initiate_shutdown()
                return ScreenResult(pop=True)
        return ScreenResult(dirty=False)
    
    def _initiate_shutdown(self):
        """Trigger system shutdown."""
        print("User confirmed shutdown - initiating...")
        
        # Turn off NeoKey LEDs before shutdown
        if self.neokey:
            self.neokey.set_brightness(0.0)
            time.sleep(0.1)  # Brief pause to ensure it takes effect
        
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to initiate shutdown: {e}")
        except FileNotFoundError:
            print("Shutdown command not found - running in development environment?")
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        
        # Title
        draw.text((4, 2), "Shutdown System?", fill=1)
        
        # Options
        y = 20
        options = ["Cancel", "Shutdown"]
        for i, option in enumerate(options):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + option, fill=1)
            y += 12
        
        # Instructions
        draw.text((4, h - 24), "UP/DOWN: Select", fill=1)
        draw.text((4, h - 12), "LEFT: Cancel, SELECT: Confirm", fill=1)

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

# Keep DDTiSyncScreen class for potential future use, but remove from active menu system
class DDTiSyncScreen(Screen):
    """
    Screen that waits for a manual DDTi bank dump to ingest kit0.
    User triggers dump on the hardware; we watch incoming MIDI for kit0 bulk frame.
    
    NOTE: This screen is kept for potential future use but is no longer part of the
    active menu system. The new Learn Mapping workflow has replaced DDTi dumps.
    """
    def __init__(self, chord_capture):
        self._cc = chord_capture
        self._done = False
        self._status = "Waiting for dump..."
        self._last_notes = None
        self._start_ts = time.monotonic()
        self._sysex_count = 0
        self._debug_messages = []
        # Add state for managing ALSA router
        self._alsa_router = None
        self._prev_ddti_thru = None

    def attach(self, chord_capture, config, alsa_router=None):
        """Attach shared objects to the screen."""
        self._cc = chord_capture
        self._alsa_router = alsa_router

    def activate(self):
        """Called when the screen becomes active. Temporarily disables DDTi thru."""
        self._add_debug("Activating Sync...")
        if self._alsa_router:
            self._prev_ddti_thru = self._alsa_router.get_ddti_thru()
            if self._prev_ddti_thru:
                self._add_debug("Disabling DDTi thru")
                self._alsa_router.set_ddti_thru(False)
                time.sleep(0.2)  # Give filter thread time to die and release port
        
        # Now that the port is hopefully free, reopen MIDI ports
        self._add_debug("Re-opening MIDI ports")
        self._cc.midi.reopen_ports()

    def deactivate(self):
        """Called when the screen is closed. Restores DDTi thru."""
        self._add_debug("Deactivating Sync...")
        if self._alsa_router and self._prev_ddti_thru is not None:
            self._add_debug("Restoring DDTi thru")
            self._alsa_router.set_ddti_thru(self._prev_ddti_thru)

    def _add_debug(self, msg: str):
        """Add a debug message with timestamp."""
        ts = time.strftime("%H:%M:%S", time.localtime())
        full_msg = f"{ts}: {msg}"
        self._debug_messages.append(full_msg)
        if len(self._debug_messages) > 5:  # Keep only last 5 messages
            self._debug_messages.pop(0)
        print(f"DDTiSync: {full_msg}")

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4,2), "DDTi Sync", fill=1)
        
        y = 14
        
        # Show DDTi input connection status
        ddti_port = self._cc.midi.get_ddti_in_port_name()
        if not ddti_port:
            draw.text((4, y), "No DDTi input ✗", fill=1)
            y += 10
        
        # One blank line after header
        y += 7
        
        # Instructions - only center the main message
        if self._done:
            # Center "Kit0 captured!"
            text1 = "Kit0 captured!"
            bbox1 = draw.textbbox((0, 0), text1)
            text1_w = bbox1[2] - bbox1[0]
            text1_x = (w - text1_w) // 2
            draw.text((text1_x, y), text1, fill=1)
            
            # Center "SELECT to continue"
            text2 = "SELECT to continue"
            bbox2 = draw.textbbox((0, 0), text2)
            text2_w = bbox2[2] - bbox2[0]
            text2_x = (w - text2_w) // 2
            draw.text((text2_x, y + 10), text2, fill=1)
        else:
            # Center "Trigger DDTi"
            text1 = "Trigger DDTi"
            bbox1 = draw.textbbox((0, 0), text1)
            text1_w = bbox1[2] - bbox1[0]
            text1_x = (w - text1_w) // 2
            draw.text((text1_x, y), text1, fill=1)
            
            # Center "SysEx Dump..."
            text2 = "SysEx Dump..."
            bbox2 = draw.textbbox((0, 0), text2)
            text2_w = bbox2[2] - bbox2[0]
            text2_x = (w - text2_w) // 2
            draw.text((text2_x, y + 10), text2, fill=1)
            
            text3 = "(Function & Value Up)"
            bbox3 = draw.textbbox((0, 0), text3)
            text3_w = bbox3[2] - bbox3[0]
            text3_x = (w - text3_w) // 2
            draw.text((text3_x, y + 20), text3, fill=1)

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:
            self.deactivate()  # Deactivate before popping
            return ScreenResult(pop=True)
        if key == BUTTON_SELECT and self._done:
            self.deactivate()  # Deactivate before popping
            return ScreenResult(pop=True)
        if key == BUTTON_UP and not self._done:
            # Debug: show port status
            ddti_port = self._cc.midi.get_ddti_in_port_name()
            self._add_debug(f"DDTi port: {ddti_port}")
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN and not self._done:
            # Debug: show current DDTi state
            if self._cc.ddti.have_kit0_bulk():
                notes = self._cc.ddti.extract_kit0_notes()
                self._add_debug(f"Kit0: {notes}")
            else:
                self._add_debug("No kit0 bulk")
            return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)

    def update(self) -> ScreenResult:
        # Use the new dedicated DDTi SysEx input method
        sysex_messages = self._cc.midi.iter_ddti_sysex()
        
        for msg in sysex_messages:
            self._sysex_count += 1
            data = bytes(msg.data)
            
            # Log exactly like the working script
            self._add_debug(f"SysEx len={len(data)} head={list(data[:8])}")
            
            # Try to ingest into DDTi
            try:
                before_bulk = self._cc.ddti.have_kit0_bulk()
                self._cc.ddti.ingest_sysex_frame(data)
                after_bulk = self._cc.ddti.have_kit0_bulk()
                
                if not before_bulk and after_bulk:
                    self._add_debug("*** Kit0 captured! ***")
                    
                    # Record the captured kit0 state as the initial undo point
                    notes = self._cc.ddti.extract_kit0_notes()
                    if notes:
                        # Store this as the "original" state for undo
                        self._cc.record_current_state_for_undo()
                        self._add_debug(f"Initial undo state: {notes}")
                
            except Exception as e:
                self._add_debug(f"Ingest error: {e}")
        
        # Check if we successfully captured kit0
        if not self._done and self._cc.ddti.have_kit0_bulk():
            notes = self._cc.ddti.extract_kit0_notes()
            if notes:
                self._last_notes = notes
                self._status = "Kit0 captured!"
                self._done = True
                self._add_debug(f"SUCCESS: {notes}")
                
                # Auto-exit after successful capture
                time.sleep(0.5)  # Brief pause to show success
                self.deactivate()  # Clean up ALSA routing
                return ScreenResult(pop=True, dirty=True)  # Auto-exit
        
        # Auto-refresh display every 0.5 seconds
        if (time.monotonic() - self._start_ts) > 0.5:
            self._start_ts = time.monotonic()
            return ScreenResult(dirty=True)
            
        return ScreenResult(dirty=False)

class HomeScreen(Screen):
    def __init__(self):
        self.items = [
            "Chord Capture",
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
        draw.text((4, 2), "ChordToKit", fill=1)
        
        # Show if we have learned mapping
        if self._chord_capture and self._chord_capture.has_learned_mapping():
            draw.text((80, 2), "✓", fill=1)  # Checkmark if learned
        
        y = 16
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
        inputs = self._midi.get_inputs()
        current = self._midi.get_in_port_name()
        
        if not inputs:
            return
            
        try:
            current_idx = inputs.index(current) if current else -1
            new_idx = (current_idx + 1) % len(inputs)
            new_port = inputs[new_idx]
            
            self._cfg.set("midi_in_name", new_port)
            self._cfg.save()
            self._midi.set_in(new_port)
            print(f"MIDI input changed to: {new_port}")
        except Exception as e:
            print(f"Error cycling MIDI input: {e}")

    def _cycle_out(self):
        """Cycle through available MIDI output ports."""
        outputs = self._midi.get_outputs()
        current = self._midi.get_out_port_name()
        
        if not outputs:
            return
            
        try:
            current_idx = outputs.index(current) if current else -1
            new_idx = (current_idx + 1) % len(outputs)
            new_port = outputs[new_idx]
            
            self._cfg.set("midi_out_name", new_port)
            self._cfg.save()
            self._midi.set_out(new_port)
            print(f"MIDI output changed to: {new_port}")
        except Exception as e:
            print(f"Error cycling MIDI output: {e}")

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
        self.neokey = neokey
        self.sel = 0  # 0 = Cancel, 1 = Shutdown
        
    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:  # Cancel
            return ScreenResult(pop=True)
        elif key == BUTTON_UP or key == BUTTON_DOWN:
            self.sel = 1 - self.sel  # Toggle between 0 and 1
            return ScreenResult(dirty=True)
        elif key == BUTTON_SELECT:
            if self.sel == 0:  # Cancel
                return ScreenResult(pop=True)
            else:  # Shutdown
                self._initiate_shutdown()
                return ScreenResult(pop=True)
        return ScreenResult(dirty=False)
    
    def _initiate_shutdown(self):
        """Trigger system shutdown."""
        print("User confirmed shutdown - initiating...")
        
        # Turn off NeoKey LEDs before shutdown
        if self.neokey:
            self.neokey.set_brightness(0.0)
            time.sleep(0.1)  # Brief pause to ensure it takes effect
        
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to initiate shutdown: {e}")
        except FileNotFoundError:
            print("Shutdown command not found - running in development environment?")
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        
        # Title
        draw.text((4, 2), "Shutdown System?", fill=1)
        
        # Options
        y = 20
        options = ["Cancel", "Shutdown"]
        for i, option in enumerate(options):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + option, fill=1)
            y += 12
        
        # Instructions
        draw.text((4, h - 24), "UP/DOWN: Select", fill=1)
        draw.text((4, h - 12), "LEFT: Cancel, SELECT: Confirm", fill=1)

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

# Keep DDTiSyncScreen class for potential future use, but remove from active menu system
class DDTiSyncScreen(Screen):
    """
    Screen that waits for a manual DDTi bank dump to ingest kit0.
    User triggers dump on the hardware; we watch incoming MIDI for kit0 bulk frame.
    
    NOTE: This screen is kept for potential future use but is no longer part of the
    active menu system. The new Learn Mapping workflow has replaced DDTi dumps.
    """
    def __init__(self, chord_capture):
        self._cc = chord_capture
        self._done = False
        self._status = "Waiting for dump..."
        self._last_notes = None
        self._start_ts = time.monotonic()
        self._sysex_count = 0
        self._debug_messages = []
        # Add state for managing ALSA router
        self._alsa_router = None
        self._prev_ddti_thru = None

    def attach(self, chord_capture, config, alsa_router=None):
        """Attach shared objects to the screen."""
        self._cc = chord_capture
        self._alsa_router = alsa_router

    def activate(self):
        """Called when the screen becomes active. Temporarily disables DDTi thru."""
        self._add_debug("Activating Sync...")
        if self._alsa_router:
            self._prev_ddti_thru = self._alsa_router.get_ddti_thru()
            if self._prev_ddti_thru:
                self._add_debug("Disabling DDTi thru")
                self._alsa_router.set_ddti_thru(False)
                time.sleep(0.2)  # Give filter thread time to die and release port
        
        # Now that the port is hopefully free, reopen MIDI ports
        self._add_debug("Re-opening MIDI ports")
        self._cc.midi.reopen_ports()

    def deactivate(self):
        """Called when the screen is closed. Restores DDTi thru."""
        self._add_debug("Deactivating Sync...")
        if self._alsa_router and self._prev_ddti_thru is not None:
            self._add_debug("Restoring DDTi thru")
            self._alsa_router.set_ddti_thru(self._prev_ddti_thru)

    def _add_debug(self, msg: str):
        """Add a debug message with timestamp."""
        ts = time.strftime("%H:%M:%S", time.localtime())
        full_msg = f"{ts}: {msg}"
        self._debug_messages.append(full_msg)
        if len(self._debug_messages) > 5:  # Keep only last 5 messages
            self._debug_messages.pop(0)
        print(f"DDTiSync: {full_msg}")

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4,2), "DDTi Sync", fill=1)
        
        y = 14
        
        # Show DDTi input connection status
        ddti_port = self._cc.midi.get_ddti_in_port_name()
        if not ddti_port:
            draw.text((4, y), "No DDTi input ✗", fill=1)
            y += 10
        
        # One blank line after header
        y += 7
        
        # Instructions - only center the main message
        if self._done:
            # Center "Kit0 captured!"
            text1 = "Kit0 captured!"
            bbox1 = draw.textbbox((0, 0), text1)
            text1_w = bbox1[2] - bbox1[0]
            text1_x = (w - text1_w) // 2
            draw.text((text1_x, y), text1, fill=1)
            
            # Center "SELECT to continue"
            text2 = "SELECT to continue"
            bbox2 = draw.textbbox((0, 0), text2)
            text2_w = bbox2[2] - bbox2[0]
            text2_x = (w - text2_w) // 2
            draw.text((text2_x, y + 10), text2, fill=1)
        else:
            # Center "Trigger DDTi"
            text1 = "Trigger DDTi"
            bbox1 = draw.textbbox((0, 0), text1)
            text1_w = bbox1[2] - bbox1[0]
            text1_x = (w - text1_w) // 2
            draw.text((text1_x, y), text1, fill=1)
            
            # Center "SysEx Dump..."
            text2 = "SysEx Dump..."
            bbox2 = draw.textbbox((0, 0), text2)
            text2_w = bbox2[2] - bbox2[0]
            text2_x = (w - text2_w) // 2
            draw.text((text2_x, y + 10), text2, fill=1)
            
            text3 = "(Function & Value Up)"
            bbox3 = draw.textbbox((0, 0), text3)
            text3_w = bbox3[2] - bbox3[0]
            text3_x = (w - text3_w) // 2
            draw.text((text3_x, y + 20), text3, fill=1)

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:
            self.deactivate()  # Deactivate before popping
            return ScreenResult(pop=True)
        if key == BUTTON_SELECT and self._done:
            self.deactivate()  # Deactivate before popping
            return ScreenResult(pop=True)
        if key == BUTTON_UP and not self._done:
            # Debug: show port status
            ddti_port = self._cc.midi.get_ddti_in_port_name()
            self._add_debug(f"DDTi port: {ddti_port}")
            return ScreenResult(dirty=True)
        if key == BUTTON_DOWN and not self._done:
            # Debug: show current DDTi state
            if self._cc.ddti.have_kit0_bulk():
                notes = self._cc.ddti.extract_kit0_notes()
                self._add_debug(f"Kit0: {notes}")
            else:
                self._add_debug("No kit0 bulk")
            return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)

    def update(self) -> ScreenResult:
        # Use the new dedicated DDTi SysEx input method
        sysex_messages = self._cc.midi.iter_ddti_sysex()
        
        for msg in sysex_messages:
            self._sysex_count += 1
            data = bytes(msg.data)
            
            # Log exactly like the working script
            self._add_debug(f"SysEx len={len(data)} head={list(data[:8])}")
            
            # Try to ingest into DDTi
            try:
                before_bulk = self._cc.ddti.have_kit0_bulk()
                self._cc.ddti.ingest_sysex_frame(data)
                after_bulk = self._cc.ddti.have_kit0_bulk()
                
                if not before_bulk and after_bulk:
                    self._add_debug("*** Kit0 captured! ***")
                    
                    # Record the captured kit0 state as the initial undo point
                    notes = self._cc.ddti.extract_kit0_notes()
                    if notes:
                        # Store this as the "original" state for undo
                        self._cc.record_current_state_for_undo()
                        self._add_debug(f"Initial undo state: {notes}")
                
            except Exception as e:
                self._add_debug(f"Ingest error: {e}")
        
        # Check if we successfully captured kit0
        if not self._done and self._cc.ddti.have_kit0_bulk():
            notes = self._cc.ddti.extract_kit0_notes()
            if notes:
                self._last_notes = notes
                self._status = "Kit0 captured!"
                self._done = True
                self._add_debug(f"SUCCESS: {notes}")
                
                # Auto-exit after successful capture
                time.sleep(0.5)  # Brief pause to show success
                self.deactivate()  # Clean up ALSA routing
                return ScreenResult(pop=True, dirty=True)  # Auto-exit
        
        # Auto-refresh display every 0.5 seconds
        if (time.monotonic() - self._start_ts) > 0.5:
            self._start_ts = time.monotonic()
            return ScreenResult(dirty=True)
            
        return ScreenResult(dirty=False)

class ShutdownConfirmScreen(Screen):
    def __init__(self, neokey=None):
        self.neokey = neokey
        self.sel = 0  # 0 = Cancel, 1 = Shutdown
        
    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:  # Cancel
            return ScreenResult(pop=True)
        elif key == BUTTON_UP or key == BUTTON_DOWN:
            self.sel = 1 - self.sel  # Toggle between 0 and 1
            return ScreenResult(dirty=True)
        elif key == BUTTON_SELECT:
            if self.sel == 0:  # Cancel
                return ScreenResult(pop=True)
            else:  # Shutdown
                self._initiate_shutdown()
                return ScreenResult(pop=True)
        return ScreenResult(dirty=False)
    
    def _initiate_shutdown(self):
        """Trigger system shutdown."""
        print("User confirmed shutdown - initiating...")
        
        # Turn off NeoKey LEDs before shutdown
        if self.neokey:
            self.neokey.set_brightness(0.0)
            time.sleep(0.1)  # Brief pause to ensure it takes effect
        
        try:
            subprocess.run(["sudo", "shutdown", "-h", "now"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to initiate shutdown: {e}")
        except FileNotFoundError:
            print("Shutdown command not found - running in development environment?")
    
    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        
        # Title
        draw.text((4, 2), "Shutdown System?", fill=1)
        
        # Options
        y = 20
        options = ["Cancel", "Shutdown"]
        for i, option in enumerate(options):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + option, fill=1)
            y += 12
        
        # Instructions
        draw.text((4, h - 24), "UP/DOWN: Select", fill=1)
        draw.text((4, h - 12), "LEFT: Cancel, SELECT: Confirm", fill=1)

