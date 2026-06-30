"""Entry point — ЭИТ Монитор пациента (прототип)."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app.main_window import MainWindow


def main():
    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("ЭИТ Монитор пациента")
    app.setOrganizationName("EIT Medical")

    window = MainWindow()

    # 1280×800 — typical 12-inch monitor resolution
    screen = app.primaryScreen().geometry()
    w, h = 1280, 800
    window.resize(w, h)
    window.move((screen.width() - w) // 2, (screen.height() - h) // 2)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
