# Yamaha Style Studio

Modern Windows desktop prototype for MIDI event editing and Yamaha STY files that use Standard MIDI File (SMF) chunks.

## Features
- Dark modern UI with mixer, MIDI editor, and project workspace.
- Drag-and-drop of .STY/.MID files on Windows with tkinterdnd2; file picker is also available.
- Per-channel MIDI CC7 volume mixer and a command to lower all channels together.
- Event-level MIDI editing: tick, channel, event type and data; add/delete common events.
- Organized project folders with .ysproj files to continue work later.
- Offline Smart Mix expert-system assistant that analyzes note density, average note velocity, current CC7, and drum-channel role. Suggestions require confirmation before application.
- Export edits as a new .STY or .MID file.

## Run from source
Python 3.11+ recommended:
```powershell
py -m pip install -r requirements.txt
py main.py
```

## Compatibility and safety
This is a prototype, not a certified universal Yamaha style editor. It parses Standard MIDI File (SMF) structures with MThd/MTrk chunks. Some Yamaha STY files contain proprietary CASM, OTS, voice-bank or other structures that may not be fully supported. Saving re-encodes MIDI track events, so always keep the original file and test exported files on the target keyboard before performance. Program Change alone may not select the desired Yamaha voice without correct bank-select events.

The Smart Mix assistant is an offline heuristic/expert system, not a trained neural-network model and not an audio analyzer. It proposes starting points based on MIDI event features; listening and human judgment are still required.

## Windows build
GitHub Actions creates a portable one-file executable. It is not currently a signed MSI installer.
