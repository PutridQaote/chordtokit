"""Minimal runnable app to display Home + MIDI Settings on the OLED
and navigate with the NeoKey (left/up/down/select).
"""
import time
from hw.neokey import NeoKey
from hw.oled import Oled
from hw.midi_io import Midi
from ui.menu import Menu

def main():
    nk = NeoKey()
    oled = Oled()
    midi = Midi()
    menu = Menu(midi_adapter=midi)

    # Initial render
    img, draw = oled.begin_frame()
    menu.render_into(draw, oled.width, oled.height)
    oled.show(img)
    menu.dirty = False

    try:
        while True:
            events = nk.read_events()
            if events:
                menu.handle_events(events)
            if menu.dirty:
                img, draw = oled.begin_frame()
                menu.render_into(draw, oled.width, oled.height)
                oled.show(img)
                menu.dirty = False
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        # Optional: clear display or LEDs here if desired
        pass

if __name__ == "__main__":
    main()