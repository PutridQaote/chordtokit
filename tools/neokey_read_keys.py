# tools/neokey_read_keys.py
import time, board
from adafruit_seesaw.seesaw import Seesaw

ss = Seesaw(board.I2C(), addr=0x30)

PINS = [4, 5, 6, 7]
for p in PINS:
    ss.pin_mode(p, ss.INPUT_PULLUP)

print("Press/release keys; 1=unpressed, 0=pressed")
while True:
    states = {p: int(not ss.digital_read(p)) for p in PINS}
    print(states)
    time.sleep(0.2)
