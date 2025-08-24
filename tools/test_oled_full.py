import busio, board
import adafruit_ssd1306
from PIL import Image, ImageDraw

i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3D)  # note 0x3D from detect

oled.fill(0)
oled.show()

image = Image.new("1", (oled.width, oled.height))
draw = ImageDraw.Draw(image)
# solid white rectangle filling the display
draw.rectangle((0, 0, oled.width-1, oled.height-1), outline=1, fill=1)
oled.image(image)
oled.show()
