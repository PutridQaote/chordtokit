import mido, time, sys, json

CAP_SECONDS = 30
OUTFILE = "ddti_captured_dump.syx"

def main():
    # Pick DDTi port (same name used as output in the app)
    ddti_port = None
    for name in mido.get_input_names():
        if any(k in name.lower() for k in ["triggerio", "ddti", "ddrum"]):
            ddti_port = name
            break
    if not ddti_port:
        print("No DDTi-like input port found. Available:", mido.get_input_names())
        return

    print(f"Listening for SysEx on: {ddti_port}")
    print(f"Hit the DDTi front-panel dump / send kit now (timeout {CAP_SECONDS}s)...")

    msgs = []
    start = time.monotonic()
    with mido.open_input(ddti_port) as port:
        while (time.monotonic() - start) < CAP_SECONDS:
            for msg in port.iter_pending():
                if msg.type == 'sysex':
                    print(f"SysEx len={len(msg.data)} data[0:8]={list(msg.data[:8])}")
                    msgs.append(msg)
            time.sleep(0.01)

    if not msgs:
        print("No SysEx received.")
        return

    # Save first dump to .syx (standard MIDO write)
    try:
        from mido import MidiFile, MidiTrack, MetaMessage
        mf = MidiFile()
        tr = MidiTrack()
        mf.tracks.append(tr)
        for m in msgs:
            tr.append(m)
        mf.save(OUTFILE)
        print(f"Saved {len(msgs)} SysEx message(s) to {OUTFILE}")
    except Exception as e:
        print(f"Failed to save .syx: {e}")

    # Also dump JSON summary
    summary = [{
        "len": len(m.data),
        "head": list(m.data[:12]),
        "tail": list(m.data[-8:]),
    } for m in msgs]
    with open("ddti_sysex_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("Wrote ddti_sysex_summary.json")

if __name__ == "__main__":
    main()