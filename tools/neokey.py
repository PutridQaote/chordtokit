# tools/neokey.py
import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR      = 0x30
KEY_PINS  = [4, 5, 6, 7]
PIXELS    = 4
DATA_PIN  = 2            # <-- confirmed working on your board
BRIGHT    = 0.4

class NeoKey:
    def __init__(self, addr=ADDR, key_pins=KEY_PINS, data_pin=DATA_PIN, pixels=PIXELS, bright=BRIGHT):
        self.ss = Seesaw(board.I2C(), addr=addr)
        self.key_pins = list(key_pins)
        for p in self.key_pins:
            self.ss.pin_mode(p, self.ss.INPUT_PULLUP)
        self.px = SSNeoPixel(self.ss, data_pin, pixels, auto_write=False)
        self.px.brightness = bright

    def read_keys(self):
        # returns list[bool] length 4: True=pressed
        return [not self.ss.digital_read(p) for p in self.key_pins]

    def set_pixel(self, idx, rgb):
        self.px[idx] = rgb

    def show(self):
        self.px.show()

    def clear(self):
        self.px.fill((0,0,0)); self.px.show()
