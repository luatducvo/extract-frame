import sys
from datetime import datetime
from pathlib import Path

from ffmpeg_gui.app import ProcessWorker, build_run_log_path, log_root
from ffmpeg_gui.app import format_command


def test_format_command_quotes_arguments_with_spaces() -> None:
    assert format_command(["ffmpeg.exe", "-i", "C:/Media/input file.mp4"]) == (
        'ffmpeg.exe -i "C:/Media/input file.mp4"'
    )


def test_build_run_log_path_uses_app_logs_folder(tmp_path) -> None:
    log_path = build_run_log_path(tmp_path, datetime(2026, 7, 7, 8, 9, 10))

    assert log_path == tmp_path / "logs" / "run_20260707_080910.log"


def test_log_root_uses_executable_folder_when_frozen(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\FFmpegDesktopGUI\FFmpegDesktopGUI.exe")

    assert log_root() == Path(r"C:\Apps\FFmpegDesktopGUI")


def test_process_worker_appends_extract_details_to_run_log(tmp_path) -> None:
    log_path = tmp_path / "logs" / "run.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("Session header\n", encoding="utf-8")
    worker = ProcessWorker(
        [sys.executable, "-c", "print('worker output')"],
        log_path,
        diagnostics=["Mode: test"],
    )

    worker.run()

    content = log_path.read_text(encoding="utf-8")
    assert content.startswith("Session header\n")
    assert "Command:" in content
    assert "Mode: test" in content
    assert "worker output" in content
    assert "Exit code: 0" in content
    assert "Elapsed seconds:" in content
