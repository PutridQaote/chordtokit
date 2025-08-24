import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR = 0x30
ss = Seesaw(board.I2C(), addr=ADDR)

# Try both likely data pins
CANDIDATE_PINS = [6, 24]
COUNT = 4

for dp in CANDIDATE_PINS:
    try:
        pixels = SSNeoPixel(ss, dp, COUNT, auto_write=False)
        pixels.brightness = 0.6
        print(f"Testing data pin {dp}...")
        for rgb in [(255,0,0), (0,255,0), (0,0,255), (255,255,255)]:
            pixels.fill(rgb); pixels.show()
            print("  showing", rgb)
            time.sleep(0.6)
        pixels.fill((0,0,0)); pixels.show()
    except Exception as e:
        print(f"Pin {dp} failed: {e}")
