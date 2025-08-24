# tools/test_neokey_leds_strong.py
import time, board
from adafruit_seesaw.seesaw import Seesaw

# Some NeoKey 1x4 variants gate NeoPixel power via a seesaw GPIO (often 5).
# Try enabling it before driving pin 24 (the NeoPixel data pin).
NEO_PWR_PIN = 5     # try power-enable on 5
NEO_DATA_PIN = 24   # NeoPixel data on 24
PIXELS = 4

print("Init Seesaw @0x30...")
ss = Seesaw(board.I2C(), addr=0x30)

# Try to turn on NeoPixel power (safe even if not needed)
try:
    ss.pin_mode(NEO_PWR_PIN, ss.OUTPUT)
    ss.digital_write(NEO_PWR_PIN, True)
    print(f"Enabled NeoPixel power on pin {NEO_PWR_PIN}")
except Exception as e:
    print(f"(Power pin enable skipped/failed: {e})")

# Import the Seesaw NeoPixel helper only after Seesaw is up
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

pixels = SSNeoPixel(ss, NEO_DATA_PIN, PIXELS, auto_write=False)  # force manual show
pixels.brightness = 0.8  # crank it up to be obvious

def wipe(rgb):
    pixels.fill((0,0,0))
    pixels.fill(rgb)
    pixels.show()
    print(f"Filled {rgb}")
    time.sleep(0.6)

# Solid wipes
wipe((255, 255, 255))
wipe((255,   0,   0))
wipe((  0, 255,   0))
wipe((  0,   0, 255))

# Chase with explicit show
for i in range(PIXELS):
    pixels.fill((0,0,0))
    pixels[i] = (255, 255, 255)
    pixels.show()
    print(f"Pixel {i} ON")
    time.sleep(0.4)

pixels.fill((0,0,0))
pixels.show()
print("Done.")
