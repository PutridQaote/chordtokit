"""
central hardware & app constants for chordtokit
edit here if wiring/addresses change
"""
from pathlib import Path

# project root (assuming this file is at the root level)
ROOT = Path(__file__).resolve().parent


#------------------------//
# NEOKEY CONSTANTS
#----------------------//

NEOKEY_ADDR      = 0x30         # i2c address
NEOKEY_KEY_PINS = [7, 6, 5, 4]  # this is in the order left→right on the interface

NEOKEY_PIXELS    = 4
NEOKEY_DATA_PIN  = 3            # led data pin, confirmed by testing
NEOKEY_BRIGHT    = 0.4          # not used currently??

DEBOUNCE_MS = 2                # key/footswitch debounce window


#------------------------//
# FOOTSWITCH CONSTANTS
#----------------------//

FOOTSWITCH_GPIO = 17
FOOTSWITCH_ACTIVE_LOW = True       # True if pressing shorts to GND (typical)
FOOTSWITCH_DEBOUNCE_MS = 25


#------------------------//
# OLED CONSTANTS
#----------------------//

OLED_ADDR      = 0x3D           # i2c address
OLED_WIDTH     = 128
OLED_HEIGHT    = 64
OLED_SIZE      = (OLED_WIDTH, OLED_HEIGHT)
# OLED_RESET_PIN = 4              # wtf is this


#------------------------//
# DDTI CONSTANTS
#----------------------//

DDTI_TEMPLATE_PATH = ROOT / "data" / "kit0_clean.bin"
DDTI_NOTE_OFFSETS = [11, 17, 23, 29]
