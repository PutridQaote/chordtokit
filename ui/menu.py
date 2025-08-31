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
            ("Variable Trigger Capture", self._start_variable_trigger_capture),
            ("Single Note Capture", self._start_single_note_capture),
            ("Footswitch Mode", self._toggle_footswitch_mode),
            # Removed "Undo Mapping" - moved to utilities
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
            print("Menu: Starting single-note capture")
            screen = SingleNoteCaptureScreen(self._chord_capture, config=self._cfg)  # Pass config
            if self._alsa_router:
                screen.set_alsa_router(self._alsa_router)
            screen.activate()
            return ScreenResult(push=screen, dirty=True)
        return ScreenResult(dirty=False)
    
    def _start_variable_trigger_capture(self):
        """Start the new variable-trigger capture mode."""
        if self._chord_capture:
            print("Menu: Starting variable-trigger capture")
            screen = VariableTriggerCaptureScreen(self._chord_capture, config=self._cfg)
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
            "Variable Trigger Capture",
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
        """Start single note capture mode (no extra port, no routing changes)."""
        super().activate()
        # Reset state
        self.captured_trigger_note = None
        self.captured_keyboard_note = None
        self.waiting_for_trigger = True
        self._activation_guard_until = time.monotonic() + 0.04  # 40ms ignore window
        # Drain any stale MIDI so we start clean
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"SingleNote: Activated (drained {drained} stale msgs)")
        print("SingleNote: Using shared DDTi + dedicated Midi ddti input")

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
        ddti = self.chord_capture.ddti

        # Ingest / capture only after guard window
        capture_enabled = now >= getattr(self, "_activation_guard_until", 0)

        for msg in midi.iter_ddti_all():
            if msg.type == 'sysex':
                try:
                    ddti.ingest_sysex_frame(bytes(msg.data))
                except Exception as e:
                    print(f"SingleNote: Sysex ingest error: {e}")
            elif (capture_enabled and
                  msg.type == 'note_on' and msg.velocity > 0 and
                  self.captured_keyboard_note is None):
                self.captured_trigger_note = msg.note
                self.waiting_for_trigger = False
                print(f"SingleNote: Selected trigger note {msg.note}")

        if (capture_enabled and
            self.captured_trigger_note is not None and
            self.captured_keyboard_note is None):
            for msg in midi.iter_input():
                if msg.type == 'note_on' and getattr(msg, 'velocity', 0) > 0:
                    self.captured_keyboard_note = msg.note
                    print(f"SingleNote: Captured keyboard note {msg.note}")
                    self._send_single_note_change()
                    # Drain immediately after sending so no cascade into next screen
                    midi.drain_all_inputs()
                    self.completion_time = time.monotonic()
                    break

        return super().update()

    def _send_single_note_change(self):
        """Send SysEx patch for kit0 replacing all occurrences of trigger note (with undo)."""
        if self.captured_trigger_note is None or self.captured_keyboard_note is None:
            return
        ddti = self.chord_capture.ddti

        if not ddti.have_kit0_bulk():
            print("SingleNote: No kit0 bulk cached. Run DDTi Sync first.")
            return

        old_note = self.captured_trigger_note
        new_note = self.captured_keyboard_note

        # Capture pre-mutation bulk snapshot for undo
        pre_bulk = ddti.get_kit0_bulk_frame()
        msg = ddti.build_kit0_single_note_patch(old_note, new_note)
        if not msg:
            print("SingleNote: Patch build failed (old note not found or no change).")
            return

        # Only push undo snapshot if change actually occurred
        if pre_bulk:
            self.chord_capture.record_kit0_bulk_for_undo(pre_bulk)

        sent = self.chord_capture.midi.send(msg)
        if sent:
            print(f"SingleNote: Sent kit0 single-note patch ({len(msg.data)} bytes)")
        else:
            print("SingleNote: MIDI send failed")

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
        ddti = self.chord_capture.ddti
        if ddti.have_kit0_bulk():
            notes = ddti.extract_kit0_notes()
            # if notes:
            #     draw.text((4, 4), "Kit0:" + "/".join(str(n) for n in notes), fill=1)
        else:
            draw.text((4, 4), "Need DDTi Sync", fill=1)

        if self.captured_trigger_note is not None:
            draw.text(self.trigger_position,
                      f"{note_to_name(self.captured_trigger_note)}", fill=1)
        if self.captured_keyboard_note is not None:
            draw.text(self.keyboard_position,
                      f"{note_to_name(self.captured_keyboard_note)}", fill=1)
        if not self.completion_time:
            self._draw_listen_text(draw, w, h)

