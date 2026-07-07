from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, Slot
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QSpinBox,
    QStatusBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ffmpeg_gui.core import (
    build_extract_frames_by_count_command,
    build_extract_frames_by_interval_command,
    duration_seconds_from_probe,
    probe_media,
    resolve_tool,
)


IMAGE_FORMATS = ("png", "jpg", "webp")


class ProcessWorker(QObject):
    finished = Signal(int)
    failed = Signal(str)

    def __init__(self, command: list[str], log_path: Path, diagnostics: list[str] | None = None) -> None:
        super().__init__()
        self.command = command
        self.log_path = log_path
        self.diagnostics = diagnostics or []
        self.process: subprocess.Popen[str] | None = None

    @Slot()
    def run(self) -> None:
        started_at = datetime.now()
        start_time = time.perf_counter()
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8", errors="replace") as log_file:
                log_file.write("\n--- frame extraction ---\n")
                log_file.write(f"Started at: {started_at.isoformat(timespec='seconds')}\n")
                log_file.write(f"Command: {format_command(self.command)}\n")
                for line in self.diagnostics:
                    log_file.write(f"{line}\n")
                log_file.write("\n--- ffmpeg output ---\n")
                log_file.flush()

                self.process = subprocess.Popen(
                    self.command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                exit_code = self.process.wait()
                elapsed_seconds = time.perf_counter() - start_time
                log_file.write("\n--- summary ---\n")
                log_file.write(f"Finished at: {datetime.now().isoformat(timespec='seconds')}\n")
                log_file.write(f"Exit code: {exit_code}\n")
                log_file.write(f"Elapsed seconds: {elapsed_seconds:.3f}\n")

            self.finished.emit(exit_code)
        except Exception as exc:  # pragma: no cover - UI boundary
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        init_start = time.perf_counter()
        super().__init__()
        self.ffmpeg_path = resolve_tool("ffmpeg")
        self.ffprobe_path = resolve_tool("ffprobe")
        self.log_root = log_root()
        self.run_log_path = build_run_log_path(self.log_root)
        write_run_log(
            self.run_log_path,
            [
                "FFmpeg Frame Extractor run log",
                f"Started at: {datetime.now().isoformat(timespec='seconds')}",
                f"Working directory: {Path.cwd()}",
                f"Log root: {self.log_root}",
                f"ffmpeg: {self.ffmpeg_path}",
                f"ffprobe: {self.ffprobe_path}",
            ],
        )
        self.media_duration_seconds: float | None = None
        self.worker_thread: QThread | None = None
        self.worker: ProcessWorker | None = None
        self.current_log_path: Path | None = None
        self.prepare_diagnostics: list[str] = []

        self.setWindowTitle("FFmpeg Frame Extractor")
        self.resize(760, 520)
        self.setMinimumSize(680, 500)
        self._build_ui()
        self._apply_style()
        self._set_idle_state()
        append_run_log(self.run_log_path, f"Window initialized in {time.perf_counter() - init_start:.3f} seconds")

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QGridLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(12)

        main = QVBoxLayout()
        main.setSpacing(12)
        main.addWidget(self._build_files_group())
        main.addWidget(self._build_extraction_group())
        main.addWidget(self._build_progress_group())
        main.addLayout(self._build_actions_row())
        main.addStretch(1)
        layout.addLayout(main, 0, 0)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self._build_menu()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open input...", self)
        open_action.triggered.connect(self.pick_input)
        file_menu.addAction(open_action)

        output_action = QAction("Choose output folder...", self)
        output_action.triggered.connect(self.pick_output_dir)
        file_menu.addAction(output_action)

        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About FFmpeg paths", self)
        about_action.triggered.connect(self.show_about_paths)
        help_menu.addAction(about_action)

    def _build_files_group(self) -> QGroupBox:
        group = QGroupBox("Files")
        layout = QGridLayout(group)
        self.input_edit = QLineEdit()
        self.output_dir_edit = QLineEdit()

        input_btn = QPushButton("Browse...")
        input_btn.clicked.connect(self.pick_input)
        output_btn = QPushButton("Choose folder...")
        output_btn.clicked.connect(self.pick_output_dir)

        layout.addWidget(QLabel("Input video"), 0, 0)
        layout.addWidget(self.input_edit, 0, 1)
        layout.addWidget(input_btn, 0, 2)
        layout.addWidget(QLabel("Output folder"), 1, 0)
        layout.addWidget(self.output_dir_edit, 1, 1)
        layout.addWidget(output_btn, 1, 2)
        return group

    def _build_extraction_group(self) -> QGroupBox:
        group = QGroupBox("Frame extraction")
        layout = QFormLayout(group)

        self.mode_group = QButtonGroup(self)
        self.count_mode_radio = QRadioButton("By frame count")
        self.interval_mode_radio = QRadioButton("By time interval")
        self.count_mode_radio.setChecked(True)
        self.mode_group.addButton(self.count_mode_radio)
        self.mode_group.addButton(self.interval_mode_radio)
        self.count_mode_radio.toggled.connect(self.update_mode_state)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        self.count_mode_card = self._build_mode_card(
            self.count_mode_radio,
            "Auto spacing",
            "Pick the total number of images. The app spreads them evenly across the whole video.",
        )
        self.interval_mode_card = self._build_mode_card(
            self.interval_mode_radio,
            "Fixed interval",
            "Pick a seconds interval. The app saves one frame every N seconds.",
        )
        mode_row.addWidget(self.count_mode_card)
        mode_row.addWidget(self.interval_mode_card)

        self.frame_count_spin = QSpinBox()
        self.frame_count_spin.setRange(1, 100000)
        self.frame_count_spin.setValue(12)
        self.interval_seconds_spin = QSpinBox()
        self.interval_seconds_spin.setRange(1, 86400)
        self.interval_seconds_spin.setValue(5)

        self.prefix_edit = QLineEdit("frame")
        self.format_combo = QComboBox()
        self.format_combo.addItems(IMAGE_FORMATS)

        layout.addRow("Mode", mode_row)
        self.mode_inputs = QStackedWidget()
        self.mode_inputs.addWidget(self._build_spin_panel("Frame count", self.frame_count_spin))
        self.mode_inputs.addWidget(self._build_spin_panel("Every seconds", self.interval_seconds_spin))
        layout.addRow("Mode value", self.mode_inputs)
        layout.addRow("File prefix", self.prefix_edit)
        layout.addRow("Image format", self.format_combo)
        self.update_mode_state()
        return group

    def _build_mode_card(self, radio: QRadioButton, badge: str, description: str) -> QWidget:
        card = QWidget()
        card.setObjectName("modeCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event: radio.setChecked(True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)

        top_row = QHBoxLayout()
        top_row.addWidget(radio)
        top_row.addStretch(1)
        badge_label = QLabel(badge)
        badge_label.setObjectName("modeBadge")
        top_row.addWidget(badge_label)
        layout.addLayout(top_row)

        description_label = QLabel(description)
        description_label.setObjectName("modeDescription")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        return card

    def _build_spin_panel(self, label_text: str, spin: QSpinBox) -> QWidget:
        panel = QWidget()
        panel.setObjectName("modeInputPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.addWidget(QLabel(label_text))
        layout.addWidget(spin, 1)
        return panel

    def _build_actions_row(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        self.run_button = QPushButton("Extract Frames")
        self.run_button.clicked.connect(self.run_extract_frames)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_process)
        actions.addStretch(1)
        actions.addWidget(self.run_button)
        actions.addWidget(self.cancel_button)
        return actions

    def _build_progress_group(self) -> QGroupBox:
        group = QGroupBox("Progress")
        layout = QVBoxLayout(group)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        return group

    def _apply_style(self) -> None:
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f7f8fa; color: #17202a; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d7dce2;
                border-radius: 6px;
                margin-top: 10px;
                padding: 12px;
                font-weight: 600;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QWidget#modeCard {
                background: #f8fafc;
                border: 1px solid #c8ced6;
                border-radius: 6px;
            }
            QWidget#modeCard[selected="true"] {
                background: #eef6ff;
                border: 2px solid #1f6feb;
            }
            QLabel#modeBadge {
                background: #e7edf5;
                border: 1px solid #c8ced6;
                border-radius: 4px;
                color: #334155;
                font-size: 11px;
                font-weight: 700;
                padding: 2px 6px;
            }
            QWidget#modeCard[selected="true"] QLabel#modeBadge {
                background: #dbeafe;
                border-color: #93c5fd;
                color: #1e40af;
            }
            QLabel#modeDescription {
                color: #4b5563;
                font-weight: 400;
                line-height: 130%;
            }
            QWidget#modeInputPanel {
                background: #f8fafc;
                border: 1px solid #d7dce2;
                border-radius: 4px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #ffffff;
                border: 1px solid #c8ced6;
                border-radius: 4px;
                padding: 6px;
                selection-background-color: #2563eb;
            }
            QRadioButton { padding: 3px 0; font-weight: 700; }
            QPushButton {
                background: #1f6feb;
                color: #ffffff;
                border: 1px solid #1f6feb;
                border-radius: 4px;
                padding: 7px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #1a5fd0; }
            QPushButton:disabled { background: #b7c1ce; border-color: #b7c1ce; }
            QProgressBar { border: 1px solid #c8ced6; border-radius: 4px; height: 10px; text-align: center; }
            QProgressBar::chunk { background: #16a34a; }
            """
        )

    @Slot()
    def pick_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose input video")
        if path:
            self.input_edit.setText(path)
            self.media_duration_seconds = None
            if not self.output_dir_edit.text().strip():
                self.output_dir_edit.setText(str(Path(path).with_name(f"{Path(path).stem}_frames")))

    @Slot()
    def pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self.output_dir_edit.setText(path)

    @Slot()
    def update_mode_state(self) -> None:
        count_mode = self.count_mode_radio.isChecked()
        self.frame_count_spin.setEnabled(count_mode)
        self.interval_seconds_spin.setEnabled(not count_mode)
        self.mode_inputs.setCurrentIndex(0 if count_mode else 1)
        self.count_mode_card.setProperty("selected", count_mode)
        self.interval_mode_card.setProperty("selected", not count_mode)
        self.count_mode_card.style().unpolish(self.count_mode_card)
        self.count_mode_card.style().polish(self.count_mode_card)
        self.interval_mode_card.style().unpolish(self.interval_mode_card)
        self.interval_mode_card.style().polish(self.interval_mode_card)

    @Slot()
    def run_extract_frames(self) -> None:
        try:
            command = self._build_extract_command()
        except Exception as exc:
            self.show_error(str(exc))
            return
        output_dir = self._output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        self.current_log_path = self.run_log_path
        self.start_process(command, "Frame extraction started.", self.run_log_path, self.prepare_diagnostics)

    def _build_extract_command(self) -> list[str]:
        input_path = self._input_path()
        output_dir = self._output_dir()
        prefix = self.prefix_edit.text().strip() or "frame"
        image_format = self.format_combo.currentText()
        self.prepare_diagnostics = [
            f"Input path: {input_path}",
            f"Output directory: {output_dir}",
            f"Output prefix: {prefix}",
            f"Image format: {image_format}",
        ]

        if self.count_mode_radio.isChecked():
            self.prepare_diagnostics.append(f"Mode: frame count ({self.frame_count_spin.value()})")
            duration = self.media_duration_seconds
            if duration is None:
                probe_start = time.perf_counter()
                data = probe_media(self.ffprobe_path, input_path)
                probe_elapsed = time.perf_counter() - probe_start
                duration = duration_seconds_from_probe(data)
                self.media_duration_seconds = duration
                self.prepare_diagnostics.append(f"ffprobe elapsed seconds: {probe_elapsed:.3f}")
            else:
                self.prepare_diagnostics.append("ffprobe elapsed seconds: cached")
            self.prepare_diagnostics.append(f"Media duration seconds: {duration:.3f}")
            return build_extract_frames_by_count_command(
                self.ffmpeg_path,
                input_path,
                output_dir,
                duration_seconds=duration,
                frame_count=self.frame_count_spin.value(),
                prefix=prefix,
                image_format=image_format,
            )

        self.prepare_diagnostics.append(f"Mode: interval seconds ({self.interval_seconds_spin.value()})")
        return build_extract_frames_by_interval_command(
            self.ffmpeg_path,
            input_path,
            output_dir,
            interval_seconds=self.interval_seconds_spin.value(),
            prefix=prefix,
            image_format=image_format,
        )

    def start_process(
        self,
        command: list[str],
        message: str,
        log_path: Path,
        diagnostics: list[str] | None = None,
    ) -> None:
        if self.worker_thread is not None:
            self.show_error("A job is already running.")
            return
        self.worker_thread = QThread()
        self.worker = ProcessWorker(command, log_path, diagnostics)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.process_finished)
        self.worker.failed.connect(self.process_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._clear_worker)
        self._set_busy_state()
        self.statusBar().showMessage(message)
        self.worker_thread.start()

    @Slot(int)
    def process_finished(self, exit_code: int) -> None:
        self._set_idle_state()
        if exit_code == 0:
            self.statusBar().showMessage(f"Frame extraction finished. Log: {self.current_log_path}")
        else:
            self.statusBar().showMessage(f"Job exited with code {exit_code}. Log: {self.current_log_path}")

    @Slot(str)
    def process_failed(self, message: str) -> None:
        self._set_idle_state()
        self.show_error(message)

    @Slot()
    def cancel_process(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.statusBar().showMessage("Cancel requested.")

    @Slot()
    def _clear_worker(self) -> None:
        self.worker_thread = None
        self.worker = None

    def _input_path(self) -> Path:
        text = self.input_edit.text().strip()
        if not text:
            raise ValueError("Choose an input video first.")
        path = Path(text)
        if not path.exists():
            raise ValueError("Input video does not exist.")
        return path

    def _output_dir(self) -> Path:
        text = self.output_dir_edit.text().strip()
        if not text:
            raise ValueError("Choose an output folder first.")
        return Path(text)

    def _set_busy_state(self) -> None:
        self.progress.setRange(0, 0)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def _set_idle_state(self) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QMessageBox.critical(self, "FFmpeg Frame Extractor", message)

    @Slot()
    def show_about_paths(self) -> None:
        QMessageBox.information(
            self,
            "FFmpeg paths",
            f"ffmpeg: {self.ffmpeg_path}\nffprobe: {self.ffprobe_path}",
        )


def format_command(command: list[str]) -> str:
    return " ".join(quote_arg(arg) for arg in command)


def build_run_log_path(output_dir: Path, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return output_dir / "logs" / f"run_{timestamp}.log"


def log_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def write_run_log(log_path: Path, lines: list[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_run_log(log_path: Path, line: str) -> None:
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{line}\n")


def quote_arg(arg: str) -> str:
    if not arg or any(char.isspace() for char in arg):
        return f'"{arg.replace(chr(34), chr(92) + chr(34))}"'
    return arg


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
