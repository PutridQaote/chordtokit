"""Shared utilities for the UI system."""

# Button constants - logical left→right indices
BUTTON_LEFT, BUTTON_UP, BUTTON_DOWN, BUTTON_SELECT = 0, 1, 2, 3

def note_to_name(midi_note):
    """Convert MIDI note number to note name like 'F#4'."""
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    octave = (midi_note // 12) # removed -1 to match the ddti note numbers
    note = note_names[midi_note % 12]
    return f"{note}{octave}"