class VariableTriggerCaptureScreen(BaseCaptureScreen):
    def __init__(self, chord_capture, config=None):
        super().__init__(chord_capture, turns=15, 
                        config_key="spiral_turns_variable", config=config)
        
        # Variable-trigger state - TWO DISTINCT PHASES
        self.captured_triggers: List[int] = []  # DDTi notes that were hit
        self.captured_keyboard_notes: List[int] = []  # Keyboard notes to assign
        self.trigger_capture_phase = True  # True = capturing triggers, False = capturing keyboard
        
        # ALSA router reference (same as SingleNoteCaptureScreen)
        self.alsa_router = None
        self._last_ddti_hit_ts = 0.0
        self._debounce_s = 0.12
        self._min_vel = 8

    def set_alsa_router(self, router):
        """Set the ALSA router reference."""
        self.alsa_router = router

    def activate(self):
        """Start variable trigger capture mode."""
        super().activate()
        self.captured_triggers.clear()
        self.captured_keyboard_notes.clear()
        self.trigger_capture_phase = True
        self._activation_guard_until = time.monotonic() + 0.04
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"VariableTrigger: Activated (drained {drained} stale msgs)")

    def deactivate(self):
        drained = self.chord_capture.midi.drain_all_inputs()
        print(f"VariableTrigger: Deactivated (drained {drained} msgs on exit)")
        super().deactivate()

    def update(self) -> ScreenResult:
        if not self.active:
            return ScreenResult(dirty=False)
        capture_enabled = time.monotonic() >= getattr(self, "_activation_guard_until", 0)
        midi = self.chord_capture.midi
        ddti = self.chord_capture.ddti
        if self.trigger_capture_phase:
            for msg in midi.iter_ddti_all():
                if msg.type == 'sysex':
                    try:
                        ddti.ingest_sysex_frame(bytes(msg.data))
                    except Exception as e:
                        print(f"VariableTrigger: SysEx ingest error: {e}")
                elif (capture_enabled and msg.type == 'note_on' and msg.velocity >= self._min_vel):
                    now = time.monotonic()
                    if now - self._last_ddti_hit_ts >= self._debounce_s:
                        self._last_ddti_hit_ts = now
                        if msg.note not in self.captured_triggers:
                            self.captured_triggers.append(msg.note)
                            print(f"VariableTrigger: Added trigger {note_to_name(msg.note)} ({msg.note})")
                            if len(self.captured_triggers) >= 4:
                                print("VariableTrigger: Max triggers reached - advance to keyboard phase")
                                self.trigger_capture_phase = False
        else:
            if capture_enabled:
                needed_keyboard_notes = len(self.captured_triggers) - len(self.captured_keyboard_notes)
                if needed_keyboard_notes > 0:
                    for msg in midi.iter_input():
                        if msg.type == 'note_on' and msg.velocity > 0:
                            self.captured_keyboard_notes.append(msg.note)
                            print(f"VariableTrigger: Added keyboard note {note_to_name(msg.note)} ({msg.note})")
                            if len(self.captured_keyboard_notes) >= len(self.captured_triggers):
                                print("VariableTrigger: All notes captured - sending SysEx")
                                self._send_variable_trigger_change()
                                midi.drain_all_inputs()
                                self.completion_time = time.monotonic()
                                break
        return super().update()

    def _send_variable_trigger_change(self):
        """Send SysEx for variable number of triggers."""
        if not self.captured_triggers or not self.captured_keyboard_notes:
            print("VariableTrigger: No triggers or keyboard notes to send")
            return
        if len(self.captured_triggers) != len(self.captured_keyboard_notes):
            print(f"VariableTrigger: Mismatch - {len(self.captured_triggers)} triggers vs {len(self.captured_keyboard_notes)} notes")
            return
        # Need current mapping state
        if self.chord_capture.ddti.get_current_state() is None:
            print("VariableTrigger: Current DDTi state unknown (send a full chord first).")
            return
        # Record state for undo
        self.chord_capture.record_current_state_for_undo()
        try:
            # Build single partial SysEx covering all trigger changes
            msg = self.chord_capture.ddti.build_trigger_change_sysex(
                self.captured_triggers, self.captured_keyboard_notes
            )
            ok = self.chord_capture.midi.send(msg)
            if ok:
                print(f"VariableTrigger: Sent partial update for {len(self.captured_triggers)} triggers")
            else:
                print("VariableTrigger: MIDI send failed")
        except Exception as e:
            print(f"VariableTrigger: SysEx error: {e}")

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
        elif key == BUTTON_SELECT and self.trigger_capture_phase and self.captured_triggers:
            # Allow manual advance to keyboard phase
            print("VariableTrigger: Manual advance to keyboard phase")
            self.trigger_capture_phase = False
            return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        if not self._render_base_frame(draw, w, h):
            return

        ddti = self.chord_capture.ddti
        if not ddti.have_kit0_bulk():
            draw.text((4, 4), "Need DDTi Sync", fill=1)

        # Calculate vertical positions for up to 4 notes
        # Screen height is ~64, with border we have ~60 usable pixels
        # Top margin: 10, bottom margin: 10, leaves 44 pixels for notes
        available_height = h - 20  # 10px top + 10px bottom margins
        top_y = 10

        # Display captured DDTi triggers on the RIGHT side
        if self.captured_triggers:
            max_triggers = min(len(self.captured_triggers), 4)  # Max 4 triggers
            if max_triggers == 1:
                trigger_positions = [top_y + available_height // 2]  # Center
            else:
                # Distribute evenly from top to bottom
                step = available_height // (max_triggers - 1) if max_triggers > 1 else 0
                trigger_positions = [top_y + i * step for i in range(max_triggers)]

            for i, trigger_note in enumerate(self.captured_triggers[:4]):
                y_pos = trigger_positions[i]
                note_text = note_to_name(trigger_note)
                # Right-aligned: screen width (128) - text width - margin
                bbox = draw.textbbox((0, 0), note_text)
                text_w = bbox[2] - bbox[0]
                x_pos = w - text_w - 4
                draw.text((x_pos, y_pos), note_text, fill=1)

        # Display captured keyboard notes on the LEFT side
        if self.captured_keyboard_notes:
            max_keyboard = min(len(self.captured_keyboard_notes), 4)  # Max 4 notes
            if max_keyboard == 1:
                keyboard_positions = [top_y + available_height // 2]  # Center
            else:
                # Distribute evenly from top to bottom
                step = available_height // (max_keyboard - 1) if max_keyboard > 1 else 0
                keyboard_positions = [top_y + i * step for i in range(max_keyboard)]

            for i, keyboard_note in enumerate(self.captured_keyboard_notes[:4]):
                y_pos = keyboard_positions[i]
                note_text = note_to_name(keyboard_note)
                draw.text((4, y_pos), note_text, fill=1)

        # Show phase-specific instructions
        if not self.completion_time:
            if self.trigger_capture_phase:
                if not self.captured_triggers:
                    self._draw_listen_text(draw, w, h)
                else:
                    # Show "SELECT to continue" if we have triggers
                    instruction = "SELECT for keyboard"
                    bbox = draw.textbbox((0, 0), instruction)
                    text_w = bbox[2] - bbox[0]
                    text_x = (w - text_w) // 2
                    draw.text((text_x, h - 15), instruction, fill=1)
            else:
                # Keyboard capture phase
                needed = len(self.captured_triggers) - len(self.captured_keyboard_notes)
                if needed > 0:
                    instruction = f"Play {needed} more key{'s' if needed > 1 else ''}"
                    bbox = draw.textbbox((0, 0), instruction)
                    text_w = bbox[2] - bbox[0]
                    text_x = (w - text_w) // 2
                    draw.text((text_x, h - 15), instruction, fill=1)

class UtilitiesScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Allow Duplicate Notes", self._toggle_duplicates),
            ("LoNote OctDown", self._toggle_octave_down),
            ("Undo Mapping", self._undo_mapping),  # MOVED HERE
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
                result = action()
                # Handle case where action returns a ScreenResult (like _undo_mapping)
                if isinstance(result, ScreenResult):
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
            "Undo Mapping",  # NEW
            f"LEDs: {led_brightness}",
            "Back",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12

class DDTiSyncScreen(Screen):
    """
    Screen that waits for a manual DDTi bank dump to ingest kit0.
    User triggers dump on the hardware; we watch incoming MIDI for kit0 bulk frame.
    """
    def __init__(self, chord_capture):
        self._cc = chord_capture
        self._done = False
        self._status = "Waiting for dump..."
        self._last_notes = None
        self._start_ts = time.monotonic()
        self._sysex_count = 0
        self._debug_messages = []
        # NEW: Add state for managing ALSA router
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
            if self._prev_ddti_thru:
                self._add_debug("Restoring DDTi thru")
                self._alsa_router.set_ddti_thru(True)
            self._prev_ddti_thru = None
        
        # Reopen ports again to let the filter grab the port back
        # and restore the main app's normal MIDI state.
        self._cc.midi.reopen_ports()

    def _add_debug(self, msg: str):
        """Add a debug message with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        debug_msg = f"{timestamp}: {msg}"
        print(f"DDTi Sync: {debug_msg}")
        self._debug_messages.append(debug_msg)
        # Keep only last 5 messages
        if len(self._debug_messages) > 5:
            self._debug_messages.pop(0)

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4,2), "DDTi Sync", fill=1)
        
        y = 14
        
        # Show DDTi input connection status
        ddti_port = self._cc.midi.get_ddti_in_port_name()
        if not ddti_port:
            draw.text((4, y), "No DDTi input ✗", fill=1)
            y += 10
        
        # Show SysEx count only
        # draw.text((4, y), f"SysEx: {self._sysex_count}", fill=1)
                
        # One blank line after header
        y += 6
        
        # Instructions - only center the main message
        if self._done:
            # Center "Kit0 captured!"
            text1 = "Kit0 captured!"
            bbox1 = draw.textbbox((0, 0), text1)
            text1_w = bbox1[2] - bbox1[0]
            text1_x = (w - text1_w) // 2
            draw.text((text1_x, y), text1, fill=1)
            
            # Center "Auto-exiting..."
            text2 = "Auto-exiting..."
            bbox2 = draw.textbbox((0, 0), text2)
            text2_w = bbox2[2] - bbox2[0]
            text2_x = (w - text2_w) // 2
            draw.text((text2_x, y + 12), text2, fill=1)
        else:
            # Center "Waiting for DDTi"
            text1 = "Waiting for DDTi"
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
            draw.text((text3_x, y + 26), text3, fill=1)

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
                    
                    # NEW: Record the captured kit0 state as the initial undo point
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
            "DDTi Sync",        # NEW
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
            elif label == "DDTi Sync":
                return ScreenResult(push=DDTiSyncScreen(self._chord_capture), dirty=True)
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
            screen.attach(self.chord_capture, self.cfg, self.alsa_router)
        elif isinstance(screen, DDTiSyncScreen): # NEW
            screen.attach(self.chord_capture, self.cfg, self.alsa_router)
        elif isinstance(screen, HomeScreen) and self.chord_capture:
            screen._chord_capture = self.chord_capture
        
        # NEW: Call activate if the screen has it
        if hasattr(screen, 'activate'):
            screen.activate()

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
        
        top = self._top()
        
        # OLD:
        # if isinstance(top, (ChordCaptureScreen, SingleNoteCaptureScreen)):
        #     result = top.update()
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

    # --- Rendering helpers ---
    def render_into(self, draw: ImageDraw.ImageDraw, w: int, h: int):
        self._top().render(draw, w, h)

