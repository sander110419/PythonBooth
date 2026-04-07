# PythonBooth Progress

## Subtasks

- [x] Inspect the empty workspace and the reference Canon/photobooth implementation
- [x] Define the application architecture and phased delivery plan
- [x] Scaffold the project structure, packaging, and entrypoints
- [ ] Implement the session library, metadata storage, and thumbnail pipeline
- [x] Build the naming-template engine with wildcard and variable support
- [ ] Implement simulator and Canon camera backends with reconnect polling
- [ ] Build the polished PyQt6 main window, live preview, timeline, and zoom workflow
- [ ] Add secondary display windows, hot-folder import, shortcuts, and session utilities
- [ ] Run automated tests and repeated application smoke tests
- [ ] Fix runtime issues found during testing and document remaining limitations

## Log

- 2026-04-07: Reviewed `/home/sander/Dev/Photobooth-software/` to reuse its Canon EDSDK approach instead of inventing a new tethering layer.
- 2026-04-07: Chose a clean-room architecture for `PythonBooth` with a camera backend abstraction, simulator mode, persistent session library, and detachable display windows.
- 2026-04-07: Implemented `pythonbooth.services.naming` with wildcard and brace-style templates, cross-platform sanitization, sequence selection, and compiled filename previews.
- 2026-04-07: Added pytest coverage for brace tokens, wildcard templates, mixed templates, sanitization, and context field exposure. Verified with `PYTHONPATH=src python -m pytest -q` -> `5 passed`.
