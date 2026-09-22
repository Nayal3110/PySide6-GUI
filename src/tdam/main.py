"""Entry point for the TDAM Acquisition Tool."""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from .ui.splash import show_splash


def _crash_log_path() -> Path:
    """Return the location for crash logs — next to the .exe or project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "crash.log"
    return Path(__file__).resolve().parent.parent.parent / "crash.log"


def _write_crash_log(tb: str) -> Path | None:
    """Append *tb* to the crash log; return the path or None on failure."""
    try:
        path = _crash_log_path()
        now = datetime.now().astimezone()
        ts = f"{now.strftime('%Y-%m-%d %H:%M:%S.')}{now.microsecond // 1000:03d}"
        offset = now.strftime("%z")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n─── CRASH {ts} {offset} ───\n{tb}\n")
        return path
    except OSError:
        return None


def _show_crash_dialog(tb: str, log_path: Path | None) -> None:
    """Surface an unrecoverable error to the user before exiting."""
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Critical)
    msg.setWindowTitle("TDAM — Fatal Error")
    msg.setText("TDAM encountered an unrecoverable error and must close.")
    detail = tb if log_path is None else f"{tb}\n\nFull log: {log_path}"
    msg.setDetailedText(detail)
    msg.exec()


def main() -> None:
    app = QApplication(sys.argv)

    try:
        splash = show_splash(app)

        from .ui.main_window import TDAMMainWindow

        window = TDAMMainWindow()
        window.show()
        splash.finish(window)

        sys.exit(app.exec())
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        log_path = _write_crash_log(tb)
        print(tb, file=sys.stderr)
        try:
            _show_crash_dialog(tb, log_path)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
