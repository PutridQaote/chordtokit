import mido, time

def test_port_access():
    """Test if we can access the DDTi port the same way the sync screen does."""
    print("=== DDTi Sync Debug ===")
    
    # Method 1: Direct port finding (like the working script)
    ddti_port_direct = None
    for name in mido.get_input_names():
        if any(k in name.lower() for k in ["triggerio", "ddti", "ddrum"]):
            ddti_port_direct = name
            break
    print(f"Direct method found: {ddti_port_direct}")
    
    # Method 2: Simulate what sync screen does (via chord_capture.midi)
    # We need to import the actual classes to test this
    try:
        import sys
        sys.path.append('.')
        from features.chord_capture import ChordCapture
        from hw.midi_io import MidiIO
        
        # Create a MidiIO instance like the app does
        midi = MidiIO()
        out_port_name = midi.get_out_port_name()
        print(f"MidiIO get_out_port_name(): {out_port_name}")
        
        # Test if we can open this as input
        if out_port_name:
            try:
                test_port = mido.open_input(out_port_name)
                print(f"✓ Can open {out_port_name} as input")
                test_port.close()
            except Exception as e:
                print(f"✗ Cannot open {out_port_name} as input: {e}")
    except Exception as e:
        print(f"Error testing MidiIO method: {e}")
    
    # Method 3: Test if the port is already open somewhere else
    if ddti_port_direct:
        try:
            test_port = mido.open_input(ddti_port_direct)
            print(f"✓ Can open {ddti_port_direct} directly")
            test_port.close()
        except Exception as e:
            print(f"✗ Cannot open {ddti_port_direct} directly: {e}")

if __name__ == "__main__":
    test_port_access()