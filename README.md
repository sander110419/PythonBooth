# PythonBooth

PythonBooth is a PyQt6-based photobooth and tethering application focused on Canon camera workflows, fast image review, and multi-display presentation.

## Current feature set

- Modern main control window with live view, selected-image preview, timeline, and session controls
- Canon EDSDK backend with reconnect polling and a simulator backend for hardware-free testing
- Session library with thumbnails, metadata, deletion, and persistent sessions on disk
- Flexible naming engine with wildcard and variable support
- Unlimited secondary display windows that mirror the selected image
- Hot-folder import mode for workflows that deliver images outside direct tethering

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
