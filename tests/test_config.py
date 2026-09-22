"""Tests for config parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tdam.core.config import (
    CommandType,
    ConfigError,
    MeasCommand,
    VNAConfig,
    ensure_default_configs,
    load_meas_config,
    load_trvna_path,
    load_vna_config,
)


class TestVNAConfig:
    def test_load_valid(self, vna_config_file: Path) -> None:
        cfg = load_vna_config(vna_config_file)
        assert cfg.fstart_mhz == 50
        assert cfg.fstop_mhz == 400
        assert cfg.npoints == 1001
        assert cfg.ifbw_hz == 1000
        assert cfg.power_dbm == -30
        assert cfg.average == 1
        assert cfg.interval_s == 180
        assert cfg.mean_count == 10
        assert cfg.refvalue == -40

    def test_fstart_hz_property(self, sample_vna_config: VNAConfig) -> None:
        assert sample_vna_config.fstart_hz == 50e6
        assert sample_vna_config.fstop_hz == 400e6

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_vna_config(tmp_path / "missing.txt")

    def test_missing_keys(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.toml"
        p.write_text("[vna]\nfstart_mhz = 50\n")
        with pytest.raises(ConfigError, match="missing"):
            load_vna_config(p)

    def test_missing_vna_table(self, tmp_path: Path) -> None:
        p = tmp_path / "no_table.toml"
        p.write_text("fstart_mhz = 50\n")
        with pytest.raises(ConfigError, match="\\[vna\\] table"):
            load_vna_config(p)

    def test_invalid_toml(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.toml"
        p.write_text("[vna\nfstart_mhz = 50\n")
        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_vna_config(p)

    def test_comments_and_extra_keys(self, tmp_path: Path) -> None:
        p = tmp_path / "cfg.toml"
        p.write_text(
            "# comment\n"
            "[vna]\n"
            "fstart_mhz = 50\n"
            "fstop_mhz  = 400\n"
            "npoints    = 1001\n"
            "ifbw_hz    = 1000\n"
            "power_dbm  = -30\n"
            "average    = 1\n"
            "interval_s = 180\n"
            "mean_count = 10\n"
            "refvalue   = -40\n"
            "extra_key  = 42\n"
        )
        cfg = load_vna_config(p)
        assert cfg.npoints == 1001


class TestMeasConfig:
    def test_load_valid(self, meas_config_file: Path) -> None:
        seqs = load_meas_config(meas_config_file)
        assert len(seqs) == 4
        # First sequence: [RS]
        assert len(seqs[0]) == 1
        assert seqs[0][0].kind is CommandType.RS
        # Third sequence: [CA-T1AA, CA-R2AA, SA]
        assert len(seqs[2]) == 3
        assert seqs[2][0].kind is CommandType.CA
        assert seqs[2][0].raw == "CA-T1AA"
        assert seqs[2][2].kind is CommandType.SA

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_meas_config(tmp_path / "missing.toml")

    def test_empty_sequences(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.toml"
        p.write_text("[measurement]\nsequences = []\n")
        seqs = load_meas_config(p)
        assert seqs == []

    def test_missing_measurement_table(self, tmp_path: Path) -> None:
        p = tmp_path / "no_table.toml"
        p.write_text("fstart_mhz = 50\n")
        with pytest.raises(ConfigError, match="\\[measurement\\] table"):
            load_meas_config(p)

    def test_invalid_toml(self, tmp_path: Path) -> None:
        p = tmp_path / "broken.toml"
        p.write_text("[measurement\nsequences = []\n")
        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_meas_config(p)


class TestMeasCommand:
    def test_parse_simple(self) -> None:
        cmd = MeasCommand.parse("RS")
        assert cmd.kind is CommandType.RS
        assert cmd.raw == "RS"

    def test_parse_ca(self) -> None:
        cmd = MeasCommand.parse("CA-T1AA")
        assert cmd.kind is CommandType.CA
        assert cmd.raw == "CA-T1AA"

    def test_parse_unknown(self) -> None:
        with pytest.raises(ConfigError, match="Unknown"):
            MeasCommand.parse("INVALID")

    def test_parse_empty(self) -> None:
        with pytest.raises(ConfigError, match="Empty"):
            MeasCommand.parse("")


class TestTRVNAPath:
    def test_load_from_file(self, tmp_path: Path) -> None:
        p = tmp_path / "trvna_path.toml"
        p.write_text("[trvna]\npath = 'C:\\\\MyVNA\\\\TRVNA.exe'\n")
        result = load_trvna_path(p)
        assert result == Path(r"C:\MyVNA\TRVNA.exe")

    def test_default_when_missing(self, tmp_path: Path) -> None:
        result = load_trvna_path(tmp_path / "missing.txt")
        assert result == Path(r"C:\VNA\TRVNA\TRVNA.exe")


class TestEnsureDefaultConfigs:
    def test_copies_defaults(self, tmp_path: Path) -> None:
        target = tmp_path / "config"
        ensure_default_configs(target)
        assert target.is_dir()
