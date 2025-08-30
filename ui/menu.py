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
            ("4-Note Capture", self._start_4_note_capture),
            ("Single Note Capture", self._start_single_note_capture),
            ("LoNote OctDown", self._toggle_octave_down),
            ("Footswitch Mode", self._toggle_footswitch_mode),  # New option
            # Removed ("Back", None) - use back button instead
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
    
    def _toggle_octave_down(self):
        if self._chord_capture and self._cfg:
            current = self._cfg.get("octave_down_lowest", False)
            new_val = not current
            self._cfg.set("octave_down_lowest", new_val)
            self._cfg.save()
            self._chord_capture.set_octave_down_lowest(new_val)

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
        
        octave_down = self._cfg.get("octave_down_lowest", False) if self._cfg else False
        footswitch_mode = self._get_footswitch_mode_label()
        
        body = [
            "4-Note Capture",
            "Single Note Capture", 
            f"LoNote OctDown: {'On' if octave_down else 'Off'}",
            f"Footswitch: {footswitch_mode}",  # Show current footswitch mode
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
        """Start single note capture mode."""
        super().activate()
        self.captured_trigger_note = None
        self.captured_keyboard_note = None
        self.waiting_for_trigger = True
        
        # Open dedicated DDTi monitoring input
        import mido
        ddti_name = self.chord_capture.midi.get_out_port_name()
        print(f"Opening DDTi monitoring on: {ddti_name}")
        if ddti_name:
            try:
                self._ddti_in = mido.open_input(ddti_name)
                print("✓ DDTi monitoring active")
            except Exception as e:
                print(f"✗ DDTi monitoring failed: {e}")
                self._ddti_in = None
        
        # Temporarily disable keyboard thru
        if self.alsa_router:
            self._prev_kb_thru = self.alsa_router.get_keyboard_thru()
            if self._prev_kb_thru:
                print("Temporarily disabling keyboard thru")
                self.alsa_router.set_keyboard_thru(False)
                
        # Flush
        list(self.chord_capture.midi.iter_input())
        if self._ddti_in:
            list(self._ddti_in.iter_pending())
        
    def deactivate(self):
        """Stop single note capture mode."""
        # Close DDTi monitoring
        if self._ddti_in:
            try:
                self._ddti_in.close()
                print("✓ DDTi monitoring closed")
            except:
                pass
            self._ddti_in = None
        
        # Restore keyboard thru
        if self.alsa_router and self._prev_kb_thru is not None:
            if self._prev_kb_thru:
                print("Restoring keyboard thru")
                self.alsa_router.set_keyboard_thru(True)
            self._prev_kb_thru = None
        
        super().deactivate()

    def update(self) -> ScreenResult:
        if not self.active:
            return ScreenResult(dirty=False)

        # --- NEW: always allow DDTi hits to (re)select trigger until keyboard note is taken ---
        if self._ddti_in is not None and self.captured_keyboard_note is None:
            for msg in list(self._ddti_in.iter_pending()):
                if msg.type == 'note_on' and getattr(msg, 'velocity', 0) >= self._min_vel:
                    now = time.monotonic()
                    if now - self._last_ddti_hit_ts >= self._debounce_s:
                        self._last_ddti_hit_ts = now
                        self.captured_trigger_note = msg.note
                        self.waiting_for_trigger = False
                        print(f"Selected DDTi trigger: {note_to_name(msg.note)} ({msg.note}) [rollover enabled]")

        # If we have a trigger (possibly updated above) but no keyboard note yet, read keyboard
        if (self.captured_trigger_note is not None) and (self.captured_keyboard_note is None):
            for msg in list(self.chord_capture.midi.iter_input()):
                if msg.type == 'note_on' and getattr(msg, 'velocity', 0) > 0:
                    self.captured_keyboard_note = msg.note
                    print(f"Captured keyboard note: {note_to_name(msg.note)} ({msg.note})")
                    self._send_single_note_change()
                    self.completion_time = time.monotonic()
                    break

        return super().update()
    
    def _send_single_note_change(self):
        """Send SysEx to change just one trigger's note."""
        if self.captured_trigger_note is None or self.captured_keyboard_note is None:
            return
            
        try:
            from features.ddti import DDTi
            ddti = DDTi()
            
            # Get the current DDTi configuration by reading the last sent chord
            # We need to track the actual DDTi state, not use a hardcoded fallback
            if hasattr(self.chord_capture, "last_sent_chord"):
                current = list(self.chord_capture.last_sent_chord)
                print(f"Using last sent chord: {current}")
            else:
                # If we don't have the last chord, we can't safely do single-note changes
                print("ERROR: No last chord available - cannot determine current DDTi state")
                print("Please capture a 4-note chord first to establish DDTi state")
                return

            # Find the index to replace by matching the trigger note
            try:
                idx = current.index(self.captured_trigger_note)
                print(f"Found trigger note {self.captured_trigger_note} at index {idx}")
            except ValueError:
                print(f"ERROR: Trigger note {self.captured_trigger_note} not found in current chord {current}")
                print("DDTi state may have changed - please capture a 4-note chord to resync")
                return

            old = current[idx]
            current[idx] = self.captured_keyboard_note
            print(f"Changing trigger {idx} from {note_to_name(old)} ({old}) to {note_to_name(self.captured_keyboard_note)} ({self.captured_keyboard_note})")
            print(f"Full chord change: {[old if i != idx else self.captured_keyboard_note for i, old in enumerate(current)]} -> {current}")

            # Build + send
            msg = ddti.build_sysex(current)
            sent = self.chord_capture.midi.send(msg)
            if sent:
                print(f"Sent single-note SysEx: {len(msg.data)} bytes")
                # Update the chord_capture's last sent chord
                self.chord_capture.last_sent_chord = current[:]
            else:
                print("Failed to send SysEx (MIDI out not open?)")
        except Exception as e:
            print(f"single-note SysEx error: {e}")
    
    def on_key(self, key: int) -> ScreenResult:
        """Handle back button to exit single-note capture."""
        if key == BUTTON_LEFT:  # Back button - abort capture
            self.deactivate()
            return ScreenResult(pop=True)
        elif key == BUTTON_UP:  # Increase spiral turns
            self.turns = min(50, self.turns + 1)
            self._save_turns_to_config()
            print(f"Spiral turns increased to {self.turns}")
            return ScreenResult(dirty=True)
        elif key == BUTTON_DOWN:  # Decrease spiral turns
            self.turns = max(1, self.turns - 1)
            self._save_turns_to_config()
            print(f"Spiral turns decreased to {self.turns}")
            return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)
    
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

