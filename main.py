"""Entry point — ЭИТ Монитор пациента (прототип)."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from app.config import AppConfig
from app.container import ApplicationContainer
from app.main_window import MainWindow
from app.technical_logging import configure_logging
from app.i18n import i18n, t


def main():
    # Enable high-DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(t("app_title"))
    app.setOrganizationName("EIT Medical")
    i18n.language_changed.connect(lambda _language: app.setApplicationName(t("app_title")))

    config = AppConfig.from_env()
    configure_logging(config)
    for diagnostic in config.diagnostics:
        print(f"Configuration: {diagnostic}", file=sys.stderr)
    container = ApplicationContainer.build(config)
    for diagnostic in container.startup_diagnostics[len(config.diagnostics):]:
        print(f"Startup: {diagnostic}", file=sys.stderr)
    window = MainWindow(container)

    # 1280×800 — typical 12-inch monitor resolution
    screen = app.primaryScreen().geometry()
    w, h = 1280, 800
    window.resize(w, h)
    window.move((screen.width() - w) // 2, (screen.height() - h) // 2)
    window.show()

    exit_code = app.exec()
    container.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
