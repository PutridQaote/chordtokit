# tools/test_oled_text_fill.py
import busio, board, time, textwrap
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont

from constants import *

TEXT = (
    "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG 0123456789 "
    "the quick brown fox jumps over the lazy dog 0123456789"
)

# Try a scalable TTF first; fallback to PIL default
def load_font(pt):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", pt)
    except Exception:
        return ImageFont.load_default()

def fit_text(text, w, h, margin=2, max_pt=48, min_pt=6):
    # Binary search font size that fits both width and height
    best = (min_pt, [])
    lo, hi = min_pt, max_pt
    while lo <= hi:
        mid = (lo + hi) // 2
        font = load_font(mid)
        # wrap by width heuristic, then check bbox
        # Estimate chars per line from average char width
        avg_w = max(1, int(font.getlength("M")))
        chars = max(1, int((w - 2*margin) / (avg_w * 0.6)))
        wrapped = textwrap.fill(text, width=chars)
        img = Image.new("1", (w, h))
        draw = ImageDraw.Draw(img)
        bbox = draw.multiline_textbbox((margin, margin), wrapped, font=font, spacing=0)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= (w - 2*margin) and th <= (h - 2*margin):
            best = (mid, wrapped)
            lo = mid + 1
        else:
            hi = mid - 1
    return best

# Init display
i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c, addr=OLED_ADDR)

# Build image
img = Image.new("1", (OLED_WIDTH, OLED_HEIGHT))
d   = ImageDraw.Draw(img)

# Border
d.rectangle((0, 0, OLED_WIDTH-1, OLED_HEIGHT-1), outline=1, fill=0)

# Fit and draw text
pt, wrapped = fit_text(TEXT, OLED_WIDTH, OLED_HEIGHT, margin=2)
font = load_font(pt)
d.multiline_text((2, 2), wrapped, font=font, fill=1, spacing=0)

# Show + report
oled.image(img); oled.show()
print(f"Rendered with font size: {pt} (addr 0x{OLED_ADDR:02X}, {W}x{H})")

# Hold a moment, then optionally clear on exit:
time.sleep(20)
oled.fill(0); oled.show()
print("Cleared.")