class VariableTriggerCaptureScreen(BaseCaptureScreen):
    def __init__(self, chord_capture, config=None):
        super().__init__(chord_capture, turns=15, 
                        config_key="spiral_turns_variable", config=config)
        
        # Variable-trigger state
        self.captured_triggers: List[int] = []  # DDTi notes that were hit
        self.captured_keyboard_notes: List[int] = []  # Keyboard notes to assign
        self.trigger_capture_phase = True  # True = capturing triggers, False = capturing keyboard
        
    def _send_variable_trigger_change(self):
        """Send SysEx for variable number of triggers."""
        if not self.captured_triggers or not self.captured_keyboard_notes:
            return
        
        if len(self.captured_triggers) != len(self.captured_keyboard_notes):
            print("Error: Trigger and keyboard note counts don't match")
            return
            
        try:
            # Use the new variable-trigger method
            sysex_msg = self.chord_capture.ddti.build_trigger_change_sysex(
                self.captured_triggers, self.captured_keyboard_notes
            )
            sent = self.chord_capture.midi.send(sysex_msg)
            
            if sent:
                print(f"Updated {len(self.captured_triggers)} triggers with variable SysEx")
                for trigger, note in zip(self.captured_triggers, self.captured_keyboard_notes):
                    print(f"  Trigger {note_to_name(trigger)} -> {note_to_name(note)}")
            
        except Exception as e:
            print(f"Variable-trigger SysEx error: {e}")

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
        self._ddti_in = None
        self._sysex_count = 0  # Track received SysEx messages

    def _activate_monitoring(self):
        """Start monitoring DDTi port for incoming SysEx."""
        import mido
        ddti_name = self._cc.midi.get_out_port_name()  # Use same port as output
        print(f"DDTi Sync: Opening monitoring on: {ddti_name}")
        if ddti_name:
            try:
                self._ddti_in = mido.open_input(ddti_name)
                print("✓ DDTi sync monitoring active")
                return True
            except Exception as e:
                print(f"✗ DDTi sync monitoring failed: {e}")
                self._ddti_in = None
                return False
        return False

    def _deactivate_monitoring(self):
        """Stop monitoring DDTi port."""
        if self._ddti_in:
            try:
                self._ddti_in.close()
                print("✓ DDTi sync monitoring closed")
            except:
                pass
            self._ddti_in = None

    def render(self, draw: ImageDraw.ImageDraw, w: int, h: int) -> None:
        draw.rectangle((0,0,w-1,h-1), outline=1, fill=0)
        draw.text((4,2), "DDTi Sync", fill=1)
        
        # Show status and SysEx count
        if self._sysex_count > 0:
            status_text = f"Got {self._sysex_count} SysEx"
        else:
            status_text = self._status[:18]
        draw.text((4,14), status_text, fill=1)
        
        if self._last_notes:
            draw.text((4,26), "Notes:"+"/".join(str(n) for n in self._last_notes), fill=1)
        
        age = self._cc.ddti.kit0_age_seconds()
        if age is not None:
            draw.text((4,38), f"Age:{int(age)}s", fill=1)
            
        if self._done:
            draw.text((4,50), "OK - Back", fill=1)
        else:
            draw.text((4,50), "Press DUMP", fill=1)

    def on_key(self, key: int) -> ScreenResult:
        if key == BUTTON_LEFT:
            self._deactivate_monitoring()
            return ScreenResult(pop=True)
        if key == BUTTON_SELECT and self._done:
            self._deactivate_monitoring()
            return ScreenResult(pop=True)
        if key == BUTTON_UP and not self._done:
            # Manual trigger to activate monitoring if not already active
            if not self._ddti_in:
                if self._activate_monitoring():
                    self._status = "Monitoring active"
                else:
                    self._status = "Monitor failed"
                return ScreenResult(dirty=True)
        return ScreenResult(dirty=False)

    def update(self) -> ScreenResult:
        # Start monitoring on first update if not already started
        if not self._ddti_in and not self._done:
            self._activate_monitoring()
            
        # Process incoming SysEx messages
        if self._ddti_in:
            for msg in list(self._ddti_in.iter_pending()):
                if msg.type == 'sysex':
                    self._sysex_count += 1
                    print(f"DDTi Sync: Received SysEx len={len(msg.data)} data[0:8]={list(msg.data[:8])}")
                    try:
                        self._cc.ddti.ingest_sysex_frame(bytes(msg.data))
                    except Exception as e:
                        print(f"DDTi Sync: Ingest error: {e}")
        
        # Check if we successfully captured kit0
        if not self._done and self._cc.ddti.have_kit0_bulk():
            notes = self._cc.ddti.extract_kit0_notes()
            if notes:
                self._last_notes = notes
                self._status = "Kit0 captured!"
                self._done = True
                print(f"DDTi Sync: Successfully captured kit0 notes: {notes}")
                return ScreenResult(dirty=True)
        
        # Update status if we're receiving SysEx but no kit0 yet
        if self._sysex_count > 0 and not self._done:
            self._status = f"Processing {self._sysex_count} msgs"
            
        # Keep redrawing every ~0.5s to show updates
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
            screen.attach(self.chord_capture, self.cfg, self.alsa_router)  # Pass router
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

