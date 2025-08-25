"""Minimal runnable app to display Home + MIDI Settings on the OLED
and navigate with the NeoKey (left/up/down/select). Also listens to the footswitch
(GPIO 17) and shows a toast when it is pressed.
"""
import time
from hw.neokey import NeoKey
from hw.oled import Oled
from hw.midi_io import Midi
from hw.footswitch import Footswitch
from ui.menu import Menu

TOAST_SECS = 1.2

def main():
    nk = NeoKey()
    oled = Oled()
    midi = Midi()
    midi.open_ports()
    foot = Footswitch()
    menu = Menu(midi_adapter=midi)

    toast_until = 0.0

    # Initial render
    img, draw = oled.begin_frame()
    menu.render_into(draw, oled.width, oled.height)
    oled.show(img)
    menu.dirty = False

    try:
        while True:
            # --- Inputs ---
            events = nk.read_events()
            if events:
                menu.handle_events(events)

            if foot.pressed_edge():
                toast_until = time.monotonic() + TOAST_SECS

            # --- Render if dirty or toast active ---
            need_render = menu.dirty or (time.monotonic() < toast_until)
            if need_render:
                img, draw = oled.begin_frame()
                menu.render_into(draw, oled.width, oled.height)
                # toast overlay
                if time.monotonic() < toast_until:
                    w, h = oled.width, oled.height
                    draw.rectangle((0, h-12, w-1, h-1), outline=1, fill=0)
                    draw.text((4, h-11), "Footswitch!", fill=1)
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