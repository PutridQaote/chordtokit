# tools/neokey_leds_on.py
import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR      = 0x30
DATA_PIN  = 3       # confirmed
PIXELS    = 4
BRIGHT    = 0.6
SAGE      = (150, 169, 125)

print("Init NeoKey @0x30 …")
ss = Seesaw(board.I2C(), addr=ADDR)

pixels = SSNeoPixel(ss, DATA_PIN, PIXELS, auto_write=False)
pixels.brightness = BRIGHT
pixels.fill(SAGE)
pixels.show()
print("LEDs ON (sage). Ctrl+C to exit.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    pixels.fill((0,0,0))
    pixels.show()
    print("LEDs OFF.")
