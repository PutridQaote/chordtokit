import time, board
from adafruit_seesaw.seesaw import Seesaw

ss = Seesaw(board.I2C(), addr=0x30)

# Buttons are typically on seesaw pins 24..27; read as a bitfield.
# (Implementation detail varies by board; this often works out of the box.)
print("Press keys; Ctrl+C to stop")
while True:
    keys = ss.digital_read_bulk((1<<24)|(1<<25)|(1<<26)|(1<<27))
    # bit set = HIGH; depending on pullups it may invert; we just print the raw
    print(bin(keys))
    time.sleep(0.2)