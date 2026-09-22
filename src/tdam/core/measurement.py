"""Measurement sequence orchestration"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from .config import CommandType, MeasCommand, VNAConfig
from .logger import TDAMLogger
from .serial_device import SerialDevice
from .state import AppState
from .vna_client import MeasurementData, VNAClient

# Commands that only need serial dispatch + log (no special handling)
_SIMPLE_DISPATCH = frozenset({
    CommandType.RS, CommandType.TM, CommandType.GC, CommandType.SR,
})


@dataclass
class MeasurementResult:
    """Aggregated result of one full measurement sequence."""

    measure_id: str
    place: str
    data_blocks: list[MeasurementData] = field(default_factory=list)
    antenna_configs: list[str] = field(default_factory=list)
    finished_clean: bool = False  # True if the sequence ran to the end without a stop request


def new_measure_id() -> str:
    """Generate a timestamp-based measure ID: YYYY-MM-DD_HH-MM-SS_mmm (local time)."""
    return datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%f")[:23]


@dataclass
class _BlockState:
    """Mutable bookkeeping carried across commands within one sequence block."""

    config_all_ok: bool = True
    current_antennas: list[str] = field(default_factory=list)
    sa_without_ca_warned: bool = False


class MeasurementSequence:
    """Executes the measurement command sequence from meas_config.toml.

    Dispatches commands to the serial device and VNA.
    """

    def __init__(
        self,
        serial: SerialDevice,
        vna: VNAClient,
        commands: list[list[MeasCommand]],
        config: VNAConfig,
        state: AppState,
        logger: TDAMLogger,
        place: str = "",
    ) -> None:
        self._serial = serial
        self._vna = vna
        self._commands = commands
        self._config = config
        self._state = state
        self._logger = logger
        self._place = place

    def run(self) -> MeasurementResult:
        """Execute the full measurement sequence.

        Returns a *MeasurementResult* with all acquired data.
        """
        measure_id = new_measure_id()
        result = MeasurementResult(measure_id=measure_id, place=self._place)

        self._logger.log_marker(f"#START_MEASURE\tID\t{measure_id}")

        block = _BlockState()
        for seq_block in self._commands:
            if self._state.is_stop_requested():
                self._logger.log("Sequence interrupted by user")
                break

            for cmd in seq_block:
                if self._state.is_stop_requested():
                    self._logger.log("Stop during config")
                    break
                self._dispatch(cmd, result, measure_id, block)

        if not self._commands:
            self._logger.log("No configuration sent and no measurement done")

        # Skip the trailing marker (and its file flush + DB insert) when the
        # app is closing — the worker's finally block will also skip session_end.
        if not self._state.is_shutdown_requested():
            self._logger.log_marker("#STOP_MEASURE")

        return replace(result, finished_clean=not self._state.is_stop_requested())

    # ── Command dispatch ────────────────────────────────────────────

    def _dispatch(
        self,
        cmd: MeasCommand,
        result: MeasurementResult,
        measure_id: str,
        block: _BlockState,
    ) -> None:
        if cmd.kind in _SIMPLE_DISPATCH:
            resp = self._dispatch_serial(cmd.raw)
            self._logger.log(f"{cmd.kind.name}-->{resp}")

        elif cmd.kind is CommandType.CA:
            self._handle_ca(cmd, block)

        elif cmd.kind is CommandType.SA:
            self._handle_sa(result, measure_id, block)

        elif cmd.kind in (CommandType.TS, CommandType.TC):
            self._dispatch_serial(cmd.raw)

    def _handle_ca(self, cmd: MeasCommand, block: _BlockState) -> None:
        resp = self._dispatch_serial(cmd.raw)
        ok = "success" in resp.lower() and "antenna configured" in resp.lower()
        block.config_all_ok = block.config_all_ok and ok
        block.current_antennas.append(cmd.raw)
        self._logger.log(f"{cmd.raw}-->{resp}")
        if not ok:
            self._logger.log(
                f"CONFIG FAIL: {cmd.raw} --> {resp}",
                level="ERROR",
                error_type="COMMAND_FAIL",
            )

    def _handle_sa(
        self,
        result: MeasurementResult,
        measure_id: str,
        block: _BlockState,
    ) -> None:
        self._dispatch_serial("SA")
        if not block.current_antennas:
            msg = "SA without preceding CA — no antenna configured"
            if not block.sa_without_ca_warned:
                self._logger.warn_ui(msg)
                block.sa_without_ca_warned = True
            else:
                self._logger.log(msg, level="WARNING")

        if block.config_all_ok:
            self._do_vna_measurement(result, measure_id, block.current_antennas)
        else:
            self._logger.log(
                "NO measure done due to config fail",
                level="WARNING",
            )

        # Reset for next block
        block.config_all_ok = True
        block.current_antennas = []

    def _dispatch_serial(self, cmd: str) -> str:
        try:
            return self._serial.send_command(cmd)
        except Exception as exc:
            self._logger.log(
                f"Serial error for {cmd}: {exc}",
                level="ERROR",
                error_type="SERIAL_TIMEOUT",
            )
            return f"No response to {cmd}"

    def _do_vna_measurement(
        self,
        result: MeasurementResult,
        measure_id: str,
        antennas: list[str],
    ) -> None:
        try:
            self._vna.assert_ready(timeout_s=3)
        except Exception as exc:
            self._logger.log(
                f"VNA NOT READY -> measure aborted: {exc}",
                level="ERROR",
                error_type="VNA_SCPI_ERROR",
            )
            self._state.request_stop()
            return

        self._logger.log(f"VNA MEAS START id={measure_id}")

        try:
            data = self._vna.trigger_and_read(
                self._config.npoints, self._config.mean_count
            )
            result.data_blocks.append(data)
            result.antenna_configs.append(" ".join(antennas))
        except Exception as exc:
            self._logger.log(
                f"VNA measurement error: {exc}",
                level="ERROR",
                error_type="VNA_SCPI_ERROR",
            )
            return

        self._logger.log(f"VNA MEAS END id={measure_id}")


def save_tsv(result: MeasurementResult, output_dir: Path) -> Path:
    """Write measurement results to a TSV file (matching MATLAB format)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{result.measure_id}.tsv"

    with open(path, "w", encoding="utf-8") as f:
        lines: list[str] = [f"#START_MEASURE\t{result.place}"]

        for data, antennas in zip(
            result.data_blocks, result.antenna_configs, strict=False
        ):
            lines.append(f"{antennas} ")

            # Column header — full 2-port: S11, S21, S12(=S21), S22(=S11)
            n_repetitions = data.s21.shape[1]
            hdr = ["freq_Hz"]
            for j in range(1, n_repetitions + 1):
                hdr.extend([
                    f"S11_{j}_re", f"S11_{j}_im",
                    f"S21_{j}_re", f"S21_{j}_im",
                    f"S12_{j}_re", f"S12_{j}_im",
                    f"S22_{j}_re", f"S22_{j}_im",
                ])
            lines.append("\t".join(hdr))

            # Data rows — reciprocity assumption: S12=S21, S22=S11
            for k in range(len(data.freq_hz)):
                parts = [f"{data.freq_hz[k]:.12g}"]
                for j in range(n_repetitions):
                    s11 = data.s11[k, j]
                    s21 = data.s21[k, j]
                    parts.extend([
                        f"{s11.real:.12g}", f"{s11.imag:.12g}",
                        f"{s21.real:.12g}", f"{s21.imag:.12g}",
                        f"{s21.real:.12g}", f"{s21.imag:.12g}",
                        f"{s11.real:.12g}", f"{s11.imag:.12g}",
                    ])
                lines.append("\t".join(parts))
            lines.append("end acquisition")

        lines.append("#STOP_MEASURE")
        f.write("\n".join(lines) + "\n")

    return path
