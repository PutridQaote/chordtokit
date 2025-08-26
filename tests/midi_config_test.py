"""Simple test to see raw MIDI input from KeyStep."""
import time
from hw.midi_io import Midi
from config import Config

def main():
    cfg = Config().load()
    midi = Midi(cfg.as_dict())
    
    print("Available MIDI inputs:")
    for i, port in enumerate(midi.get_inputs()):
        print(f"  {i}: {port}")
    
    print("Available MIDI outputs:")
    for i, port in enumerate(midi.get_outputs()):
        print(f"  {i}: {port}")
    
    print(f"\nConfigured input: {cfg.get('midi_in_name', 'Not set')}")
    print(f"Configured output: {cfg.get('midi_out_name', 'Not set')}")
    
    try:
        midi.open_ports()
        print(f"\nListening on: {midi.get_selected_in()}")
        print(f"Sending to: {midi.get_selected_out()}")
        print("Play some keys on your KeyStep...")
        print("Press Ctrl+C to stop\n")
        
        while True:
            for msg in midi.iter_input():
                print(f"MIDI: {msg.type} note={getattr(msg, 'note', 'N/A')} vel={getattr(msg, 'velocity', 'N/A')} channel={getattr(msg, 'channel', 'N/A')}")
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()