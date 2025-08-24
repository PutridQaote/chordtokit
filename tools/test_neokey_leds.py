import time, board
from adafruit_seesaw.seesaw import Seesaw
try:
    from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel
except Exception as e:
    raise SystemExit("Missing adafruit-circuitpython-neopixel / seesaw: "+str(e))

ADDR = 0x30
print("Init Seesaw @0x30…")
ss = Seesaw(board.I2C(), addr=ADDR)

# NeoKey 1x4 uses the Seesaw “neopixel” pin 24 with 4 pixels
PIN = 24
N   = 4
print(f"Init NeoPixels on pin {PIN} count {N}…")
pixels = SSNeoPixel(ss, PIN, N)
pixels.brightness = 0.2

def flash(i, rgb):
    pixels.fill((0,0,0))
    pixels[i] = rgb
    print(f"Lit pixel {i} -> {rgb}")
    time.sleep(0.4)

for i in range(N):
    flash(i, (255,0,0))
    flash(i, (0,255,0))
    flash(i, (0,0,255))

pixels.fill((0,0,0))
print("Done.")