# Create a new test script: tests/single_note_debug.py
import time
import mido
from collections import defaultdict
from hw.alsa_router import AlsaRouter

def main():
    # Set up ALSA router
    router = AlsaRouter()
    
    print("=== Testing Single Note Capture MIDI Flow ===")
    print("1. Setting up like single-note capture mode...")
    
    # Get current keyboard thru state
    original_kb_thru = router.get_keyboard_thru()
    print(f"Original keyboard thru: {original_kb_thru}")
    
    # Disable keyboard thru (like single-note capture does)
    print("Disabling keyboard thru...")
    router.set_keyboard_thru(False)
    
    time.sleep(1)  # Let routing settle
    
    try:
        port = mido.open_input('TriggerIO:TriggerIO TriggerIO MIDI In 24:0')
        print("Listening to TriggerIO port...")
        print("NOW try:")
        print("1. Hit DDTi triggers - should see channel 10")
        print("2. Play keyboard notes - should see other channels")
        print("Press Ctrl+C to stop\n")
        
        message_counts = defaultdict(int)
        
        while True:
            for msg in port.iter_pending():
                if msg.type == 'note_on' and msg.velocity > 0:
                    channel_display = msg.channel + 1
                    source = "DDTi" if msg.channel == 9 else "Keyboard"
                    message_counts[msg.channel] += 1
                    
                    print(f"Note: {msg.note:3d} Channel: {channel_display:2d} Vel: {msg.velocity:3d} Source: {source}")
                    
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print(f"\nMessage counts by channel:")
        for channel in sorted(message_counts.keys()):
            print(f"  Channel {channel + 1}: {message_counts[channel]} messages")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Restore original routing
        print(f"Restoring keyboard thru to: {original_kb_thru}")
        router.set_keyboard_thru(original_kb_thru)

if __name__ == "__main__":
    main()