"""Shared fixtures for TDAM tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tdam.core.config import VNAConfig


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def sample_vna_config() -> VNAConfig:
    return VNAConfig(
        fstart_mhz=50,
        fstop_mhz=400,
        npoints=1001,
        ifbw_hz=1000,
        power_dbm=-30,
        average=1,
        interval_s=180,
        mean_count=10,
        refvalue=-40,
    )


@pytest.fixture
def vna_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "vna_config.toml"
    p.write_text(
        "# VNA configuration\n"
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
    )
    return p


@pytest.fixture
def meas_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "meas_config.toml"
    p.write_text(
        "[measurement]\n"
        "sequences = [\n"
        '    ["RS"],\n'
        '    ["TM"],\n'
        '    ["CA-T1AA", "CA-R2AA", "SA"],\n'
        '    ["GC"],\n'
        "]\n"
    )
    return p
