"""TCP/SCPI client for Copper Mountain VNA (TR1300/1)."""

from __future__ import annotations

import socket
import sys
import time
from dataclasses import dataclass

import numpy as np

from .config import VNAConfig


class VNAError(Exception):
    """Raised on VNA communication failures."""


@dataclass
class MeasurementData:
    """Result of a single VNA measurement sweep set."""

    freq_hz: np.ndarray  # (N,) frequency points
    s21: np.ndarray  # (N, M) complex S21 — M repetitions
    s11: np.ndarray  # (N, M) complex S11 — M repetitions


class VNAClient:
    """TCP client for Copper Mountain VNA using SCPI commands.

    Parameters
    ----------
    host : str
        IP address of the VNA (default from config).
    port : int
        TCP port (5025).
    """

    NEWLINE = b"\n"

    def __init__(self, host: str, port: int = 5025) -> None:
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None

    # ── Connection ──────────────────────────────────────────────────

    def connect(self, timeout: float = 20.0, connect_timeout: float = 5.0) -> str:
        """Open TCP connection and return the VNA identification string."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(connect_timeout)
        try:
            sock.connect((self._host, self._port))
        except OSError as exc:
            sock.close()
            raise VNAError(
                f"TCP connection to {self._host}:{self._port} failed: {exc}"
            ) from exc
        sock.settimeout(timeout)
        self._sock = sock
        return self.query("*IDN?")

    def close(self) -> None:
        """Safely close the TCP connection (idempotent)."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError as exc:
                print(f"[TDAM] Error closing VNA socket: {exc}", file=sys.stderr)
            self._sock = None

    def __enter__(self) -> VNAClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Low-level SCPI I/O ──────────────────────────────────────────

    def _write(self, cmd: str) -> None:
        if self._sock is None:
            raise VNAError("Not connected")
        self._sock.sendall(cmd.encode() + self.NEWLINE)

    def _read_until_newline(self) -> str:
        """Read from socket until a newline character, accumulating partial reads."""
        if self._sock is None:
            raise VNAError("Not connected")
        buf = bytearray()
        while True:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise VNAError("Connection closed by VNA")
            buf.extend(chunk)
            if buf[-1:] == self.NEWLINE:
                break
        return buf.decode(errors="replace").strip()

    def write(self, cmd: str) -> None:
        """Send a SCPI command (no response expected)."""
        self._write(cmd)

    def query(self, cmd: str) -> str:
        """Send a SCPI command and return the response string."""
        self._write(cmd)
        return self._read_until_newline()

    def write_and_wait(self, cmd: str) -> None:
        """Send command then wait for completion via ``*OPC?``."""
        self._write(cmd)
        self._write("*OPC?")
        self._read_until_newline()  # consume the "1" response

    # ── High-level VNA operations ───────────────────────────────────

    def assert_ready(self, timeout_s: float = 12.0) -> None:
        """Poll ``SYST:READy?`` until the VNA reports ready."""
        self._write("*CLS")
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            resp = self.query("SYST:READy?")
            if resp.strip() == "1":
                return
            time.sleep(0.2)
        raise VNAError(f"VNA not ready after {timeout_s}s timeout")

    def assert_rf_on(self) -> None:
        """Verify RF output is enabled."""
        resp = self.query("OUTP?")
        val = resp.strip()
        if val != "1":
            raise VNAError(f"VNA RF is OFF (OUTP? = {val!r})")

    def output_on(self) -> None:
        self.write_and_wait("OUTP:STAT 1")

    def output_off(self) -> None:
        self.write_and_wait("OUTP:STAT 0")

    def get_id(self) -> str:
        return self.query("*IDN?")

    def get_temperature(self) -> float:
        """Read internal VNA temperature in Celsius."""
        self._write("*CLS")
        resp = self.query("SYSTem:TEMPerature:SENSor?")
        resp = resp.replace(",", ".")
        try:
            return float(resp)
        except ValueError:
            raise VNAError(f"Invalid temperature response: {resp!r}") from None

    def configure(self, cfg: VNAConfig) -> None:
        """Apply full VNA configuration"""
        self.write_and_wait("SYSTem:PRESet")
        self.write_and_wait("OUTP:STAT 0")
        self.write_and_wait("TRIG:SOUR INT")

        self.write_and_wait(f"SENS:FREQ:STAR {cfg.fstart_hz}")
        self.write_and_wait(f"SENS:FREQ:STOP {cfg.fstop_hz}")
        self.write_and_wait(f"SENS:SWE:POIN {cfg.npoints}")
        self.write_and_wait(f"SOUR:POW:LEV {cfg.power_dbm}")
        self.write_and_wait(f"SENS:BWID:RES {cfg.ifbw_hz}")

        # Trace 1: S21 for display
        self.write_and_wait("CALC:PAR1:DEF S21")
        # Trace 2: S21 for data readout (re/im)
        self.write_and_wait("CALC:PAR:COUN 2")
        self.write_and_wait("CALC:PAR2:DEF S21")
        self.write_and_wait("CALC:SEL:FORM SCOM")
        # Trace 3: S11 for data readout
        self.write_and_wait("CALC:PAR:COUN 3")
        self.write_and_wait("CALC:PAR3:DEF S11")
        self.write_and_wait("CALC:SEL:FORM SCOM")

        # Display setup
        self.write_and_wait("CALC1:PAR1:SEL")
        self.write_and_wait("DISP:WIND:MAX 1")

        # RF on
        self.write_and_wait("OUTP:STAT 1")
        self.write_and_wait(f"DISP:WIND:TRAC:Y:RLEV {cfg.refvalue}")

    def trigger_and_read(self, npoints: int, mean_count: int) -> MeasurementData:
        """Execute *mean_count* triggered sweeps and return the data.

        Frequency is read each sweep since it may change between iterations.
        """
        if mean_count < 1:
            raise VNAError(f"mean_count must be >= 1, got {mean_count}")

        s21_all = np.zeros((npoints, mean_count), dtype=complex)
        s11_all = np.zeros((npoints, mean_count), dtype=complex)
        freq = np.zeros(npoints, dtype=float)

        for k in range(mean_count):
            # Set trigger to bus mode
            self.write_and_wait("TRIG:SOUR BUS")
            # Single trigger + wait
            self.write_and_wait("TRIG:SING")

            # Read frequency data (changes between sweeps)
            freq_str = self.query("SENS:FREQuency:DATA?")
            # Double *OPC? sync: write_and_wait sends *OPC? internally,
            # so this issues *OPC? → *OPC? → read. The extra round-trip
            # ensures the VNA has fully committed the frequency data before
            # we proceed to read S-parameter traces.
            self.write_and_wait("*OPC?")
            freq = np.fromiter(
                (float(x) for x in freq_str.split(",")),
                dtype=float,
                count=npoints,
            )

            # Read S21 (trace 2)
            s21_str = self.query("CALC1:TRAC2:DATA:FDAT?")
            s21_raw = np.fromiter(
                (float(x) for x in s21_str.split(",")),
                dtype=float,
                count=npoints * 2,
            )
            s21_all[:, k] = np.conj(s21_raw[0::2] + 1j * s21_raw[1::2])

            # Read S11 (trace 3)
            s11_str = self.query("CALC1:TRAC3:DATA:FDAT?")
            s11_raw = np.fromiter(
                (float(x) for x in s11_str.split(",")),
                dtype=float,
                count=npoints * 2,
            )
            s11_all[:, k] = np.conj(s11_raw[0::2] + 1j * s11_raw[1::2])

            # Restore internal trigger
            self.write_and_wait("TRIG:SOUR INT")

        return MeasurementData(freq_hz=freq, s21=s21_all, s11=s11_all)
