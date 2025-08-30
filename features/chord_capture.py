"""Chord capture logic for ChordToKit.
Collects incoming MIDI notes and builds chords, then sends SysEx to DDTi.
"""
from collections import OrderedDict
from typing import List, Optional
import time

from features.ddti import DDTi

class ChordCapture:
    """
    Captures MIDI note_on messages and builds 4-note chords.
    When 4 distinct notes are collected, sends SysEx to DDTi via MIDI output.
    """
    
    def __init__(self, midi_adapter, max_notes: int = 4, timeout_seconds: float = 5.0, allow_duplicates: bool = False, octave_down_lowest: bool = False):
        """
        Args:
            midi_adapter: Midi object with iter_input() and send() methods
            max_notes: Number of notes needed for a complete chord (default 4)
            timeout_seconds: Clear bucket if no new notes for this long
            allow_duplicates: If True, allow duplicate notes in chord
            octave_down_lowest: If True, transpose lowest note down one octave
        """
        self.midi = midi_adapter
        self.max_notes = max_notes
        self.timeout_seconds = timeout_seconds
        self.allow_duplicates = allow_duplicates
        self.octave_down_lowest = octave_down_lowest
        
        self.ddti = DDTi()
        self.bucket: List[int] = []
        self.last_note_time = 0.0
        self.active = False

        # DDTi state tracking
        self.last_sent_chord: Optional[List[int]] = None

    def set_allow_duplicates(self, allow: bool):
        """Change duplicate policy and clear bucket."""
        self.allow_duplicates = allow
        self.clear_bucket()

    def set_octave_down_lowest(self, octave_down: bool):
        """Change octave down policy and clear bucket."""
        self.octave_down_lowest = octave_down
        self.clear_bucket()

    def activate(self):
        """Activate chord capture mode."""
        self.active = True
        self.clear_bucket()
        
        # Flush any pending MIDI messages to start with a clean slate
        flushed_messages = list(self.midi.iter_input())
        if flushed_messages:
            print(f"Flushed {len(flushed_messages)} stale MIDI messages")
        
        # Reset timing
        self.last_note_time = 0.0
        
    def deactivate(self):
        """Deactivate chord capture mode."""
        print("ChordCapture.deactivate() - clearing bucket and flushing MIDI input")
        self.active = False
        self.clear_bucket()
        
        # Also flush on deactivate to prevent messages from accumulating
        flushed_messages = list(self.midi.iter_input())
        if flushed_messages:
            print(f"Flushed {len(flushed_messages)} stale MIDI messages on deactivate")


    def process_midi_input(self) -> Optional[List[int]]:
        """
        Process pending MIDI input messages.
        Returns the chord notes if a complete chord was captured, None otherwise.
        """
        # Only process MIDI when active.
        if not self.active:
            # Still consume messages to prevent buildup, but don't process them
            list(self.midi.iter_input())
            return None
        
        now = time.monotonic()
        
        # Check for timeout - clear bucket if too much time has passed
        if self.bucket and (now - self.last_note_time) > self.timeout_seconds:
            print(f"Chord capture timeout - clearing {len(self.bucket)} notes")
            self.bucket.clear()
        
        # Process incoming MIDI messages
        new_notes = []
        all_messages = list(self.midi.iter_input())
        
        for msg in all_messages:
            if msg.type == 'note_on' and msg.velocity > 0:
                if self.allow_duplicates:
                    # Always add new notes
                    new_notes.append(msg.note)
                    self.last_note_time = now
                else:
                    # Only add if not already in bucket (avoid duplicates)
                    if msg.note not in self.bucket:
                        new_notes.append(msg.note)
                        self.last_note_time = now
        
        # Add new notes to bucket
        if new_notes:
            self.bucket.extend(new_notes)
            print(f"Added {len(new_notes)} notes, bucket now has {len(self.bucket)} notes")
        
        # Check if we have enough notes for a chord
        if len(self.bucket) >= self.max_notes:
            if self.allow_duplicates:
                # Take first max_notes notes as-is
                chord = self.bucket[:self.max_notes]
            else:
                # Get unique notes, sorted, take first max_notes
                chord = sorted(list(OrderedDict.fromkeys(self.bucket)))[:self.max_notes]
            
            if len(chord) == self.max_notes:
                final_chord = self._apply_octave_down(chord) if self.octave_down_lowest else chord
                
                # Send SysEx using new DDTi interface
                try:
                    sysex_msg = self.ddti.build_full_sysex(final_chord)
                    self.midi.send(sysex_msg)
                    print(f"Sent full SysEx: {len(sysex_msg.data)} bytes")
                    
                    # The DDTi class now tracks its own state
                    self.last_sent_chord = self.ddti.get_current_state()
                    
                except Exception as e:
                    print(f"Error sending SysEx: {e}")
                
                # Clear bucket and return the original chord (for display purposes)
                self.bucket.clear()
                return chord  # Return original chord for display
            elif not self.allow_duplicates:
                print(f"Need {self.max_notes} distinct notes; got {len(chord)}: {chord}")
                # Keep collecting if we don't have enough unique notes
                
        return None

    def _apply_octave_down(self, chord: List[int]) -> List[int]:
        """Apply octave down to the lowest note in the chord."""
        if not chord:
            return chord
            
        result = list(chord)
        lowest_note = min(result)
        lowest_index = result.index(lowest_note)
        
        # Transpose down one octave (subtract 12 semitones)
        # Ensure we don't go below MIDI note 0
        new_lowest = max(0, lowest_note - 12)
        result[lowest_index] = new_lowest
        
        return result

    def clear_bucket(self):
        """Manually clear the note collection bucket."""
        if self.bucket:
            print(f"Manually cleared {len(self.bucket)} notes from bucket")
        self.bucket.clear()
        
    def get_bucket_status(self) -> dict:
        """Get current status of note collection."""
        if self.allow_duplicates:
            # Show all notes in order, but limit to 4 for display
            display_notes = self.bucket[:4]  # Only show first 4 for corner display
            progress_count = len(self.bucket)
        else:
            # Show only unique notes, limit to 4 for display
            unique_notes = list(OrderedDict.fromkeys(self.bucket))
            display_notes = unique_notes[:4]  # Only show first 4 for corner display
            progress_count = len(unique_notes)
        
        return {
            'notes': display_notes,
            'count': len(self.bucket),
            'unique_count': len(set(self.bucket)),
            'progress_count': progress_count,
            'needs': self.max_notes - progress_count,
            'last_note_age': time.monotonic() - self.last_note_time if self.bucket else 0,
            'allow_duplicates': self.allow_duplicates
        }