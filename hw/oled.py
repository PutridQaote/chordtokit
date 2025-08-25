"""SSD1306 OLED wrapper for simple text/menu rendering.
Creates a fresh 1-bit frame per render and pushes it to the display.
"""
from typing import Tuple
import board, busio
from PIL import Image, ImageDraw
import adafruit_ssd1306

from constants import OLED_ADDR, OLED_SIZE

class Oled:
    def __init__(self, addr: int = OLED_ADDR, size: Tuple[int, int] = OLED_SIZE):
        self.width, self.height = size
        self._i2c = busio.I2C(board.SCL, board.SDA)
        try:
            self._oled = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, self._i2c, addr=addr)
        except Exception:
            # Fallback for 128x32 panels if size was misconfigured
            self.width, self.height = 128, 32
            self._oled = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, self._i2c, addr=addr)
        self.clear()

    def clear(self):
        self._oled.fill(0)
        self._oled.show()

    def begin_frame(self):
        """Return (img, draw) for the next frame."""
        img = Image.new("1", (self.width, self.height))
        draw = ImageDraw.Draw(img)
        return img, draw

    def show(self, img):
        self._oled.image(img)
        self._oled.show()