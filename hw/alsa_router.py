"""
ALSA sequencer router for hardware-level MIDI thru connections.
Uses aconnect to create/remove kernel-level routes for near-zero latency.
"""
import re
import subprocess
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

@dataclass
class AlsaPort:
    client_id: int
    port_id: int
    client_name: str
    port_name: str
    
    @property
    def address(self) -> str:
        return f"{self.client_id}:{self.port_id}"

class AlsaRouter:
    def __init__(self):
        self._managed_connections: Set[Tuple[str, str]] = set()
        self._keyboard_thru_enabled = False
        self._ddti_thru_enabled = True  # Default ON
        self._midi_filters: Dict[str, any] = {}  # Track active filters
        
    def discover_ports(self) -> Dict[str, List[AlsaPort]]:
        """Discover ALSA MIDI ports, categorized by type."""
        try:
            result = subprocess.run(['aconnect', '-l'], 
                                  capture_output=True, text=True, check=True)
            return self._parse_aconnect_output(result.stdout)
        except Exception as e:
            print(f"Error discovering ALSA ports: {e}")
            return {"keyboard": [], "ddti": [], "external": []}
    
    def _parse_aconnect_output(self, output: str) -> Dict[str, List[AlsaPort]]:
        """Parse aconnect -l output into categorized port lists."""
        ports = {"keyboard": [], "ddti": [], "external": []}
        current_client = None
        
        for line in output.strip().split('\n'):
            # Match client line: "client 20: 'Arturia KeyStep 32' [type=kernel]"
            client_match = re.match(r'client\s+(\d+):\s+\'([^\']+)\'', line)
            if client_match:
                client_id = int(client_match.group(1))
                client_name = client_match.group(2)
                current_client = (client_id, client_name)
                continue
                
            # Match port line: "    0 'Arturia KeyStep 32 MIDI 1'"
            port_match = re.match(r'\s+(\d+)\s+\'([^\']+)\'', line)
            if port_match and current_client:
                client_id, client_name = current_client
                port_id = int(port_match.group(1))
                port_name = port_match.group(2)
                
                # Skip the problematic "Midi Through" client entirely
                if "midi through" in client_name.lower():
                    continue
                    
                port = AlsaPort(client_id, port_id, client_name, port_name)
                
                # Categorize by client name patterns
                if self._is_keyboard(client_name):
                    ports["keyboard"].append(port)
                elif self._is_ddti(client_name):
                    ports["ddti"].append(port)
                elif self._is_external_device(client_name):
                    ports["external"].append(port)
                    
        return ports
    
    def _is_keyboard(self, client_name: str) -> bool:
        """Identify keyboard input devices."""
        patterns = ["keystep", "arturia", "keylab"]
        return any(pattern in client_name.lower() for pattern in patterns)
    
    def _is_ddti(self, client_name: str) -> bool:
        """Identify DDTi device."""
        patterns = ["triggerio", "ddti", "ddrum"]
        return any(pattern in client_name.lower() for pattern in patterns)
    
    def _is_external_device(self, client_name: str) -> bool:
        """Identify external MIDI devices (not keyboard, not DDTi, not virtual)."""
        if self._is_keyboard(client_name) or self._is_ddti(client_name):
            return False
        
        # Exclude virtual and problematic clients
        exclude_patterns = [
            "rtmidi",           # RtMidi clients
            "midi through",     # ALSA through ports
            "through",          # Generic through ports
            "system",           # System clients
            "timer",            # Timer clients
            "announce",         # Announce clients
        ]
        
        for pattern in exclude_patterns:
            if pattern in client_name.lower():
                return False
        
        # Look for real USB MIDI devices
        include_patterns = ["um-one", "usb", "roland", "yamaha", "korg", "akai", "novation"]
        return any(pattern in client_name.lower() for pattern in include_patterns)
    
    def get_existing_connections(self) -> Set[Tuple[str, str]]:
        """Get all existing ALSA connections."""
        connections = set()
        try:
            result = subprocess.run(['aconnect', '-l'], 
                              capture_output=True, text=True, check=True)
            
            current_client = None
            for line in result.stdout.strip().split('\n'):
                # Match client line
                client_match = re.match(r'client\s+(\d+):\s+\'([^\']+)\'', line)
                if client_match:
                    current_client = client_match.group(1)
                    continue
                
                # Match port line with connections
                port_match = re.match(r'\s+(\d+)\s+\'([^\']+)\'', line)
                if port_match and current_client:
                    port_id = port_match.group(1)
                    src_address = f"{current_client}:{port_id}"
                    continue
                
                # Match connection line: "	Connecting To: 20:0"
                conn_match = re.match(r'\s+Connecting To:\s+(\d+:\d+)', line)
                if conn_match and current_client:
                    src_address = f"{current_client}:0"  # Use the current client
                    connections.add((src_address, conn_match.group(1)))
                
        except Exception as e:
            print(f"Error getting existing connections: {e}")
        
        return connections
    
    def create_connection(self, src: str, dst: str) -> bool:
        """Create an ALSA connection if it doesn't exist."""
        try:
            # Verify both ports exist first
            ports = self.discover_ports()
            all_ports = ports["keyboard"] + ports["ddti"] + ports["external"]
            
            src_exists = any(p.address == src for p in all_ports)
            dst_exists = any(p.address == dst for p in all_ports)
            
            if not src_exists:
                print(f"Source port {src} not found")
                return False
            if not dst_exists:
                print(f"Destination port {dst} not found")
                return False
                
            # Check if connection already exists
            existing = self.get_existing_connections()
            if (src, dst) in existing:
                return True
                
            subprocess.run(['aconnect', src, dst], 
                          capture_output=True, check=True)
            self._managed_connections.add((src, dst))
            print(f"Created ALSA connection: {src} -> {dst}")
            return True
        except subprocess.CalledProcessError as e:
            # Don't spam errors for expected failures
            return False
        except Exception as e:
            print(f"Error creating connection {src} -> {dst}: {e}")
            return False
    
    def remove_connection(self, src: str, dst: str) -> bool:
        """Remove an ALSA connection."""
        try:
            subprocess.run(['aconnect', '-d', src, dst], 
                          capture_output=True, check=True)
            self._managed_connections.discard((src, dst))
            print(f"Removed ALSA connection: {src} -> {dst}")
            return True
        except subprocess.CalledProcessError:
            # Connection probably doesn't exist, which is fine
            self._managed_connections.discard((src, dst))
            return True
        except Exception as e:
            print(f"Error removing connection {src} -> {dst}: {e}")
            return False
    
    def set_keyboard_thru(self, enabled: bool):
        """Enable/disable keyboard thru to external devices."""
        if self._keyboard_thru_enabled == enabled:
            return
            
        self._keyboard_thru_enabled = enabled
        self._reconcile_routes()
    
    def set_ddti_thru(self, enabled: bool):
        """Enable/disable DDTi thru to external devices."""
        if self._ddti_thru_enabled == enabled:
            return
            
        self._ddti_thru_enabled = enabled
        self._reconcile_routes()
    
    def get_keyboard_thru(self) -> bool:
        return self._keyboard_thru_enabled
    
    def get_ddti_thru(self) -> bool:
        return self._ddti_thru_enabled
    
    def _create_filtered_connection(self, src_port: AlsaPort, dst_port: AlsaPort) -> bool:
        """Create a filtered MIDI connection that blocks Program Change messages."""
        try:
            # Import MidiFilter here at runtime
            from hw.midi_filter import MidiFilter
            
            # Create filter instance
            filter_key = f"{src_port.address}->{dst_port.address}"
            
            # Try to find the actual mido port names
            import mido
            available_inputs = mido.get_input_names()
            available_outputs = mido.get_output_names()
            
            # Find matching input port
            src_mido_name = None
            for name in available_inputs:
                if src_port.client_name.lower() in name.lower():
                    src_mido_name = name
                    break
                    
            # Find matching output port  
            dst_mido_name = None
            for name in available_outputs:
                if dst_port.client_name.lower() in name.lower():
                    dst_mido_name = name
                    break
                    
            if not src_mido_name or not dst_mido_name:
                print(f"Could not find mido port names for {src_port.client_name} -> {dst_port.client_name}")
                return False
                
            # Create and start filter
            midi_filter = MidiFilter(src_mido_name, dst_mido_name)
            if midi_filter.start():
                self._midi_filters[filter_key] = midi_filter
                self._managed_connections.add((src_port.address, dst_port.address))
                print(f"Created filtered MIDI connection: {src_port.address} -> {dst_port.address} (no PC)")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"Error creating filtered connection {src_port.address} -> {dst_port.address}: {e}")
            return False
    
    def _remove_filtered_connection(self, src: str, dst: str) -> bool:
        """Remove a filtered MIDI connection."""
        filter_key = f"{src}->{dst}"
        
        if filter_key in self._midi_filters:
            self._midi_filters[filter_key].stop()
            del self._midi_filters[filter_key]
            self._managed_connections.discard((src, dst))
            print(f"Removed filtered MIDI connection: {src} -> {dst}")
            return True
        return False
    
    def _reconcile_routes(self):
        """Reconcile desired routes with actual ALSA connections."""
        ports = self.discover_ports()
        
        keyboard_ports = ports["keyboard"]
        ddti_ports = ports["ddti"] 
        external_ports = ports["external"]
        
        if not external_ports:
            return  # No external devices to route to
            
        # Handle DDTi thru routes (with Program Change filtering)
        for ddti_port in ddti_ports:
            for ext_port in external_ports:
                if self._ddti_thru_enabled:
                    # Use filtered connection for DDTi -> External (blocks Program Change)
                    self._create_filtered_connection(ddti_port, ext_port)
                else:
                    # Remove filtered connection
                    self._remove_filtered_connection(ddti_port.address, ext_port.address)
        
        # Handle keyboard thru routes (no filtering needed - direct ALSA connection)
        for kb_port in keyboard_ports:
            for ext_port in external_ports:
                if self._keyboard_thru_enabled:
                    self.create_connection(kb_port.address, ext_port.address)
                else:
                    self.remove_connection(kb_port.address, ext_port.address)
    
    def ensure_baseline_routes(self):
        """Ensure baseline DDTi routes are established."""
        self._reconcile_routes()
    
    def cleanup_managed_connections(self):
        """Remove all connections we created."""
        # Clean up filtered connections first
        for filter_key, midi_filter in list(self._midi_filters.items()):
            midi_filter.stop()
        self._midi_filters.clear()
        
        # Clean up direct ALSA connections
        for src, dst in list(self._managed_connections):
            self.remove_connection(src, dst)
    
    def debug_discovered_ports(self):
        """Print discovered ports for debugging."""
        ports = self.discover_ports()
        print("=== ALSA Port Discovery ===")
        for category, port_list in ports.items():
            print(f"{category.upper()}:")
            for port in port_list:
                print(f"  {port.address} - {port.client_name}: {port.port_name}")
        print("===========================")