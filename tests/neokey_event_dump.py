from hw.neokey import NeoKey
import time

nk = NeoKey(brightness=0.2)
print("Press/release keys; Ctrl+C to stop")
try:
    while True:
        for ev in nk.read_events():
            print(ev)  # e.g., ('press', 1)
        time.sleep(0.01)
except KeyboardInterrupt:
    nk.clear()
