import time, board
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

I2C_ADDR = 0x30  # NeoKey
i2c = board.I2C()
ss = Seesaw(i2c, addr=I2C_ADDR)

# 4 RGB LEDs on NeoKey 1x4
pixels = SSNeoPixel(ss, 24, 4)  # pin 24 is the NeoPixel line, 4 pixels
pixels.brightness = 0.3

for i in range(4):
    pixels.fill((0, 0, 0))
    pixels[i] = (255, 0, 0)   # Red
    time.sleep(0.3)
    pixels[i] = (0, 255, 0)   # Green
    time.sleep(0.3)
    pixels[i] = (0, 0, 255)   # Blue
    time.sleep(0.3)

pixels.fill((0, 0, 0))  # turn off
