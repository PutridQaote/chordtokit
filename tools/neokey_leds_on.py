# tools/neokey_pixels_pin3.py
import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR = 0x30
DATA_PIN = 3          # per Adafruit pinouts
COUNT = 4

ss = Seesaw(board.I2C(), addr=ADDR)

# If your board had a power gate, we'd toggle it here.
# The NeoKey 1x4 docs don't list a separate pixel power-enable pin.

px = SSNeoPixel(ss, DATA_PIN, COUNT, auto_write=False)
px.brightness = 0.7
px.fill((255, 255, 255))
px.show()
print("All white for 2s…")
time.sleep(2)
px.fill((0, 0, 0))
px.show()
print("Off.")
