# tools/neokey.py
import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

from constants import *

ADDR      = NEOKEY_ADDR
KEY_PINS  = NEOKEY_KEY_PINS
PIXELS    = NEOKEY_PIXELS
DATA_PIN  = NEOKEY_DATA_PIN            # <-- confirmed working on your board
BRIGHT    = NEOKEY_BRIGHT

class NeoKey:
    def __init__(self, addr=NEOKEY_ADDR, key_pins=NEOKEY_KEY_PINS,
                 data_pin=NEOKEY_DATA_PIN, pixels=NEOKEY_PIXELS, bright=NEOKEY_BRIGHT):
        
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
