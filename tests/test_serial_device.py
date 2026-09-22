"""Tests for serial device communication."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.tdam.core.serial_device import SerialDevice, SerialError


class TestSerialDevice:
    def test_send_command(self) -> None:
        mock_port = MagicMock()
        mock_port.is_open = True
        mock_port.readline.return_value = b"OK\n"
        dev = SerialDevice(mock_port)

        resp = dev.send_command("RS")
        mock_port.write.assert_called_once_with(b"RS\n")
        assert resp == "OK"

    def test_send_command_no_response(self) -> None:
        mock_port = MagicMock()
        mock_port.is_open = True
        mock_port.readline.return_value = b""
        dev = SerialDevice(mock_port)

        with pytest.raises(SerialError, match="No response"):
            dev.send_command("RS")

    def test_send_command_port_closed(self) -> None:
        mock_port = MagicMock()
        mock_port.is_open = False
        dev = SerialDevice(mock_port)

        with pytest.raises(SerialError, match="not open"):
            dev.send_command("RS")

    def test_close_idempotent(self) -> None:
        mock_port = MagicMock()
        mock_port.is_open = True
        dev = SerialDevice(mock_port)

        dev.close()
        dev.close()  # should not raise
        mock_port.close.assert_called_once()

    def test_context_manager(self) -> None:
        mock_port = MagicMock()
        mock_port.is_open = True
        with SerialDevice(mock_port):
            pass
        mock_port.close.assert_called_once()

    def test_discover_no_ports(self) -> None:
        with patch("src.tdam.core.serial_device.serial.tools.list_ports.comports", return_value=[]):
            with pytest.raises(SerialError, match="No serial ports"):
                SerialDevice.discover()

    def test_discover_finds_device(self) -> None:
        mock_port_info = MagicMock()
        mock_port_info.device = "COM3"

        mock_serial = MagicMock()
        mock_serial.readline.return_value = b"TSP\n"

        with patch("src.tdam.core.serial_device.serial.tools.list_ports.comports", return_value=[mock_port_info]):
            with patch("src.tdam.core.serial_device.serial.Serial", return_value=mock_serial):
                dev = SerialDevice.discover()
                assert dev is not None
                mock_serial.write.assert_called_once_with(b"SP\n")

    def test_discover_wrong_response(self) -> None:
        mock_port_info = MagicMock()
        mock_port_info.device = "COM3"

        mock_serial = MagicMock()
        mock_serial.readline.return_value = b"WRONG\n"

        with patch("src.tdam.core.serial_device.serial.tools.list_ports.comports", return_value=[mock_port_info]):
            with patch("src.tdam.core.serial_device.serial.Serial", return_value=mock_serial):
                with pytest.raises(SerialError, match="not found"):
                    SerialDevice.discover()


class TestSerialDeviceFactoryInjection:
    """Discovery via the ``_serial_factory`` / ``_ports_lister`` testing seams."""

    def _port_info(self, device: str) -> MagicMock:
        info = MagicMock()
        info.device = device
        return info

    def test_discover_with_injected_factory_finds_device(self) -> None:
        info = self._port_info("COM7")

        port = MagicMock()
        port.readline.return_value = b"TSP\n"
        factory = MagicMock(return_value=port)

        dev = SerialDevice.discover(
            _serial_factory=factory,
            _ports_lister=lambda: [info],
        )

        assert dev is not None
        factory.assert_called_once_with("COM7", baudrate=115200, timeout=1.0)
        port.write.assert_called_once_with(b"SP\n")

    def test_discover_with_injected_factory_no_ports(self) -> None:
        with pytest.raises(SerialError, match="No serial ports"):
            SerialDevice.discover(
                _serial_factory=MagicMock(),
                _ports_lister=lambda: [],
            )

    def test_discover_skips_port_that_raises_and_tries_next(self) -> None:
        bad_info = self._port_info("COM1")
        good_info = self._port_info("COM2")

        good_port = MagicMock()
        good_port.readline.return_value = b"TSP\n"

        import serial as _serial

        def factory(device: str, **_: object):
            if device == "COM1":
                raise _serial.SerialException("busy")
            return good_port

        dev = SerialDevice.discover(
            _serial_factory=factory,
            _ports_lister=lambda: [bad_info, good_info],
        )

        assert dev is not None
        good_port.write.assert_called_once_with(b"SP\n")

    def test_discover_closes_port_when_response_wrong(self) -> None:
        info = self._port_info("COM3")

        port = MagicMock()
        port.readline.return_value = b"WRONG\n"

        with pytest.raises(SerialError, match="not found"):
            SerialDevice.discover(
                _serial_factory=lambda *a, **kw: port,
                _ports_lister=lambda: [info],
            )
        port.close.assert_called_once()

    def test_discover_passes_custom_baudrate_and_timeout(self) -> None:
        info = self._port_info("COM4")

        port = MagicMock()
        port.readline.return_value = b"TSP\n"
        factory = MagicMock(return_value=port)

        SerialDevice.discover(
            baudrate=9600,
            timeout=0.5,
            _serial_factory=factory,
            _ports_lister=lambda: [info],
        )

        factory.assert_called_once_with("COM4", baudrate=9600, timeout=0.5)
