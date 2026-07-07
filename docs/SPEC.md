# Spec: FFmpeg Frame Extractor

## Objective
Build a Windows-friendly desktop GUI for FFmpeg that lets non-command-line users inspect media, extract evenly spaced video frames, run jobs, and package the app with the bundled FFmpeg binaries.

## Tech Stack
- Python 3.13 compatible source, requiring Python >= 3.11.
- PySide6 for the desktop interface.
- FFmpeg/ffprobe from `ffmpeg-8.1.2-essentials_build/bin` during development and from the PyInstaller bundle at runtime.
- uv for dependency and command management.
- PyInstaller for Windows packaging.

## Commands
- Install/sync: `uv sync --group dev`
- Run app: `uv run ffmpeg-gui`
- Test: `uv run pytest`
- Package: `uv run pyinstaller ffmpeg_gui.spec --clean --noconfirm`

## Project Structure
- `ffmpeg_gui/`: application source code.
- `ffmpeg_gui/core.py`: FFmpeg path discovery, frame extraction command building, ffprobe parsing, process helpers.
- `ffmpeg_gui/app.py`: PySide6 UI and background worker integration.
- `tests/`: unit tests for command and path behavior.
- `docs/`: implementation spec and usage notes.
- `ffmpeg_gui.spec`: PyInstaller configuration.

## Code Style
Keep UI code separate from subprocess command construction.

```python
command = build_extract_frames_by_interval_command(ffmpeg_path, input_path, output_dir, 5)
```

## Testing Strategy
- Unit tests cover path resolution, ffprobe parsing, duration parsing, and FFmpeg frame extraction command construction.
- Smoke verification checks imports and PyInstaller spec parsing.
- Manual UI verification is possible with `uv run ffmpeg-gui`.

## Boundaries
- Always: keep FFmpeg invocation argument-list based, never shell-string based.
- Ask first: adding online services, telemetry, or destructive file overwrite defaults.
- Never: write output over input files, embed secrets, or require global FFmpeg PATH setup.

## Success Criteria
- App can choose an input video/output folder, inspect metadata, extract frames by count or by seconds interval, run FFmpeg in a worker, show logs, and cancel a running job.
- App can find bundled FFmpeg/ffprobe in development and PyInstaller runtime.
- `uv run pytest` passes.
- PyInstaller packaging configuration includes the FFmpeg portable binary directory.
