# Yamaha Style Studio

Modern Windows desktop prototype for inspecting and editing MIDI events in Yamaha STY files that use Standard MIDI File (SMF) chunks.

## Features in version 0.2.0
- Dark, modern desktop UI with mixer, MIDI editor, and project workspace.
- Drag-and-drop of .STY/.MID files when the optional Windows drag-and-drop package is available; file picker always remains available.
- Per-channel mixer for MIDI CC7 volume, with an all-channel reduction command.
- Event-level MIDI editing: change tick, channel, event type and data; add/delete common MIDI events.
- Save project into an organized folder as a .ysproj file; reopen it later to continue.
- Local Smart Mix recommendations based on channel and CC7 values, with confirmation before applying.
- Export edited data to a new .STY or .MID file.

## Run from source
Python 3.11+ recommended:
```powershell
py -m pip install -r requirements.txt
py main.py
```

## Important compatibility limits
This is not a certified universal Yamaha style editor. It currently parses Standard MIDI File (SMF) structures containing MThd/MTrk chunks. Some Yamaha STY files use additional or proprietary CASM, OTS, voice-bank, or other structures that may not be fully supported. Track data is re-encoded when saved, so do not overwrite originals; test exported files on the target keyboard. Program Change alone may not select the intended Yamaha voice without the appropriate bank-select data.

The "Smart Mix" feature is a transparent local rule-based assistant, not a cloud AI model and not an audio analyzer. Recommendations are starting points, not professional mastering advice.

## Windows build
GitHub Actions builds a portable one-file executable. It is not currently a signed MSI installer.
