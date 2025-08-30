import mido, time

IDENTITY_REQUEST = [0x7E, 0x7F, 0x06, 0x01]  # Universal Non-RT, device=7F (all), SubID1=06, SubID2=01

def main():
    # Find any DDTi OUT (to send TO device) and corresponding IN (to receive FROM device)
    out_name = None
    in_name = None
    for name in mido.get_output_names():
        if any(k in name.lower() for k in ["triggerio", "ddti", "ddrum"]):
            out_name = name
            break
    for name in mido.get_input_names():
        if any(k in name.lower() for k in ["triggerio", "ddti", "ddrum"]):
            in_name = name
            break

    if not out_name or not in_name:
        print("Could not find DDTi ports. Inputs:", mido.get_input_names(), "Outputs:", mido.get_output_names())
        return

    print(f"Sending Identity Request to {out_name}, listening on {in_name}")
    with mido.open_output(out_name) as outp, mido.open_input(in_name) as inp:
        outp.send(mido.Message('sysex', data=IDENTITY_REQUEST))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3.0:
            for msg in inp.iter_pending():
                if msg.type == 'sysex':
                    print("Got SysEx response len", len(msg.data), "data:", list(msg.data))
            time.sleep(0.01)

if __name__ == "__main__":
    main()