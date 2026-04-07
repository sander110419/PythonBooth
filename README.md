# PythonBooth

PythonBooth is a PyQt6-based photobooth and tethering application focused on Canon camera workflows, fast image review, and multi-display presentation.

## Current feature set

- Modern main control window with selected-image preview, timeline, and session controls
- Canon EDSDK backend with reconnect polling and a simulator backend for hardware-free testing
- Session library with thumbnails, metadata, deletion, and persistent sessions on disk
- Flexible naming engine with wildcard and variable support
- Unlimited secondary display windows that mirror the selected image
- Hot-folder import mode for workflows that deliver images outside direct tethering
- Keyboard shortcuts, rotating logs, and headless smoke-test support

## Workflow highlights

- Capture-driven tethering that polls the camera for new images without running live view
- Large selected-image preview so each new capture is immediately reviewable
- Lightroom-style horizontal timeline with automatic selection and right-click delete
- Zoom toggle with `fit` and `fill` display modes for the selected preview
- Session-aware naming previews using templates such as `{EVENT}_{BOOTH}_{DAY}_{CAMERA:05d}.{EXT}` or `EVENT_BOOTH_DAY_0XXXX.CRX`
- Secondary display windows that can be resized freely and toggled fullscreen with `F11`
- Hot-folder import for workflows where another process downloads images outside direct tethering

## Running

```bash
python -m pip install -e .[dev]
python main.py
```

Useful shortcuts:

- `Space`: request a capture
- `Ctrl+N`: open a secondary image window
- `Ctrl+Shift+N`: start a new session
- `Delete`: delete the selected timeline image
- `F11`: toggle fullscreen in a secondary display window

## Canon SDK notes

- The Canon backend is written against EDSDK and searches `EDSDK_LIBRARY_PATH`, a local `canon-sdk/` folder, or the sibling reference project at `/home/sander/Dev/Photobooth-software/canon-sdk`.
- Windows support expects Canon DLLs such as `EDSDK.dll`.
- Linux support expects `libEDSDK.so`. In this environment there was no x86_64 Linux EDSDK binary available, so Canon startup was verified only for graceful failure and reconnect behavior, not real camera polling.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
python main.py
```

For headless smoke tests:

```bash
QT_QPA_PLATFORM=offscreen python main.py --demo --auto-exit-ms 2000
```
