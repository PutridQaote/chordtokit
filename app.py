# app.py
import time

from config import Config
from constants import FOOTSWITCH_ACTIVE_LOW
from hw.neokey import NeoKey
from hw.oled import Oled
from hw.midi_io import Midi
from hw.footswitch import Footswitch
from ui.menu import Menu, ChordCaptureScreen, SingleNoteCaptureScreen
from features.chord_capture import ChordCapture

import subprocess
from hw.alsa_router import AlsaRouter

def main():

    cfg = Config().load()

    # Get LED settings from config - now includes brightness
    led_enabled = bool(cfg.get("led_backlights_on", True))
    led_color = tuple(cfg.get("led_backlight_color", [84, 255, 61]))
    led_brightness = float(cfg.get("led_backlight_brightness", 1.0))
    
    nk = NeoKey(
        brightness=led_brightness,  # Use the brightness setting
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

    # Initialize ALSA router for hardware-level MIDI routing
    alsa_router = AlsaRouter()
    
    # Debug: see what ports are discovered
    alsa_router.debug_discovered_ports()
    
    # Load settings and apply initial routing
    alsa_router.set_keyboard_thru(bool(cfg.get("alsa_keyboard_thru", False)))
    alsa_router.set_ddti_thru(bool(cfg.get("alsa_ddti_thru", True)))
    
    # Wait a moment for ports to settle, then establish routes
    time.sleep(1)
    alsa_router.ensure_baseline_routes()

    # Pass router to menu
    menu = Menu(midi_adapter=midi, config=cfg, chord_capture=chord_capture, 
               neokey=nk, alsa_router=alsa_router)

    # Set chord_capture reference for the home screen
    if hasattr(menu._stack[0], '_chord_capture'):
        menu._stack[0]._chord_capture = chord_capture

    img, draw = oled.begin_frame()
    menu.render_into(draw, oled.width, oled.height)
    oled.show(img)
    menu.dirty = False

    # Add periodic reconciliation (every 5 seconds)
    last_reconcile = time.monotonic()
    
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
                    # Check footswitch mode setting
                    footswitch_mode = cfg.get("footswitch_capture_mode", "all")
                    
                    if footswitch_mode == "single":
                        # Start single-note capture
                        print("Footswitch: Starting single-note capture")
                        capture_screen = SingleNoteCaptureScreen(chord_capture, config=cfg)  # Pass config
                        if alsa_router:
                            capture_screen.set_alsa_router(alsa_router)
                        capture_screen.activate()
                        menu.push(capture_screen)
                    else:
                        # Start 4-note capture (default)
                        print("Footswitch: Starting 4-note chord capture")
                        capture_screen = ChordCaptureScreen(chord_capture, config=cfg)  # Pass config
                        capture_screen.activate()
                        menu.push(capture_screen)

            # Check for long press and other screen updates
            screen_changed = menu.update()
            if menu.dirty or screen_changed:
                img, draw = oled.begin_frame()
                menu.render_into(draw, oled.width, oled.height)
                oled.show(img)
                menu.dirty = False

            # Periodic route reconciliation for device hotplug
            now = time.monotonic()
            if now - last_reconcile > 5.0:  # Every 5 seconds
                alsa_router._reconcile_routes()
                last_reconcile = now

            time.sleep(0.002)  # Slightly increased sleep to balance CPU usage
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up ALSA connections on exit
        alsa_router.cleanup_managed_connections()

if __name__ == "__main__":
    main()
