# tools/neokey_leds_on.py
# Turn all NeoKey LEDs on (sage green) and keep them on until Ctrl+C.
# NeoKey: seesaw @ 0x30, NeoPixel data pin = 2, 4 pixels

import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR      = 0x30
DATA_PIN  = 2
PIXELS    = 4
BRIGHT    = 0.5
SAGE      = (150, 169, 125)

print("Initializing NeoKey…")
ss = Seesaw(board.I2C(), addr=ADDR)

# Create neopixel object on the seesaw data pin
pixels = SSNeoPixel(ss, DATA_PIN, PIXELS, auto_write=False)
pixels.brightness = BRIGHT

# Light them up
pixels.fill(SAGE)
pixels.show()
print("LEDs ON (sage). Press Ctrl+C to turn off and exit.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    pixels.fill((0, 0, 0))
    pixels.show()
    print("LEDs OFF. Bye.")
