"""Settings-related screens: MIDI Settings and Utilities."""
from .base_screens import Screen, ScreenResult
from ..utils import BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT


class MidiSettingsScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Chord In", self._cycle_in),
            ("Chord Out", self._cycle_out),
            ("Keyboard Thru", self._toggle_keyboard_thru),
            ("DDTi Thru", self._toggle_ddti_thru),
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

    def render(self, draw, w: int, h: int) -> None:
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
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12


class UtilitiesScreen(Screen):
    def __init__(self):
        self.rows = [
            ("Allow Duplicate Notes", self._toggle_duplicates),
            ("Undo Mapping", self._undo_mapping),
            ("LED Brightness", self._cycle_led_brightness),
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

    def _undo_mapping(self):
        """Undo the most recent mapping change."""
        if self._chord_capture:
            ok = self._chord_capture.undo_last_mapping()
            if not ok:
                print("Utilities: Undo failed or no history")
        return ScreenResult(dirty=True)

    def _cycle_led_brightness(self):
        """Cycle through LED brightness levels: Off, 25%, 50%, 75%, 100%"""
        if not self._cfg or not self._neokey:
            return ScreenResult(dirty=False)
        
        current = float(self._cfg.get("led_backlight_brightness", 1.0))
        
        # Cycle through brightness levels: 0.0, 0.25, 0.5, 0.75, 1.0
        if current <= 0.0:
            new_brightness = 0.25
        elif current <= 0.25:
            new_brightness = 0.5
        elif current <= 0.5:
            new_brightness = 0.75
        elif current <= 0.75:
            new_brightness = 1.0
        else:
            new_brightness = 0.0  # Back to off
            
        # Update config
        self._cfg.set("led_backlight_brightness", new_brightness)
        self._cfg.save()
        
        # Apply to hardware - use the correct method calls
        if new_brightness == 0.0:
            self._neokey.set_backlight_enabled(False)
        else:
            self._neokey.set_backlight_brightness(new_brightness)
            self._neokey.set_backlight_enabled(True)
            # Re-apply the current backlight color to make the brightness change visible
            current_color = tuple(self._cfg.get("led_backlight_color", [84, 255, 61]))
            self._neokey.set_backlight_color(current_color)
        
        return ScreenResult(dirty=True)

    def _get_led_brightness_label(self) -> str:
        """Get the current LED brightness as a label."""
        if not self._cfg:
            return "100%"
        brightness = float(self._cfg.get("led_backlight_brightness", 1.0))
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
        draw.text((4, 2), "Utilities", fill=1)
        
        allow_dupes = self._cfg.get("allow_duplicate_notes", False) if self._cfg else False
        led_brightness = self._get_led_brightness_label()
        
        body = [
            f"Duplicates: {'On' if allow_dupes else 'Off'}",
            "Undo Mapping",
            f"LEDs: {led_brightness}",
        ]
        y = 14
        for i, line in enumerate(body):
            prefix = "> " if i == self.sel else "  "
            draw.text((4, y), prefix + line, fill=1)
            y += 12