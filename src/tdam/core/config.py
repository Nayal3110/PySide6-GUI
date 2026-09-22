"""Configuration file parsing."""

from __future__ import annotations

import shutil
import sys
import tomllib
from dataclasses import dataclass, fields
from enum import Enum, auto
from pathlib import Path
from typing import Self, get_type_hints


class ConfigError(Exception):
    """Raised when a configuration file is malformed or missing."""


# ── VNA configuration ───────────────────────────────────────────────


@dataclass(frozen=True)
class VNAConfig:
    fstart_mhz: float
    fstop_mhz: float
    npoints: int
    ifbw_hz: float
    power_dbm: float
    average: int
    interval_s: int
    mean_count: int
    refvalue: int

    @property
    def fstart_hz(self) -> float:
        return self.fstart_mhz * 1e6

    @property
    def fstop_hz(self) -> float:
        return self.fstop_mhz * 1e6


# Field names expected in the [vna] table of the TOML config.
_VNA_FIELDS: set[str] = {f.name for f in fields(VNAConfig) if not f.name.startswith("_")}

# Type coercions derived from VNAConfig annotations — adding/renaming a field
# updates this automatically, no parallel set to maintain.
_VNA_HINTS = get_type_hints(VNAConfig)
_INT_FIELDS: set[str] = {
    f.name for f in fields(VNAConfig) if _VNA_HINTS.get(f.name) is int
}


def load_vna_config(path: Path) -> VNAConfig:
    """Parse a TOML VNA config file into a `VNAConfig`.

    Expects a *vna* table whose keys match the `VNAConfig` field
    names exactly ("fstart_mhz", "npoints", "ifbw_hz", etc.).
    Extra keys are silently ignored; missing required keys raise a
    'ConfigError' that lists the accepted field names.
    """
    if not path.is_file():
        raise ConfigError(f"VNA config file not found: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path.name}: {exc}") from exc

    vna = data.get("vna")
    if not isinstance(vna, dict):
        raise ConfigError(
            f"VNA config must contain a [vna] table (found: {type(vna).__name__})"
        )

    missing = _VNA_FIELDS - set(vna.keys())
    if missing:
        raise ConfigError(
            f"VNA config is missing {len(missing)} required field(s): "
            f"{', '.join(sorted(missing))}. "
            f"Accepted fields: {', '.join(sorted(_VNA_FIELDS))}"
        )

    values: dict[str, float | int] = {}
    for name in _VNA_FIELDS:
        raw = vna[name]
        try:
            values[name] = int(raw) if name in _INT_FIELDS else float(raw)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Field '{name}' must be numeric, got {raw!r}") from exc

    return VNAConfig(**values)


# ── Measurement commands ────────────────────────────────────────────


class CommandType(Enum):
    RS = auto()  # Reset
    TM = auto()  # Temperature / pressure / humidity
    GC = auto()  # Get current
    SA = auto()  # Set antenna (triggers VNA measurement)
    SR = auto()  # Search ROM
    TS = auto()  # Test serial (debug)
    TC = auto()  # Test current (debug)
    CA = auto()  # Configure antenna (with spec string)


@dataclass(frozen=True)
class MeasCommand:
    kind: CommandType
    raw: str  # The full command string sent over serial (e.g. "CA-T1AA")

    @classmethod
    def parse(cls, token: str) -> Self:
        token = token.strip()
        if not token:
            raise ConfigError("Empty command token")

        if token.startswith("CA-"):
            return cls(kind=CommandType.CA, raw=token)

        try:
            kind = CommandType[token]
        except KeyError:
            raise ConfigError(f"Unknown command: {token!r}") from None

        return cls(kind=kind, raw=token)


def load_meas_config(path: Path) -> list[list[MeasCommand]]:
    """Parse a TOML measurement config file into command sequences.

    Expects a ``measurement`` table with a sequences key — an array
    of string arrays, where each inner array is one PCB command sequence::

        [measurement]
        sequences = [
            ["RS"],
            ["CA-T1AA", "CA-R2AA", "SA"],
        ]

    Empty inner arrays are silently skipped.
    """
    if not path.is_file():
        raise ConfigError(f"Measurement config file not found: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path.name}: {exc}") from exc

    measurement = data.get("measurement")
    if not isinstance(measurement, dict):
        raise ConfigError(
            "Measurement config must contain a [measurement] table"
        )

    raw_sequences = measurement.get("sequences")
    if not isinstance(raw_sequences, list):
        raise ConfigError(
            "'measurement.sequences' must be an array of command arrays"
        )

    sequences: list[list[MeasCommand]] = []
    for i, seq in enumerate(raw_sequences):
        if not isinstance(seq, list):
            raise ConfigError(
                f"Sequence {i} must be an array of command strings, got {type(seq).__name__}"
            )
        commands = [MeasCommand.parse(str(token)) for token in seq if str(token).strip()]
        if commands:
            sequences.append(commands)

    return sequences


# ── TRVNA path ──────────────────────────────────────────────────────

_TRVNA_DEFAULT = Path(r"C:\VNA\TRVNA\TRVNA.exe")


def load_trvna_path(path: Path) -> Path:
    """Read the TRVNA executable path from a TOML config file.

    Expects a ``trvna`` table with a ``path`` string key::

        [trvna]
        path = 'C:\\VNA\\TRVNA\\TRVNA.exe'

    Returns the default path if the file is missing or malformed.
    """
    if not path.is_file():
        return _TRVNA_DEFAULT
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return _TRVNA_DEFAULT
    trvna = data.get("trvna", {})
    exe = trvna.get("path", "")
    return Path(exe) if exe else _TRVNA_DEFAULT


# ── Default config bootstrapping ────────────────────────────────────

# config.py lives at src/tdam/core/config.py — project root is 4 levels up
_SRC_DIR = Path(__file__).resolve().parents[2]  # src/
_PROJECT_ROOT = _SRC_DIR.parent                 # project root
_BUNDLED_CONFIG_DIR = _PROJECT_ROOT / "config"


def ensure_default_configs(target_dir: Path) -> None:
    """Copy bundled default configs to *target_dir* if they don't exist.

    A missing bundle file is reported on stderr rather than silently skipped
    — the caller will hit a ``ConfigError`` later, this gives the real cause.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    for name in ("vna_config.toml", "meas_config.toml", "trvna_path.toml"):
        dest = target_dir / name
        if dest.exists():
            continue
        src = _BUNDLED_CONFIG_DIR / name
        if not src.is_file():
            print(
                f"[TDAM] Bundled default config missing: {src}",
                file=sys.stderr,
            )
            continue
        shutil.copy2(src, dest)
