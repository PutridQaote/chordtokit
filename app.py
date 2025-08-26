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


def main():
    cfg = Config().load()

    nk = NeoKey(brightness=float(cfg.get("neokey_brightness", 0.5)))
    oled = Oled()
    midi = Midi(cfg.as_dict()); midi.open_ports()
    foot = Footswitch(active_low=bool(cfg.get("footswitch_active_low", FOOTSWITCH_ACTIVE_LOW)))

    allow_dupes = bool(cfg.get("allow_duplicate_notes", False))
    chord_capture = ChordCapture(midi, allow_duplicates=allow_dupes)

    menu = Menu(midi_adapter=midi, config=cfg, chord_capture=chord_capture)

    # Set chord_capture reference for the home screen
    if hasattr(menu._stack[0], '_chord_capture'):
        menu._stack[0]._chord_capture = chord_capture

    img, draw = oled.begin_frame()
    menu.render_into(draw, oled.width, oled.height)
    oled.show(img)
    menu.dirty = False

    try:
        while True:
            events = nk.read_events()
            if events:
                menu.handle_events(events)

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

            # Update current screen (important for ChordCaptureScreen)
            screen_changed = menu.update()
            
            if menu.dirty or screen_changed:
                img, draw = oled.begin_frame()
                menu.render_into(draw, oled.width, oled.height)
                oled.show(img)
                menu.dirty = False

            time.sleep(0.001)  # Much faster polling - 1ms instead of 10ms
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
