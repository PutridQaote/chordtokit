import time, board
from adafruit_seesaw.seesaw import Seesaw

ss = Seesaw(board.I2C(), addr=0x30)

PINS = [24, 25, 26, 27]  # common for NeoKey 1x4
for p in PINS:
    ss.pin_mode(p, ss.INPUT_PULLUP)

print("Press/release keys; 1=HIGH, 0=LOW")
while True:
    states = [(1 if ss.digital_read(p) else 0) for p in PINS]
    print(dict(zip(PINS, states)))
    time.sleep(0.2)