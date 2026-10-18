# Yamaha Style Studio

Windows desktop prototype for inspecting and editing Yamaha .sty files that use Standard MIDI File (SMF) track chunks.

## Current features
- Open .sty, .mid, and .midi files with an SMF structure.
- Inspect MIDI events and track names.
- Apply MIDI channel volume (CC7) and instrument Program Change to channels found in a selected track.
- Save to a new file; unrecognized chunks outside MIDI tracks are preserved byte-for-byte.

## Important compatibility notice
Yamaha style files can contain vendor-specific sections and arranger metadata (for example CASM/OTS-related data), and keyboard models vary. This is an early prototype, not a verified full-fidelity Yamaha style editor. Always keep the original file and test an edited copy on your keyboard. A track's MIDI program number does not guarantee the same instrument sound on every keyboard; Yamaha voice banks may require bank-select messages (CC0/CC32), which are not yet edited by this version.

## Run from source
Install Python 3.11+, then run:
    py main.py

## Windows build
The GitHub Actions workflow builds a portable Windows executable using PyInstaller when code is pushed to main. It does not yet create a signed MSI installer.
