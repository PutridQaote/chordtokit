# Create a new test file: tests/midi_channel_debug.py
import time
import mido
from collections import defaultdict

def main():
    # Open the TriggerIO port for listening
    try:
        port = mido.open_input('TriggerIO:TriggerIO TriggerIO MIDI In 24:0')
        print("Listening to TriggerIO port...")
        print("1. Play some notes on your keyboard")
        print("2. Hit some triggers on the DDTi")
        print("3. Watch what channel each message comes on")
        print("Press Ctrl+C to stop\n")
        
        message_counts = defaultdict(int)
        
        while True:
            for msg in port.iter_pending():
                if msg.type == 'note_on' and msg.velocity > 0:
                    channel_display = msg.channel + 1  # Convert to 1-based
                    source = "DDTi" if msg.channel == 9 else "Keyboard"
                    message_counts[msg.channel] += 1
                    
                    print(f"Note: {msg.note:3d} Channel: {channel_display:2d} Vel: {msg.velocity:3d} Source: {source}")
                elif msg.type in ['note_off', 'control_change', 'program_change']:
                    channel_display = msg.channel + 1
                    print(f"Other: {msg.type} Channel: {channel_display}")
                    
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print(f"\nMessage counts by channel:")
        for channel in sorted(message_counts.keys()):
            print(f"  Channel {channel + 1}: {message_counts[channel]} messages")
    except Exception as e:
        print(f"Error: {e}")
        print("\nAvailable MIDI inputs:")
        for name in mido.get_input_names():
            print(f"  {name}")

if __name__ == "__main__":
    main()