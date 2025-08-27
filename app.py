# app.py
import time

from config import Config
from constants import FOOTSWITCH_ACTIVE_LOW
from hw.neokey import NeoKey
from hw.oled import Oled
from hw.midi_io import Midi
from hw.footswitch import Footswitch
from ui.menu import Menu, ChordCaptureScreen
from features.chord_capture import ChordCapture

import subprocess

def notify_ready():
    """function to detect when initial system loading has finished, facilitating startup boot screen."""
    try:
        subprocess.run(["/usr/bin/systemd-notify", "--ready"], check=False)
    except Exception:
        pass


def main():

    notify_ready()

    cfg = Config().load()

    # Get LED settings from config
    led_enabled = bool(cfg.get("led_backlights_on", True))
    led_color = tuple(cfg.get("led_backlight_color", [84, 255, 61]))
    
    nk = NeoKey(
        brightness=float(cfg.get("neokey_brightness", 0.5)),
        backlight_enabled=led_enabled,
        backlight_color=led_color
    )
    oled = Oled()

    midi = Midi(cfg.as_dict())
    midi.open_ports()
    
    # Midi thru routing has been configured to:
    # 1. Never send raw input to the DDTi (main output)
    # 2. Only send processed chord messages to DDTi
    # 3. Filter out any "Midi Through" virtual ports to prevent feedback
    # 4. Route raw MIDI to all other physical devices

    foot = Footswitch(active_low=bool(cfg.get("footswitch_active_low", FOOTSWITCH_ACTIVE_LOW)))

    allow_dupes = bool(cfg.get("allow_duplicate_notes", False))
    octave_down = bool(cfg.get("octave_down_lowest", False))
    chord_capture = ChordCapture(midi, allow_duplicates=allow_dupes, octave_down_lowest=octave_down)

    # Pass neokey to menu for LED control
    menu = Menu(midi_adapter=midi, config=cfg, chord_capture=chord_capture, neokey=nk)

    # Set chord_capture reference for the home screen
    if hasattr(menu._stack[0], '_chord_capture'):
        menu._stack[0]._chord_capture = chord_capture

    img, draw = oled.begin_frame()
    menu.render_into(draw, oled.width, oled.height)
    oled.show(img)
    menu.dirty = False

    try:
        while True:
            # Read events more frequently - check multiple times per loop
            for _ in range(5):  # Check for events up to 5 times per main loop iteration
                events = nk.read_events()
                if events:
                    menu.handle_events(events)
                    # Process screen updates immediately after events
                    screen_changed = menu.update()
                    if menu.dirty or screen_changed:
                        img, draw = oled.begin_frame()
                        menu.render_into(draw, oled.width, oled.height)
                        oled.show(img)
                        menu.dirty = False
                else:
                    break  # No more events, exit the inner loop

            # Handle footswitch
            if foot.pressed_edge():
                top_screen = menu._top()
                if isinstance(top_screen, ChordCaptureScreen):
                    # If already in capture mode, abort it
                    print("Footswitch: Aborting chord capture")
                    top_screen.deactivate()
                    menu.pop()
                else:
                    # Start chord capture - ensure we start fresh
                    print("Footswitch: Starting chord capture")
                    capture_screen = ChordCaptureScreen(chord_capture)
                    capture_screen.activate()
                    menu.push(capture_screen)

            # Check for long press and other screen updates
            screen_changed = menu.update()
            if menu.dirty or screen_changed:
                img, draw = oled.begin_frame()
                menu.render_into(draw, oled.width, oled.height)
                oled.show(img)
                menu.dirty = False

            time.sleep(0.002)  # Slightly increased sleep to balance CPU usage
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
