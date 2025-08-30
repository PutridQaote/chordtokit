import time, mido
from hw.alsa_router import AlsaRouter
from hw.midi_io import Midi
from config import Config

def drain(p): 
    try: 
        for _ in range(2): list(p.iter_pending()); time.sleep(0.01)
    except: pass

cfg = Config().load().as_dict()
m = Midi(cfg); m.open_ports()

router = AlsaRouter()
prev = router.get_keyboard_thru()
router.set_keyboard_thru(False)

ddti_name = m.get_out_port_name()
kb_name   = m.get_in_port_name()
print("DDTi out name (will open for IN):", ddti_name)
print("Keyboard in name:", kb_name)

ddti_in = mido.open_input(ddti_name) if ddti_name else None
drain(ddti_in); drain(m._in_port)

print("\nNow hit a DDTi trigger, then press a key on the keyboard. Ctrl+C to stop.\n")
try:
    while True:
        if ddti_in:
            for msg in list(ddti_in.iter_pending()):
                if msg.type == 'note_on' and msg.velocity > 0:
                    print(f"[DDTi ] note {msg.note} ch{msg.channel+1} vel{msg.velocity}")
        for msg in list(m.iter_input()):
            if msg.type == 'note_on' and msg.velocity > 0:
                print(f"[KBD  ] note {msg.note} ch{msg.channel+1} vel{msg.velocity}")
        time.sleep(0.01)
except KeyboardInterrupt:
    pass
finally:
    try: ddti_in and ddti_in.close()
    except: pass
    router.set_keyboard_thru(prev)
