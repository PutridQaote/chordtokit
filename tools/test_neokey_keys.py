import time, board
from adafruit_seesaw.seesaw import Seesaw

ss = Seesaw(board.I2C(), addr=0x30)

cand = list(range(0,32))  # brute-force 0..31
states = {}
# set all as INPUT_PULLUP, ignore pins that error
for p in cand[:]:
    try:
        ss.pin_mode(p, ss.INPUT_PULLUP)
        states[p] = ss.digital_read(p)
    except Exception:
        cand.remove(p)

print("Probing pins:", cand)
print("Press/release each key; changes will print. Ctrl+C to stop.")
while True:
    for p in cand:
        try:
            v = ss.digital_read(p)
            if v != states[p]:
                print(f"PIN {p} -> {int(v)}")
                states[p] = v
        except Exception:
            pass
    time.sleep(0.03)