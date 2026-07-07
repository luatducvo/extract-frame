from pathlib import Path

import pytest

from ffmpeg_gui.core import (
    build_extract_frames_by_count_command,
    build_extract_frames_by_interval_command,
    build_screenshot_command,
    duration_seconds_from_probe,
    resolve_tool,
    summarize_probe,
)


def test_resolve_tool_prefers_bundled_binary(tmp_path: Path) -> None:
    bin_dir = tmp_path / "ffmpeg-8.1.2-essentials_build" / "bin"
    bin_dir.mkdir(parents=True)
    ffmpeg = bin_dir / "ffmpeg.exe"
    ffmpeg.write_text("", encoding="utf-8")

    assert resolve_tool("ffmpeg", tmp_path) == ffmpeg


def test_build_screenshot_command_seeks_and_writes_one_frame(tmp_path: Path) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "frame.png"

    command = build_screenshot_command(Path("ffmpeg.exe"), input_path, output_path, "00:00:05")

    assert command == [
        "ffmpeg.exe",
        "-hide_banner",
        "-y",
        "-ss",
        "00:00:05",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        str(output_path),
    ]


def test_build_extract_frames_by_count_uses_duration_to_space_frames(tmp_path: Path) -> None:
    input_path = tmp_path / "input.mp4"
    output_dir = tmp_path / "frames"

    command = build_extract_frames_by_count_command(
        Path("ffmpeg.exe"),
        input_path,
        output_dir,
        duration_seconds=100,
        frame_count=5,
        prefix="scene",
    )

    assert command == [
        "ffmpeg.exe",
        "-hide_banner",
        "-benchmark",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "fps=1/20",
        "-frames:v",
        "5",
        str(output_dir / "scene_%04d.png"),
    ]


def test_build_extract_frames_by_interval_uses_user_seconds(tmp_path: Path) -> None:
    input_path = tmp_path / "input.mp4"
    output_dir = tmp_path / "frames"

    command = build_extract_frames_by_interval_command(
        Path("ffmpeg.exe"),
        input_path,
        output_dir,
        interval_seconds=5,
        prefix="frame",
    )

    assert command == [
        "ffmpeg.exe",
        "-hide_banner",
        "-benchmark",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        "fps=1/5",
        str(output_dir / "frame_%04d.png"),
    ]


def test_extract_frames_rejects_invalid_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        build_extract_frames_by_count_command(
            Path("ffmpeg.exe"),
            tmp_path / "input.mp4",
            tmp_path / "frames",
            duration_seconds=60,
            frame_count=0,
        )


def test_duration_seconds_from_probe_reads_format_duration() -> None:
    assert duration_seconds_from_probe({"format": {"duration": "12.75"}}) == 12.75


def test_summarize_probe_formats_stream_information() -> None:
    summary = summarize_probe(
        {
            "format": {
                "format_name": "mov,mp4",
                "duration": "62.4",
                "size": "1048576",
                "bit_rate": "800000",
            },
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30/1",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                    "sample_rate": "48000",
                },
            ],
        }
    )

    assert "Duration: 00:01:02" in summary
    assert "Size: 1.0 MB" in summary
    assert "Stream #0: video - h264 (1920x1080, 30/1 fps)" in summary
    assert "Stream #1: audio - aac (2 ch, 48000 Hz)" in summary
