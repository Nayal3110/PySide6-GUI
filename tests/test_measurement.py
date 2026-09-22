"""Tests for measurement sequence orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.tdam.core.config import CommandType, MeasCommand, VNAConfig
from src.tdam.core.measurement import (
    MeasurementResult,
    MeasurementSequence,
    new_measure_id,
    save_tsv,
)
from src.tdam.core.state import AppState
from src.tdam.core.vna_client import MeasurementData


@pytest.fixture
def mock_serial() -> MagicMock:
    m = MagicMock()
    m.send_command.return_value = "SUCCESS antenna configured"
    return m


@pytest.fixture
def mock_vna() -> MagicMock:
    from src.tdam.core.vna_client import VNAClient

    m = MagicMock(spec=VNAClient)
    m.assert_ready.return_value = None
    data = MeasurementData(
        freq_hz=np.array([1e6, 2e6]),
        s21=np.array([[1 + 2j], [3 + 4j]]),
        s11=np.array([[0.1 + 0.2j], [0.3 + 0.4j]]),
    )
    m.trigger_and_read.return_value = data
    return m


@pytest.fixture
def mock_logger() -> MagicMock:
    m = MagicMock()
    return m


@pytest.fixture
def simple_config() -> VNAConfig:
    return VNAConfig(
        fstart_mhz=50, fstop_mhz=400, npoints=2,
        ifbw_hz=1000, power_dbm=-30, average=1,
        interval_s=180, mean_count=1, refvalue=-40,
    )


class TestNewMeasureId:
    def test_format(self) -> None:
        mid = new_measure_id()
        # YYYY-MM-DD_HH-MM-SS_mmm — 23 chars
        assert len(mid) == 23
        assert mid[10] == "_"
        assert mid[19] == "_"


class TestMeasurementSequence:
    def test_empty_commands(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        state = AppState()
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=[], config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        assert result.finished_clean
        assert result.data_blocks == []
        mock_logger.log.assert_any_call("No configuration sent and no measurement done")

    def test_rs_command(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        state = AppState()
        commands = [[MeasCommand(kind=CommandType.RS, raw="RS")]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        mock_serial.send_command.assert_called_with("RS")
        assert result.finished_clean

    def test_ca_sa_sequence(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        state = AppState()
        commands = [[
            MeasCommand(kind=CommandType.CA, raw="CA-T1AA"),
            MeasCommand(kind=CommandType.CA, raw="CA-R2AA"),
            MeasCommand(kind=CommandType.SA, raw="SA"),
        ]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        assert len(result.data_blocks) == 1
        assert len(result.antenna_configs) == 1
        assert "CA-T1AA" in result.antenna_configs[0]

    def test_ca_fail_skips_measurement(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        mock_serial.send_command.return_value = "FAILURE"
        state = AppState()
        commands = [[
            MeasCommand(kind=CommandType.CA, raw="CA-T1AA"),
            MeasCommand(kind=CommandType.SA, raw="SA"),
        ]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        assert len(result.data_blocks) == 0
        mock_vna.trigger_and_read.assert_not_called()

    def test_vna_not_ready_aborts(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        """When VNA is not ready, measurement is aborted and stop is requested."""
        from src.tdam.core.vna_client import VNAError

        mock_vna.assert_ready.side_effect = VNAError("VNA not ready after 3s timeout")
        state = AppState()
        commands = [[
            MeasCommand(kind=CommandType.CA, raw="CA-T1AA"),
            MeasCommand(kind=CommandType.SA, raw="SA"),
        ]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        assert len(result.data_blocks) == 0
        mock_vna.trigger_and_read.assert_not_called()
        assert state.is_stop_requested()
        mock_logger.log.assert_any_call(
            "VNA NOT READY -> measure aborted: VNA not ready after 3s timeout",
            level="ERROR",
            error_type="VNA_SCPI_ERROR",
        )

    def test_vna_trigger_failure_skips_block(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        """When trigger_and_read raises, the data block is not appended."""
        mock_vna.trigger_and_read.side_effect = RuntimeError("SCPI timeout")
        state = AppState()
        commands = [[
            MeasCommand(kind=CommandType.CA, raw="CA-T1AA"),
            MeasCommand(kind=CommandType.SA, raw="SA"),
        ]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        assert len(result.data_blocks) == 0
        mock_logger.log.assert_any_call(
            "VNA measurement error: SCPI timeout",
            level="ERROR",
            error_type="VNA_SCPI_ERROR",
        )

    def test_sa_without_ca_warns(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        """SA without preceding CA should log a warning about no antenna configured."""
        state = AppState()
        commands = [[
            MeasCommand(kind=CommandType.SA, raw="SA"),
        ]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        seq.run()
        mock_logger.warn_ui.assert_called_once_with(
            "SA without preceding CA \u2014 no antenna configured"
        )

    def test_stop_interrupts(self, mock_serial, mock_vna, mock_logger, simple_config) -> None:
        state = AppState()
        state.try_start_measurement()
        state.request_stop()
        commands = [[MeasCommand(kind=CommandType.RS, raw="RS")]]
        seq = MeasurementSequence(
            serial=mock_serial, vna=mock_vna,
            commands=commands, config=simple_config,
            state=state, logger=mock_logger,
        )
        result = seq.run()
        assert not result.finished_clean


class TestSaveTsv:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        data = MeasurementData(
            freq_hz=np.array([1e6, 2e6]),
            s21=np.array([[1 + 2j], [3 + 4j]]),
            s11=np.array([[0.1 + 0.2j], [0.3 + 0.4j]]),
        )
        result = MeasurementResult(
            measure_id="20240101_120000_000",
            place="TestPlace",
            data_blocks=[data],
            antenna_configs=["CA-T1AA CA-R2AA"],
            finished_clean=True,
        )
        path = save_tsv(result, tmp_path / "measures")
        assert path.exists()
        content = path.read_text()
        assert "#START_MEASURE" in content
        assert "#STOP_MEASURE" in content
        assert "TestPlace" in content
        assert "freq_Hz" in content
        # Full 2-port S-parameter columns: S11, S21, S12(=S21), S22(=S11)
        assert "S11_1_re" in content
        assert "S21_1_re" in content
        assert "S12_1_re" in content
        assert "S22_1_re" in content

    def test_save_empty_result(self, tmp_path: Path) -> None:
        result = MeasurementResult(
            measure_id="20240101_120000_000",
            place="Empty",
            data_blocks=[],
            antenna_configs=[],
        )
        path = save_tsv(result, tmp_path / "measures")
        content = path.read_text()
        assert "#START_MEASURE" in content
        assert "#STOP_MEASURE" in content
