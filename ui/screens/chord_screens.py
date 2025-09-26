"""Chord-related screens for capture functionality."""
import time
from .base_screens import Screen, ScreenResult, BaseCaptureScreen
from ..utils import BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT, note_to_name


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

    def render(self, draw, w: int, h: int) -> None:
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
        
    def _complete_learning(self):
        """Complete the learning process and save the mapping."""
        if len(self.learned_notes) == 4:
            # Store the learned mapping
            self.chord_capture.set_learned_mapping(self.learned_notes)
            self.completion_time = time.monotonic()
        
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
        
    def render(self, draw, w: int, h: int) -> None:
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
    
    def render(self, draw, w: int, h: int) -> None:
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

    def render(self, draw, w: int, h: int) -> None:
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