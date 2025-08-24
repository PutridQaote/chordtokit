# tools/neokey_leds_fullscan.py
import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR = 0x30
PIXELS = 4

ss = Seesaw(board.I2C(), addr=ADDR)

# Try enabling possible NeoPixel power gates (safe no-ops if absent)
for gp in [5, 15, 16, 17, 20, 21, 22, 23]:
    try:
        ss.pin_mode(gp, ss.OUTPUT)
        ss.digital_write(gp, True)
    except Exception:
        pass

def try_pin(dp):
    try:
        pixels = SSNeoPixel(ss, dp, PIXELS, auto_write=False)
        pixels.brightness = 0.8
        for rgb in [(255,0,0),(0,255,0),(0,0,255),(255,255,255)]:
            pixels.fill(rgb); pixels.show(); time.sleep(0.35)
        pixels.fill((0,0,0)); pixels.show()
        return True
    except Exception as e:
        return False

found = []
for dp in range(0, 32):
    ok = try_pin(dp)
    print(f"pin {dp}: {'OK (did you see light?)' if ok else 'no/err'}")
    time.sleep(0.05)
    if ok:
        found.append(dp)

print("DONE. Candidates that did not error:", found)
