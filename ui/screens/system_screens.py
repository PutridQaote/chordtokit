"""System screens: Home, Shutdown, and DDTi (legacy)."""
import time
import subprocess
from .base_screens import Screen, ScreenResult
from ..utils import BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT


class HomeScreen(Screen):
    def __init__(self):
        self.items = [
            "Chord Capture",
            "Learn Mapping", 
            "MIDI Settings",
            "Utilities",
        ]
        self.sel = 0
        self._chord_capture = None  # Will be set by Menu
        self._cfg = None  # Will be set by Menu

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
                # Use local import to avoid circular dependency
                from .settings_screens import MidiSettingsScreen
                return ScreenResult(push=MidiSettingsScreen(), dirty=True)
            elif label == "Chord Capture":
                # Use local import to avoid circular dependency
                from .chord_screens import ChordCaptureMenuScreen
                return ScreenResult(push=ChordCaptureMenuScreen(), dirty=True)
            elif label == "Learn Mapping":
                # Use local import to avoid circular dependency
                from .chord_screens import LearnMappingScreen
                if self._chord_capture:
                    screen = LearnMappingScreen(self._chord_capture, config=self._cfg)
                    screen.activate()
                    return ScreenResult(push=screen, dirty=True)
                return ScreenResult(dirty=False)
            elif label == "Utilities":
                # Use local import to avoid circular dependency
                from .settings_screens import UtilitiesScreen
                return ScreenResult(push=UtilitiesScreen(), dirty=True)
            return ScreenResult(dirty=False)
        return ScreenResult(dirty=False)

    def render(self, draw, w: int, h: int) -> None:
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


class ShutdownConfirmScreen(Screen):
    def __init__(self, neokey=None):
        self.neokey = neokey
        self.shutting_down = False
        
    def on_key(self, key: int) -> ScreenResult:
        if self.shutting_down:
            return ScreenResult(dirty=False)
            
        if key == BUTTON_LEFT:  # Cancel
            return ScreenResult(pop=True)
        elif key == BUTTON_SELECT:  # Confirm shutdown
            self._shutdown()
            self.shutting_down = True
            return ScreenResult(dirty=True)  # Update to show "safe to unplug"
        return ScreenResult(dirty=False)

    def _shutdown(self):
        """Perform system shutdown."""
        try:
            print("Shutting down system...")
            
            # Turn off NeoKey LEDs first
            if self.neokey:
                self.neokey.brightness = 0.0  # Use property, not method
                print("NeoKey LEDs turned off")
            
            # Use threading to delay shutdown so we can show "safe to unplug" first
            import threading
            def delayed_shutdown():
                time.sleep(0.5)  # Give time for display to update
                try:
                    subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=True)
                except Exception as e:
                    print(f"Shutdown command failed: {e}")
            
            threading.Thread(target=delayed_shutdown, daemon=True).start()
            
        except Exception as e:
            print(f"Shutdown setup failed: {e}")

    def render(self, draw, w: int, h: int) -> None:
        draw.rectangle((0, 0, w-1, h-1), outline=1, fill=0)
        
        if self.shutting_down:
            # Center "safe to unplug" message
            text = "safe to unplug"
            bbox = draw.textbbox((0, 0), text)
            text_w = bbox[2] - bbox[0]
            text_x = (w - text_w) // 2
            text_y = h // 2 - 6
            draw.text((text_x, text_y), text, fill=1)
        else:
            # Center "Shutdown System?" message  
            text = "Shutdown System?"
            bbox = draw.textbbox((0, 0), text)
            text_w = bbox[2] - bbox[0]
            text_x = (w - text_w) // 2
            text_y = h // 2 - 6
            draw.text((text_x, text_y), text, fill=1)


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

    def render(self, draw, w: int, h: int) -> None:
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
                from ..utils import note_to_name
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