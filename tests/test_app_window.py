import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton

from ffmpeg_gui.app import MainWindow


def test_main_window_hides_diagnostic_panels(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    group_titles = {group.title() for group in window.findChildren(QGroupBox)}
    button_texts = {button.text() for button in window.findChildren(QPushButton)}

    assert "Media Info" not in group_titles
    assert "Command" not in group_titles
    assert "FFmpeg Log" not in group_titles
    assert "Probe Media" not in button_texts
    assert "Preview Command" not in button_texts

    window.close()
    app.processEvents()
