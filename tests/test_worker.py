"""Tests for MeasurementWorker (no hardware required)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.tdam.core.state import AppState, ConnectionState
from src.tdam.core.worker import MeasurementWorker


class TestMeasurementWorker:
    def test_initial_state(self, tmp_path: Path) -> None:
        state = AppState()
        worker = MeasurementWorker(
            state=state,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
        )
        assert worker.vna_config is None
        assert state.connection is ConnectionState.DISCONNECTED

    def test_request_stop(self, tmp_path: Path) -> None:
        state = AppState()
        worker = MeasurementWorker(
            state=state,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
        )
        worker.request_stop()
        assert state.is_stop_requested()

    def test_disconnect_resets_state(self, tmp_path: Path) -> None:
        state = AppState()
        state.set_connection(ConnectionState.CONNECTED)
        worker = MeasurementWorker(
            state=state,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
        )
        worker.disconnect_instruments()
        assert state.connection is ConnectionState.DISCONNECTED

    def test_start_measurement_without_instruments(self, tmp_path: Path) -> None:
        state = AppState()
        worker = MeasurementWorker(
            state=state,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
        )
        error_handler = MagicMock()
        worker.error_occurred.connect(error_handler)

        worker.start_measurement("Test", 1, 180)
        error_handler.assert_called()

    def test_connect_trvna_failure_sets_error(self, tmp_path: Path) -> None:
        """When TRVNA fails to launch, state should be ERROR."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        # Write valid VNA config
        (config_dir / "vna_config.toml").write_text(
            "[vna]\n"
            "fstart_mhz = 50\nfstop_mhz = 400\nnpoints = 1001\n"
            "ifbw_hz = 1000\npower_dbm = -30\naverage = 1\n"
            "interval_s = 180\nmean_count = 10\nrefvalue = -40\n"
        )

        state = AppState()
        worker = MeasurementWorker(
            state=state,
            config_dir=config_dir,
            data_dir=tmp_path / "data",
        )

        error_handler = MagicMock()
        worker.error_occurred.connect(error_handler)
        conn_handler = MagicMock()
        worker.connection_status.connect(conn_handler)

        with (
            patch("src.tdam.core.worker.SessionDB") as mock_db_cls,
            patch("src.tdam.core.worker.ensure_trvna_running", side_effect=RuntimeError("TRVNA not found")),
        ):
            mock_db_cls.return_value = MagicMock()
            worker.connect_instruments("127.0.0.1")

        assert state.connection is ConnectionState.ERROR
        error_handler.assert_called_once()
        conn_handler.assert_called_once_with(False, False)

    def test_connect_serial_failure_sets_error(self, tmp_path: Path) -> None:
        """When serial discovery fails, state should be ERROR."""
        from src.tdam.core.serial_device import SerialError

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "vna_config.toml").write_text(
            "[vna]\n"
            "fstart_mhz = 50\nfstop_mhz = 400\nnpoints = 1001\n"
            "ifbw_hz = 1000\npower_dbm = -30\naverage = 1\n"
            "interval_s = 180\nmean_count = 10\nrefvalue = -40\n"
        )

        state = AppState()
        worker = MeasurementWorker(
            state=state,
            config_dir=config_dir,
            data_dir=tmp_path / "data",
        )

        error_handler = MagicMock()
        worker.error_occurred.connect(error_handler)

        mock_vna = MagicMock()
        mock_vna.connect.return_value = "VNA IDN"
        mock_vna.get_temperature.return_value = 25.0

        with (
            patch("src.tdam.core.worker.SessionDB") as mock_db_cls,
            patch("src.tdam.core.worker.ensure_trvna_running"),
            patch("src.tdam.core.worker.VNAClient", return_value=mock_vna),
            patch("src.tdam.core.worker.SerialDevice.discover", side_effect=SerialError("No STM32")),
            patch("time.sleep"),
        ):
            mock_db_cls.return_value = MagicMock()
            worker.connect_instruments("127.0.0.1")

        assert state.connection is ConnectionState.ERROR
        error_handler.assert_called_once()

    def test_disconnect_logs_before_close(self, tmp_path: Path) -> None:
        """Verify logger.log is called before _close_all nullifies it."""
        state = AppState()
        state.set_connection(ConnectionState.CONNECTED)
        worker = MeasurementWorker(
            state=state,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
        )
        mock_logger = MagicMock()
        worker._logger = mock_logger

        worker.disconnect_instruments()

        mock_logger.log.assert_called_with("CONNECT ALL: disconnected")
        assert state.connection is ConnectionState.DISCONNECTED

    def test_start_measurement_guards_vna_config(self, tmp_path: Path) -> None:
        """start_measurement should error if _vna_config is None."""
        state = AppState()
        worker = MeasurementWorker(
            state=state,
            config_dir=tmp_path / "config",
            data_dir=tmp_path / "data",
        )
        # Set instruments but not config
        worker._vna = MagicMock()
        worker._serial = MagicMock()
        worker._logger = MagicMock()
        worker._vna_config = None

        error_handler = MagicMock()
        worker.error_occurred.connect(error_handler)

        worker.start_measurement("Test", 1, 180)
        error_handler.assert_called_once()
