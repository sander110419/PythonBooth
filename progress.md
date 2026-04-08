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
- [x] Add crash recovery, durable capture jobs, backup writing, diagnostics export, preflight validation, and resilient camera reconnects

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
- 2026-04-08: Added atomic JSON/file writes, `session_state.json`, `jobs.json`, a durable `CapturePipeline`, backup-target mirroring with verification, diagnostics bundle export, and preflight validation for storage, naming, SDK, hot-folder, and disk checks.
- 2026-04-08: Hardened `CameraManager` with reconnect backoff, degraded/retrying states, poll-failure thresholds, and explicit recovery when a backend poll loop stops being healthy.
- 2026-04-08: Added crash-safe session restoration by reopening the last dirty session, replaying unfinished capture jobs on launch, persisting current session pointers in config, and keeping camera/session snapshots on disk while the app runs.
- 2026-04-08: Verified the reliability pass with `python -m compileall src main.py tests`, `python -m pytest -q` -> `19 passed`, and `QT_QPA_PLATFORM=offscreen PYTHONPATH=src python main.py --demo --auto-exit-ms 1200`.
- 2026-04-08: Added an offscreen recovery smoke test that simulated an unclean exit after a capture and confirmed the next launch restored the same session with the captured photo intact (`restored=True photos=1`).
- 2026-04-08: Added Canon-specific tethering guidance so busy/file-transfer connection failures now point operators to `[Choose USB connection app] -> [Photo Import/Remote Control]`, Wi-Fi-off, direct-USB, and Linux auto-mount conflict checks. Added a matching preflight warning and regression coverage.
- 2026-04-08: Hardened Canon capture requests for EOS R bodies by clearing stale transfer events before each shot and preferring Canon's direct `TakePicture` command with shutter-press fallback, to reduce tethered capture faults such as camera-side `Err 70`.
- 2026-04-08: Fixed preview rendering for RAW captures by extracting Canon SDK thumbnails for tethered CR2/CR3 files, adding embedded-JPEG fallback extraction for local/imported RAW files, and making the viewer/thumbnail pipeline load those previews instead of trying to open RAW files directly.
- 2026-04-08: Corrected a Canon transfer regression by removing thumbnail extraction from the live `DirItemRequestTransfer` path; RAW previews now come from the downloaded CR2/CR3 bytes so capture delivery to the app is not interrupted.
- 2026-04-08: Reworked the main window again to prioritize the selected-photo area: slimmer header chrome, removed preview footer blocks, reduced timeline height, and added a centered aspect-ratio preview stage that keeps the visible canvas locked to 3:2 or 2:3 while using the maximum available space.
- 2026-04-08: Fixed secondary-display initialization so a newly opened secondary window is seeded immediately with the current selected image instead of waiting for the next selection or capture event. Added an offscreen regression test for that flow.
- 2026-04-08: Updated the shared preview decoder to honor EXIF rotation via Qt auto-transform, so the main preview, timeline thumbnails, secondary displays, and embedded RAW JPEG previews all follow camera orientation correctly.
- 2026-04-08: Fixed portrait RAW preview handling by applying raw-file orientation metadata when Canon embedded previews arrive landscape, and updated the main preview stage to switch between 3:2 and 2:3 based on the selected image orientation.
- 2026-04-08: Added an appearance setting for application background color, including a color picker in the options dialog, persisted config, and live theme refresh so the main window updates immediately without restarting.
- 2026-04-08: Reduced RAW-session startup cost by skipping unsupported 14-bit embedded JPEG candidates, using cached preview/thumbnail files in the UI once they exist, and only rebuilding RAW previews on launch when they are missing or orientation-mismatched.
- 2026-04-08: Refined the custom-background theme behavior so only the app backdrop follows the chosen color, while labels, cards, controls, and the status bar keep their intended dark surfaces and contrast.
- 2026-04-08: Extended the custom background theme into the image presentation surfaces so the letterboxed area behind photos updates in both the main preview and every secondary display window.
- 2026-04-08: Narrowed the custom color setting further so it now applies only to the image background surfaces behind photos; the surrounding app shell stays on the default dark theme.

## Remaining limitation

- Canon tethering code is implemented and reconnect-safe, but it could not be validated against a real connected camera in this environment.
- Real Canon capture still needs a connected camera to validate end-to-end behavior even though the required bundled SDK binaries are now present.
