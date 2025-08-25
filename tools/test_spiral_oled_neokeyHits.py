# tools/spiral_oled_neokey.py
# Animates a spiral on the OLED and lights NeoKey buttons sage green when pressed.
# OLED: SSD1306 I2C 128x64 at 0x3D
# NeoKey: seesaw @ 0x30, key pins 4..7 (active-low), NeoPixel data pin = 2

import time, math, board, busio
from PIL import Image, ImageDraw
import adafruit_ssd1306
from adafruit_seesaw.seesaw import Seesaw
from adafruit_seesaw.neopixel import NeoPixel as SSNeoPixel

#------------------------//
# NEOKEY CONSTANTS
#----------------------//

NEOKEY_ADDR      = 0x30
NEOKEY_KEY_PINS  = [4, 5, 6, 7]
NEOKEY_PIXELS    = 4
NEOKEY_DATA_PIN  = 2            # <-- confirmed working on my board
NEOKEY_BRIGHT    = 0.4

#------------------------//
# OLED CONSTANTS
#----------------------//

OLED_ADDR      = 0x3D
OLED_WIDTH     = 128
OLED_HEIGHT    = 64
OLED_RESET_PIN = 4 # wtf is this



#------------------------//
# ---- Config ----
#----------------------//

OLED_SIZE   = (OLED_WIDTH, OLED_HEIGHT)
SAGE        = (150, 169, 125)    # soft sage green
FRAME_HZ    = 30                 # target frame rate for the OLED animation
SPIRAL_SPEED = 3.33               # higher = faster sweep
SPIRAL_TURNS = 8.88               # how many turns to draw at once

# ---- Init I2C, OLED, NeoKey ----
i2c = busio.I2C(board.SCL, board.SDA)

# OLED init; try 128x64 first, then fallback to 128x32 if it throws
W, H = OLED_SIZE
try:
    oled = adafruit_ssd1306.SSD1306_I2C(W, H, i2c, addr=OLED_ADDR)
except Exception:
    W, H = 128, 32
    oled = adafruit_ssd1306.SSD1306_I2C(W, H, i2c, addr=OLED_ADDR)

oled.fill(0); oled.show()
img = Image.new("1", (W, H))
draw = ImageDraw.Draw(img)
cx, cy = W // 2, H // 2
radius = min(W, H) * 0.5 - 2

# NeoKey init
ss = Seesaw(i2c, addr=NEOKEY_ADDR)
for p in NEOKEY_KEY_PINS:
    ss.pin_mode(p, ss.INPUT_PULLUP)

pixels = SSNeoPixel(ss, NEOKEY_DATA_PIN, NEOKEY_PIXELS, auto_write=False)
pixels.NEOKEY_BRIGHT = NEOKEY_BRIGHT
pixels.fill((0, 0, 0)); pixels.show()

# ---- Helpers ----
def read_keys_pressed():
    # returns [bool x4], True if pressed
    return [not ss.digital_read(p) for p in NEOKEY_KEY_PINS]

def update_key_leds(pressed):
    for i, p in enumerate(pressed):
        pixels[i] = SAGE if p else (0, 0, 0)
    pixels.show()

def draw_spiral(t):
    # Archimedean spiral r = a + b*theta, animated by phase t
    # We’ll render SPIRAL_TURNS turns with a small step.
    draw.rectangle((0, 0, W-1, H-1), outline=0, fill=0)

    # subtle frame border (helps you see enclosure edges)
    draw.rectangle((0, 0, W-1, H-1), outline=1, fill=0)

    turns = SPIRAL_TURNS
    theta_max = 2 * math.pi * turns
    a = 0.0
    b = radius / theta_max  # so it fits nicely

    # phase offset to animate
    phase = t * SPIRAL_SPEED

    # draw the spiral as connected short segments
    step = 0.03
    prev = None
    for k in range(int(theta_max / step) + 1):
        theta = k * step + phase
        r = a + b * (k * step)
        x = int(cx + r * math.cos(theta))
        y = int(cy + r * math.sin(theta))
        if prev is not None:
            draw.line((prev[0], prev[1], x, y), fill=1)
        prev = (x, y)

# ---- Main loop ----
print(f"OLED {W}x{H} @0x{OLED_ADDR:02X}, NeoKey @0x{NEOKEY_ADDR:02X} (data pin {NEOKEY_DATA_PIN})")
print("Press keys to light them sage green. Ctrl+C to exit.")

frame_time = 1.0 / FRAME_HZ
t0 = time.monotonic()

try:
    while True:
        # 1) Update spiral frame
        t = time.monotonic() - t0
        draw_spiral(t)
        oled.image(img)
        oled.show()

        # 2) Read keys and update LEDs
        pressed = read_keys_pressed()
        update_key_leds(pressed)

        # 3) Check for edge on pin 4 (index 0) and pin 5 (index 1)
        if pressed[0] and not prev_pressed[0]:
            SPIRAL_TURNS += 1
            print(f"SPIRAL_TURNS increased to {SPIRAL_TURNS}")
        if pressed[1] and not prev_pressed[1]:
            SPIRAL_TURNS = max(1, SPIRAL_TURNS - 1)
            print(f"SPIRAL_TURNS decreased to {SPIRAL_TURNS}")

        prev_pressed = pressed.copy()

        # simple frame pacing
        time.sleep(frame_time)
except KeyboardInterrupt:
    pass
finally:
    # graceful clear
    pixels.fill((0, 0, 0)); pixels.show()
    oled.fill(0); oled.show()
    print("Clean exit; LEDs off, OLED cleared.")
