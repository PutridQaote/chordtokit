# ChordToKit - Remote Management Guide

## Overview

ChordToKit is a Raspberry Pi-based MIDI chord capture device that automatically converts 4-note chords into drum kit patterns for the DDrum DDTi module. This guide covers how to remotely manage and update the device via SSH.

## Device Access

### SSH Connection

The device runs automatically on boot. To access it remotely:

```bash
ssh mty@chordtokit
```

## Service Management

ChordToKit runs as a systemd service that starts automatically on boot.

### Check Service Status
```bash
sudo systemctl status chordtokit.service
```

### Control the Service
```bash
# Stop the service (to make changes)
sudo systemctl stop chordtokit.service

# Start the service
sudo systemctl start chordtokit.service

# Restart the service
sudo systemctl restart chordtokit.service

# Disable auto-start (for debugging)
sudo systemctl disable chordtokit.service

# Re-enable auto-start
sudo systemctl enable chordtokit.service
```

### View Service Logs
```bash
# Real-time logs
sudo journalctl -u chordtokit.service -f

# Recent logs
sudo journalctl -u chordtokit.service --since "10 minutes ago"

# All logs from today
sudo journalctl -u chordtokit.service --since today
```

## Updating ChordToKit

### Quick Update Script

For convenience, there's an update script:

```bash
# Run the update
./update-chordtokit.sh
```

### Manual Update Process

If you prefer to update manually:

```bash
# 1. SSH into the device
ssh mty@chordtokit

# 2. Stop the running service
sudo systemctl stop chordtokit.service

# 3. Navigate to the code directory
cd ~/chordtokit

# 4. Pull latest changes
git pull origin main

# 5. Restart the service
sudo systemctl start chordtokit.service

# 6. Verify it's running
sudo systemctl status chordtokit.service
```


## Development and Debugging

### Running Manually (for debugging)

Sometimes you may want to run the app manually instead of as a service:

```bash
# Stop the service first
sudo systemctl stop chordtokit.service

# Run manually to see real-time output
cd ~/chordtokit
python3 app.py

# When done, restart the service
sudo systemctl start chordtokit.service
```

### Configuration Changes

The device stores settings in `~/chordtokit/config.json`. You can edit this manually:

```bash
cd ~/chordtokit
nano config.json
# Make your changes, then restart the service
sudo systemctl restart chordtokit.service
```

### Hardware Testing

Various test scripts are available:

```bash
cd ~/chordtokit/tests

# Test MIDI connections
python3 midi_config_test.py

# Test NeoKey buttons
python3 neokey_event_dump.py

# Test footswitch
python3 test_footswitch_raw.py

# Test spiral animation
python3 test_spiral_oled_neokeyHits.py
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status for error messages
sudo systemctl status chordtokit.service

# Check recent logs
sudo journalctl -u chordtokit.service --since "5 minutes ago"

# Check if dependencies are working
cd ~/chordtokit
python3 -c "import mido, board, adafruit_ssd1306; print('Dependencies OK')"
```

### MIDI Issues

```bash
# List available MIDI devices
python3 -c "import mido; print('Inputs:', mido.get_input_names()); print('Outputs:', mido.get_output_names())"

# Test MIDI configuration
cd ~/chordtokit
python3 tests/midi_config_test.py
```


## Device Information

- **OS**: Raspberry Pi OS
- **User**: mty
- **Service**: chordtokit.service
- **App Directory**: `/home/mty/chordtokit`
- **Auto-start**: Yes (via systemd)
- **Git Remote**: Origin (update source)

## Physical Device Controls

- **Footswitch**: Start/stop chord capture
- **NeoKey Buttons**: Navigate menus (left=back, up/down=navigate, right=select)
- **Long Press Back Button (2.2s)**: Shutdown confirmation
- **OLED Display**: Shows current status and menus

## Power Management

The device can be safely shut down using the interface:

1. Hold the back button (leftmost NeoKey) for 2.2 seconds
2. Press the right button (select) to confirm shutdown
3. Wait for "safe to unplug" message
4. Remove power

Or via SSH:
```bash
sudo shutdown -h now
```

---