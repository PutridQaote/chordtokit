import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

ADDR = 0x30
NEO_PWR_PIN  = 5        # common power gate on some batches
NEO_DATA_PIN = 6       # try 24 first; if no light, change to 6
COUNT = 4

ss = Seesaw(board.I2C(), addr=ADDR)
# power enable (safe no-op if unused)
try:
    ss.pin_mode(NEO_PWR_PIN, ss.OUTPUT)
    ss.digital_write(NEO_PWR_PIN, True)
    print("NeoPixel power enabled on pin", NEO_PWR_PIN)
except Exception as e:
    print("Power enable skipped:", e)

pixels = SSNeoPixel(ss, NEO_DATA_PIN, COUNT, auto_write=False)
pixels.brightness = 0.8

def show(rgb, name):
    pixels.fill((0,0,0))
    pixels.fill(rgb); pixels.show()
    print("fill", name); time.sleep(0.6)

for c,n in [((255,255,255),"white"),((255,0,0),"red"),((0,255,0),"green"),((0,0,255),"blue")]:
    show(c,n)

pixels.fill((0,0,0)); pixels.show(); print("done")