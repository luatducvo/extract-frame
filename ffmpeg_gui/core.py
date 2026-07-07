from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def bundled_bin_dir(root: Path | None = None) -> Path:
    base = root or app_root()
    return base / "ffmpeg-8.1.2-essentials_build" / "bin"


def resolve_tool(name: str, root: Path | None = None) -> Path:
    exe_name = name if name.endswith(".exe") else f"{name}.exe"
    bundled = bundled_bin_dir(root) / exe_name
    if bundled.exists():
        return bundled
    return Path(exe_name)


def require_distinct_paths(input_path: Path, output_path: Path) -> None:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Output file must be different from input file.")


def build_screenshot_command(
    ffmpeg_path: Path,
    input_path: Path,
    output_path: Path,
    timestamp: str,
    overwrite: bool = True,
) -> list[str]:
    require_distinct_paths(input_path, output_path)
    return [
        str(ffmpeg_path),
        "-hide_banner",
        "-y" if overwrite else "-n",
        "-ss",
        timestamp,
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        str(output_path),
    ]


def build_extract_frames_by_count_command(
    ffmpeg_path: Path,
    input_path: Path,
    output_dir: Path,
    duration_seconds: float,
    frame_count: int,
    prefix: str = "frame",
    image_format: str = "png",
    overwrite: bool = True,
) -> list[str]:
    if frame_count <= 0:
        raise ValueError("Frame count must be greater than 0.")
    if duration_seconds <= 0:
        raise ValueError("Video duration must be greater than 0.")
    interval_seconds = duration_seconds / frame_count
    return _build_extract_frames_command(
        ffmpeg_path=ffmpeg_path,
        input_path=input_path,
        output_dir=output_dir,
        fps_filter=f"fps=1/{_format_filter_number(interval_seconds)}",
        prefix=prefix,
        image_format=image_format,
        overwrite=overwrite,
        frame_limit=frame_count,
    )


def build_extract_frames_by_interval_command(
    ffmpeg_path: Path,
    input_path: Path,
    output_dir: Path,
    interval_seconds: float,
    prefix: str = "frame",
    image_format: str = "png",
    overwrite: bool = True,
) -> list[str]:
    if interval_seconds <= 0:
        raise ValueError("Interval seconds must be greater than 0.")
    return _build_extract_frames_command(
        ffmpeg_path=ffmpeg_path,
        input_path=input_path,
        output_dir=output_dir,
        fps_filter=f"fps=1/{_format_filter_number(interval_seconds)}",
        prefix=prefix,
        image_format=image_format,
        overwrite=overwrite,
    )


def duration_seconds_from_probe(data: dict) -> float:
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        raise ValueError("Could not read a positive video duration from media metadata.")
    return duration


def probe_media(ffprobe_path: Path, input_path: Path, timeout: int = 30) -> dict:
    result = subprocess.run(
        [
            str(ffprobe_path),
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    return json.loads(result.stdout)


def summarize_probe(data: dict) -> str:
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    lines = [
        f"Format: {fmt.get('format_long_name') or fmt.get('format_name') or 'Unknown'}",
        f"Duration: {_format_duration(fmt.get('duration'))}",
        f"Size: {_format_size(fmt.get('size'))}",
        f"Bitrate: {_format_bitrate(fmt.get('bit_rate'))}",
    ]
    for stream in streams:
        index = stream.get("index", "?")
        codec_type = stream.get("codec_type", "stream")
        codec = stream.get("codec_long_name") or stream.get("codec_name") or "unknown"
        if codec_type == "video":
            detail = f"{stream.get('width', '?')}x{stream.get('height', '?')}"
            fps = stream.get("avg_frame_rate")
            if fps and fps != "0/0":
                detail += f", {fps} fps"
        elif codec_type == "audio":
            detail = f"{stream.get('channels', '?')} ch, {stream.get('sample_rate', '?')} Hz"
        else:
            detail = codec_type
        lines.append(f"Stream #{index}: {codec_type} - {codec} ({detail})")
    return "\n".join(lines)


def _format_duration(raw: object) -> str:
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return "Unknown"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_size(raw: object) -> str:
    try:
        size = float(raw)
    except (TypeError, ValueError):
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "Unknown"


def _format_bitrate(raw: object) -> str:
    try:
        bitrate = float(raw)
    except (TypeError, ValueError):
        return "Unknown"
    return f"{bitrate / 1000:.0f} kb/s"


def _build_extract_frames_command(
    ffmpeg_path: Path,
    input_path: Path,
    output_dir: Path,
    fps_filter: str,
    prefix: str,
    image_format: str,
    overwrite: bool,
    frame_limit: int | None = None,
) -> list[str]:
    safe_prefix = prefix.strip() or "frame"
    safe_format = image_format.strip().lstrip(".") or "png"
    output_pattern = output_dir / f"{safe_prefix}_%04d.{safe_format}"
    args = [
        str(ffmpeg_path),
        "-hide_banner",
        "-benchmark",
        "-y" if overwrite else "-n",
        "-i",
        str(input_path),
        "-vf",
        fps_filter,
    ]
    if frame_limit is not None:
        args += ["-frames:v", str(frame_limit)]
    args.append(str(output_pattern))
    return args


def _format_filter_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")
