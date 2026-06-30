"""Capture all application screens and tabs at 1280×800 into screens/v2/."""

import os
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QEventLoop

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.main_window import MainWindow  # noqa: E402
from app.i18n import i18n  # noqa: E402

PNG_DIR = os.path.join(ROOT, "screens", "v2", "png")
JPEG_DIR = os.path.join(ROOT, "screens", "v2", "jpeg")
W, H = 1280, 800


def wait_ms(app: QApplication, ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def save_shot(window: MainWindow, name: str, app: QApplication) -> None:
    wait_ms(app, 400)
    for _ in range(3):
        app.processEvents()
        wait_ms(app, 150)

    pix = window.grab()
    png_path = os.path.join(PNG_DIR, f"{name}.png")
    jpeg_path = os.path.join(JPEG_DIR, f"{name}.jpeg")
    pix.save(png_path)
    pix.save(jpeg_path, "JPEG", quality=92)
    print(f"  saved {name}")


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    i18n.set_language("ru")

    window = MainWindow()
    window.resize(W, H)
    window.show()
    app.processEvents()
    wait_ms(app, 300)

    def go(key: str) -> None:
        window._switch_screen(key)
        window._nav.set_active(key)
        app.processEvents()

    # ── Screens without tabs ────────────────────────────────────────────────
    simple = [
        ("main", "главный_экран"),
        ("patient", "пациент"),
        ("eit_settings", "настройки_эит"),
        ("reports", "отчеты"),
        ("export", "экспорт_данных"),
        ("service", "служебная_информация"),
        ("system", "системная_информация"),
        ("debug", "отладка_и_тестирование"),
    ]
    for key, name in simple:
        go(key)
        save_shot(window, name, app)

    # ── Trends (3 tabs) ───────────────────────────────────────────────────────
    trends = window._screens["trends"]
    go("trends")
    trends.tab_bar._on(0)
    save_shot(window, "тренды_глобальная_аэрация", app)

    trends.tab_bar._on(1)
    trends.tab_regional._switch("R")
    save_shot(window, "тренды_регионарная_аэрация", app)

    trends.tab_bar._on(2)
    save_shot(window, "тренды_все_тренды_аэрации", app)

    # ── Analysis (3 tabs + 2 pathology sub-tabs) ────────────────────────────
    analysis = window._screens["analysis"]
    go("analysis")

    analysis._switch_tab(0)
    analysis._path_tab._switch_sub(0)
    save_shot(window, "анализ_тип_дыхания_pca", app)

    analysis._switch_tab(0)
    analysis._path_tab._switch_sub(1)
    save_shot(window, "анализ_тип_дыхания_усредненные", app)

    analysis._switch_tab(1)
    save_shot(window, "анализ_регионарная_аэрация", app)

    analysis._switch_tab(2)
    save_shot(window, "анализ_глобальная_аэрация", app)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
