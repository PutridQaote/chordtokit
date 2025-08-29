"""
MIDI filter to block Program Change messages while allowing everything else.
Used between DDTi and external devices.
"""
import sys
import mido
import threading
import time
from typing import Optional

class MidiFilter:
    def __init__(self, input_port_name: str, output_port_name: str):
        self.input_port_name = input_port_name
        self.output_port_name = output_port_name
        self.input_port: Optional[mido.ports.BaseInput] = None
        self.output_port: Optional[mido.ports.BaseOutput] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
    def start(self):
        """Start the filter in a background thread."""
        if self.running:
            return
            
        try:
            self.input_port = mido.open_input(self.input_port_name)
            self.output_port = mido.open_output(self.output_port_name)
            self.running = True
            
            self.thread = threading.Thread(target=self._filter_loop, daemon=True)
            self.thread.start()
            
            print(f"MIDI filter started: {self.input_port_name} -> {self.output_port_name} (blocking PC)")
            return True
            
        except Exception as e:
            print(f"Error starting MIDI filter: {e}")
            self.stop()
            return False
    
    def stop(self):
        """Stop the filter and clean up resources."""
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=1.0)
            
        if self.input_port:
            try:
                self.input_port.close()
            except:
                pass
            self.input_port = None
            
        if self.output_port:
            try:
                self.output_port.close()
            except:
                pass
            self.output_port = None
            
        print(f"MIDI filter stopped: {self.input_port_name} -> {self.output_port_name}")
    
    def _filter_loop(self):
        """Main filter loop - forwards all messages except Program Change."""
        while self.running and self.input_port and self.output_port:
            try:
                for msg in self.input_port.iter_pending():
                    # Filter out Program Change messages (type 'program_change')
                    if msg.type != 'program_change':
                        self.output_port.send(msg)
                    # Optionally log filtered messages for debugging
                    # else:
                    #     print(f"Filtered Program Change: channel={msg.channel}, program={msg.program}")
                        
                time.sleep(0.001)  # Small sleep to prevent excessive CPU usage
                
            except Exception as e:
                if self.running:  # Only log if we're supposed to be running
                    print(f"MIDI filter error: {e}")
                break

if __name__ == "__main__":
    # Allow running as standalone script for testing
    if len(sys.argv) != 3:
        print("Usage: python3 midi_filter.py <input_port> <output_port>")
        sys.exit(1)
        
    input_port = sys.argv[1]
    output_port = sys.argv[2]
    
    filter_instance = MidiFilter(input_port, output_port)
    
    try:
        if filter_instance.start():
            print("MIDI filter running. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping MIDI filter...")
    finally:
        filter_instance.stop()