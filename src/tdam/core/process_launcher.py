"""TRVNA.exe process management."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


class TRVNAError(Exception):
    """Raised when TRVNA cannot be started."""


# Only paths under one of these roots may be launched. Reading the path from
# a TOML config file makes it user-controllable, so an attacker who can write
# to trvna_path.toml could otherwise turn TDAM into a code-execution sink.
_ALLOWED_TRVNA_ROOTS: tuple[Path, ...] = (
    Path(r"C:\VNA"),
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
)


def _is_allowed_trvna_path(path: Path) -> bool:
    """True if *path* resolves under one of the allow-listed roots."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in _ALLOWED_TRVNA_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def is_process_running(exe_name: str) -> bool:
    """Check if a Windows process with *exe_name* is running."""
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return exe_name.lower() in result.stdout.lower()
    except (subprocess.SubprocessError, OSError):
        return False


def ensure_trvna_running(exe_path: Path) -> None:
    """Launch TRVNA.exe if it is not already running.

    Raises *TRVNAError* if the executable is not found, is outside the
    allow-listed roots, or cannot be started.
    """
    if sys.platform != "win32":
        raise TRVNAError("Software only supported to work on Windows")

    if not _is_allowed_trvna_path(exe_path):
        raise TRVNAError(
            f"Refusing to launch TRVNA from disallowed path: {exe_path}. "
            f"Allowed roots: {', '.join(str(r) for r in _ALLOWED_TRVNA_ROOTS)}"
        )

    exe_name = exe_path.name

    if is_process_running(exe_name):
        return

    if not exe_path.is_file():
        raise TRVNAError(f"TRVNA not found: {exe_path}")

    resolved = exe_path.resolve()
    print(f"[TDAM] Launching TRVNA from: {resolved}", file=sys.stderr)
    try:
        subprocess.Popen(
            [str(resolved)],
            creationflags=subprocess.DETACHED_PROCESS,
        )
    except OSError as exc:
        raise TRVNAError(f"Failed to launch TRVNA: {exc}") from exc
