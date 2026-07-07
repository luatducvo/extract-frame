# FFmpeg Frame Extractor

A desktop GUI for extracting frames from video with FFmpeg, built with Python, PySide6, bundled FFmpeg binaries, uv, and PyInstaller.

## Features

- Select an input video and output folder.
- Inspect media metadata through `ffprobe`.
- Extract a fixed number of frames. The app reads video duration and spaces frames evenly across the video.
- Extract one frame every N seconds, for example every 5 seconds.
- Choose output image format: PNG, JPG, or WebP.
- Preview the generated FFmpeg command before running.
- Run FFmpeg in the background with realtime logs and cancel support.
- Package a Windows desktop app with the bundled `ffmpeg-8.1.2-essentials_build` directory.

## Development

```powershell
uv sync --group dev
uv run ffmpeg-gui
```

The app first looks for FFmpeg in:

```text
ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe
ffmpeg-8.1.2-essentials_build\bin\ffprobe.exe
```

If those files are not present, it falls back to `ffmpeg.exe` and `ffprobe.exe` on PATH.

## Tests

```powershell
uv run pytest
```

## Package

```powershell
uv run pyinstaller ffmpeg_gui.spec --clean --noconfirm
```

The packaged app is created under:

```text
dist\FFmpegDesktopGUI\FFmpegDesktopGUI.exe
```

PyInstaller includes the local `ffmpeg-8.1.2-essentials_build` folder so the app does not require a global FFmpeg installation.
