"""Screens module for the UI system."""
# Import base classes first
from .base_screens import Screen, ScreenResult, BaseCaptureScreen

# Import specific screen modules
from .system_screens import HomeScreen, ShutdownConfirmScreen, DDTiSyncScreen
from .settings_screens import MidiSettingsScreen, UtilitiesScreen
from .chord_screens import ChordCaptureMenuScreen, LearnMappingScreen, ChordCaptureScreen, SingleNoteCaptureScreen

__all__ = [
    'Screen',
    'ScreenResult', 
    'BaseCaptureScreen',
    'HomeScreen',
    'ShutdownConfirmScreen',
    'DDTiSyncScreen',
    'MidiSettingsScreen',
    'UtilitiesScreen',
    'ChordCaptureMenuScreen',
    'LearnMappingScreen',
    'ChordCaptureScreen',
    'SingleNoteCaptureScreen',
]