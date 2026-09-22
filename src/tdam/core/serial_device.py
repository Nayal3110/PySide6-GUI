"""Serial port discovery and STM32 command protocol."""

from __future__ import annotations

import sys
from collections.abc import Callable

import serial
import serial.tools.list_ports

SerialFactory = Callable[..., serial.Serial]
PortsLister = Callable[[], list]


class SerialError(Exception):
    """Raised on serial communication failures."""


class SerialDevice:
    """Wrapper around a serial connection to the PCB.

    Parameters
    ----------
    port : serial.Serial
        An already-open serial port instance (injectable for testing).
    """

    def __init__(self, port: serial.Serial) -> None:
        self._port = port

    @classmethod
    def discover(
        cls,
        baudrate: int = 115200,
        timeout: float = 1.0,
        *,
        _serial_factory: SerialFactory | None = None,
        _ports_lister: PortsLister | None = None,
    ) -> SerialDevice:
        """Scan all available COM ports for the PCB.

        The discovery sends ``SP`` and expects ``TSP`` in reply.

        ``_serial_factory`` and ``_ports_lister`` are testing seams — pass a
        callable returning a mock ``serial.Serial`` / list of port infos to
        unit-test discovery without touching real hardware.
        """
        open_serial = _serial_factory or serial.Serial
        list_ports = _ports_lister or serial.tools.list_ports.comports

        ports = list_ports()
        if not ports:
            raise SerialError("No serial ports available")

        for info in ports:
            port = None
            try:
                port = open_serial(
                    info.device,
                    baudrate=baudrate,
                    timeout=timeout,
                )
                port.reset_input_buffer()
                port.write(b"SP\n")

                resp = port.readline().decode(errors="replace").strip()
                if resp == "TSP":
                    return cls(port)

                port.close()
            except (serial.SerialException, OSError) as exc:
                print(
                    f"[TDAM] Skipping serial port {info.device}: {exc}",
                    file=sys.stderr,
                )
                if port is not None:
                    try:
                        port.close()
                    except (serial.SerialException, OSError) as close_exc:
                        print(
                            f"[TDAM] Failed to close port {info.device}: {close_exc}",
                            file=sys.stderr,
                        )

        raise SerialError("PCB not found on any serial port")

    def send_command(self, cmd: str) -> str:
        """Send *cmd* and return the single-line response (stripped)."""
        if self._port is None or not self._port.is_open:
            raise SerialError("Serial port is not open")
        self._port.reset_input_buffer()
        self._port.write(f"{cmd}\n".encode())
        resp = self._port.readline().decode(errors="replace").strip()
        if not resp:
            raise SerialError(f"No response to command: {cmd!r}")
        return resp

    def close(self) -> None:
        """Safely close the serial connection (idempotent)."""
        if self._port is not None:
            try:
                if self._port.is_open:
                    self._port.close()
            except (serial.SerialException, OSError) as exc:
                print(f"[TDAM] Error closing serial port: {exc}", file=sys.stderr)
            self._port = None

    def __enter__(self) -> SerialDevice:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
