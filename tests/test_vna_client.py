"""Tests for VNA TCP/SCPI client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.tdam.core.vna_client import VNAClient, VNAError


class FakeSocket:
    """Minimal socket mock that queues responses."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._sent: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self._sent.append(data)

    def recv(self, bufsize: int) -> bytes:
        if not self._responses:
            return b""
        return (self._responses.pop(0) + "\n").encode()

    def settimeout(self, t: float) -> None:
        pass

    def connect(self, addr: tuple) -> None:
        pass

    def close(self) -> None:
        pass


class TestVNAClient:
    def test_write_raises_when_not_connected(self) -> None:
        client = VNAClient("127.0.0.1")
        with pytest.raises(VNAError, match="Not connected"):
            client.write("*IDN?")

    def test_query(self) -> None:
        client = VNAClient("127.0.0.1")
        client._sock = FakeSocket(["Copper Mountain,TR1300"])
        resp = client.query("*IDN?")
        assert resp == "Copper Mountain,TR1300"

    def test_close_idempotent(self) -> None:
        client = VNAClient("127.0.0.1")
        client._sock = FakeSocket([])
        client.close()
        client.close()  # should not raise
        assert client._sock is None

    def test_assert_ready_success(self) -> None:
        client = VNAClient("127.0.0.1")
        # *CLS (no response expected by _write), then SYST:READy? query
        client._sock = FakeSocket(["1"])
        client.assert_ready(timeout_s=1)

    def test_assert_ready_timeout(self) -> None:
        client = VNAClient("127.0.0.1")
        client._sock = FakeSocket(["0", "0", "0", "0"])
        with pytest.raises(VNAError, match="not ready"):
            client.assert_ready(timeout_s=0.3)

    def test_get_temperature(self) -> None:
        client = VNAClient("127.0.0.1")
        client._sock = FakeSocket(["32,5"])
        temp = client.get_temperature()
        assert temp == 32.5

    def test_connect_failure(self) -> None:
        with patch("src.tdam.core.vna_client.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = OSError("refused")
            mock_sock_cls.return_value = mock_sock
            client = VNAClient("127.0.0.1")
            with pytest.raises(VNAError, match="TCP connection"):
                client.connect()

    def test_context_manager(self) -> None:
        with VNAClient("127.0.0.1") as client:
            client._sock = FakeSocket([])
        assert client._sock is None

    def test_trigger_and_read_parses_data(self) -> None:
        """Verify S-parameter reconstruction from CSV: np.conj(re + 1j*im)."""
        # For npoints=2, mean_count=1, the command sequence needs these responses:
        # write_and_wait("TRIG:SOUR BUS") → "1"
        # write_and_wait("TRIG:SING")     → "1"
        # query("SENS:FREQuency:DATA?")   → freq CSV
        # write_and_wait("*OPC?")         → "1"
        # query("CALC1:TRAC2:DATA:FDAT?") → S21 re,im pairs
        # query("CALC1:TRAC3:DATA:FDAT?") → S11 re,im pairs
        # write_and_wait("TRIG:SOUR INT") → "1"
        responses = [
            "1",                        # TRIG:SOUR BUS *OPC?
            "1",                        # TRIG:SING *OPC?
            "1000000,2000000",          # SENS:FREQuency:DATA?
            "1",                        # *OPC? (double sync)
            "1.0,2.0,3.0,4.0",         # CALC1:TRAC2:DATA:FDAT? — S21
            "0.1,0.2,0.3,0.4",         # CALC1:TRAC3:DATA:FDAT? — S11
            "1",                        # TRIG:SOUR INT *OPC?
        ]
        client = VNAClient("127.0.0.1")
        client._sock = FakeSocket(responses)

        data = client.trigger_and_read(npoints=2, mean_count=1)

        # Frequency
        np.testing.assert_array_equal(data.freq_hz, [1e6, 2e6])

        # S21: conj(1+2j) = 1-2j, conj(3+4j) = 3-4j
        np.testing.assert_array_almost_equal(data.s21[:, 0], [1 - 2j, 3 - 4j])

        # S11: conj(0.1+0.2j) = 0.1-0.2j, conj(0.3+0.4j) = 0.3-0.4j
        np.testing.assert_array_almost_equal(data.s11[:, 0], [0.1 - 0.2j, 0.3 - 0.4j])

    def test_trigger_and_read_invalid_mean_count(self) -> None:
        client = VNAClient("127.0.0.1")
        client._sock = FakeSocket([])
        with pytest.raises(VNAError, match="mean_count must be >= 1"):
            client.trigger_and_read(npoints=2, mean_count=0)
