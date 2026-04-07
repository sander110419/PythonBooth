# PythonBooth Progress

## Subtasks

- [x] Inspect the empty workspace and the reference Canon/photobooth implementation
- [x] Define the application architecture and phased delivery plan
- [x] Scaffold the project structure, packaging, and entrypoints
- [x] Implement the session library, metadata storage, and thumbnail pipeline
- [x] Build the naming-template engine with wildcard and variable support
- [x] Implement simulator and Canon camera backends with reconnect polling
- [x] Build the polished PyQt6 main window, selected-photo preview, timeline, and zoom workflow
- [x] Add secondary display windows, hot-folder import, shortcuts, and session utilities
- [x] Run automated tests and repeated application smoke tests
- [x] Fix runtime issues found during testing and document remaining limitations

## Log

- 2026-04-07: Reviewed `/home/sander/Dev/Photobooth-software/` to reuse its Canon EDSDK approach instead of inventing a new tethering layer.
- 2026-04-07: Chose a clean-room architecture for `PythonBooth` with a camera backend abstraction, simulator mode, persistent session library, and detachable display windows.
- 2026-04-07: Implemented `pythonbooth.services.naming` with wildcard and brace-style templates, cross-platform sanitization, sequence selection, and compiled filename previews.
- 2026-04-07: Added pytest coverage for brace tokens, wildcard templates, mixed templates, sanitization, and context field exposure. Verified with `PYTHONPATH=src python -m pytest -q` -> `5 passed`.
- 2026-04-07: Added the persistent session library, thumbnail generation, hot-folder watcher, logging setup, simulator backend, Canon EDSDK backend, and threaded camera manager.
- 2026-04-07: Built the PyQt6 control application with selected-photo preview, Lightroom-style timeline, zoom controls, delete workflow, secondary display windows, and session/naming controls.
- 2026-04-07: Resolved a Canon backend indentation bug and replaced a painter-based placeholder thumbnail with a headless-safe OpenCV fallback after smoke testing.
- 2026-04-07: Verified with `python -m compileall src main.py tests`, `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q` -> `6 passed`, offscreen simulator launch, scripted simulator capture smoke test (`photos=1`), Canon no-camera startup smoke test (`status=Error`, `Canon SDK not found`), and hot-folder import smoke test (`photos=1`).
- 2026-04-07: Removed live-view polling from the UI and camera manager so the app only polls for completed captures, then updates the selected image and timeline.
- 2026-04-07: Reworked the UI into a preview-first layout with a compact top action bar, near-fullscreen selected-image viewer, slim timeline strip, and an options menu/dialog for backend, naming, reconnect, hot-folder, simulator, and SDK settings.
- 2026-04-07: Verified the new UI with `python -m compileall src main.py tests`, `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q` -> `6 passed`, offscreen app launch, and a simulator capture smoke test after opening the options dialog (`photos=1`).
- 2026-04-07: Added bundled Canon EDSDK assets under `canon-sdk/` from `/home/sander/Downloads/edsdk/`, including Linux `x86_64` `libEDSDK.so` and Windows DLL/lib files.
- 2026-04-07: Verified the Canon loader resolves the bundled SDK and that startup now reaches `No Canon camera detected` instead of `Canon SDK not found` when no camera is attached.

## Remaining limitation

- Canon tethering code is implemented and reconnect-safe, but it could not be validated against a real connected camera in this environment.
- Real Canon capture still needs a connected camera to validate end-to-end behavior even though the required bundled SDK binaries are now present.
