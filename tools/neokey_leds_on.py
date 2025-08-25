# tools/neokey_leds_on.py
# Turn all NeoKey LEDs on (sage green) and keep them on until Ctrl+C.
# Uses discovered setup: seesaw @ 0x30, NeoPixel data pin = 2, 4 pixels,
# and enables potential power-gate pins (safe no-ops if not present).

import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR      = 0x30
DATA_PIN  = 2       # confirmed by your scan
PIXELS    = 4
BRIGHT    = 0.6
SAGE      = (150, 169, 125)

# Pins that sometimes gate NeoPixel power on Seesaw-based boards:
PWR_GATES = [5, 15, 16, 17, 20, 21, 22, 23]

print("Initializing NeoKey…")
ss = Seesaw(board.I2C(), addr=ADDR)

# Enable any power gates (harmless if a pin doesn't exist on your board)
for gp in PWR_GATES:
    try:
        ss.pin_mode(gp, ss.OUTPUT)
        ss.digital_write(gp, True)
        print(f"Enabled power gate pin {gp}")
    except Exception:
        pass

# Drive the pixels
pixels = SSNeoPixel(ss, DATA_PIN, PIXELS, auto_write=False)
pixels.brightness = BRIGHT
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
