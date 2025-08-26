# app.py
import time
from config import Config
from constants import FOOTSWITCH_ACTIVE_LOW
from hw.neokey import NeoKey
from hw.oled import Oled
from hw.midi_io import Midi
from hw.footswitch import Footswitch
from ui.menu import Menu

TOAST_SECS = 1.2

def main():
    cfg = Config().load()

    nk = NeoKey(brightness=float(cfg.get("neokey_brightness", 0.5)))
    oled = Oled()
    midi = Midi(cfg.as_dict()); midi.open_ports()

    # Allow runtime override from config
    foot = Footswitch(active_low=bool(cfg.get("footswitch_active_low", FOOTSWITCH_ACTIVE_LOW)))

    menu = Menu(midi_adapter=midi, config=cfg)

    toast_until = 0.0

    img, draw = oled.begin_frame()
    menu.render_into(draw, oled.width, oled.height)
    oled.show(img)
    menu.dirty = False

    try:
        while True:
            events = nk.read_events()
            if events:
                menu.handle_events(events)

            # Add this missing section to re-render when menu is dirty
            if menu.dirty:
                img, draw = oled.begin_frame()
                menu.render_into(draw, oled.width, oled.height)
                oled.show(img)
                menu.dirty = False

            time.sleep(0.01)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
