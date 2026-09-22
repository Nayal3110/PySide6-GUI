"""Tests for TRVNA process launcher."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tdam.core.process_launcher import (
    TRVNAError,
    _is_allowed_trvna_path,
    ensure_trvna_running,
    is_process_running,
)


class TestIsProcessRunning:
    def test_returns_false_on_non_windows(self) -> None:
        with patch("src.tdam.core.process_launcher.sys.platform", "linux"):
            assert is_process_running("TRVNA.exe") is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_returns_true_when_tasklist_lists_exe(self) -> None:
        fake_result = MagicMock()
        fake_result.stdout = "TRVNA.exe   1234 Console   1   12,000 K"
        with patch(
            "src.tdam.core.process_launcher.subprocess.run", return_value=fake_result
        ):
            assert is_process_running("TRVNA.exe") is True

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_returns_false_when_tasklist_empty(self) -> None:
        fake_result = MagicMock()
        fake_result.stdout = ""
        with patch(
            "src.tdam.core.process_launcher.subprocess.run", return_value=fake_result
        ):
            assert is_process_running("TRVNA.exe") is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_returns_false_on_subprocess_error(self) -> None:
        with patch(
            "src.tdam.core.process_launcher.subprocess.run",
            side_effect=subprocess.TimeoutExpired("tasklist", 5),
        ):
            assert is_process_running("TRVNA.exe") is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_match_is_case_insensitive(self) -> None:
        fake_result = MagicMock()
        fake_result.stdout = "trvna.exe   1234 Console"
        with patch(
            "src.tdam.core.process_launcher.subprocess.run", return_value=fake_result
        ):
            assert is_process_running("TRVNA.exe") is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only allow-list")
class TestIsAllowedTRVNAPath:
    def test_allows_path_under_c_vna(self) -> None:
        assert _is_allowed_trvna_path(Path(r"C:\VNA\TRVNA\TRVNA.exe")) is True

    def test_allows_path_under_program_files(self) -> None:
        assert (
            _is_allowed_trvna_path(Path(r"C:\Program Files\TRVNA\TRVNA.exe"))
            is True
        )

    def test_allows_path_under_program_files_x86(self) -> None:
        assert (
            _is_allowed_trvna_path(
                Path(r"C:\Program Files (x86)\TRVNA\TRVNA.exe")
            )
            is True
        )

    def test_rejects_path_outside_allow_list(self) -> None:
        assert _is_allowed_trvna_path(Path(r"C:\Users\evil\TRVNA.exe")) is False

    def test_rejects_temp_path(self, tmp_path: Path) -> None:
        assert _is_allowed_trvna_path(tmp_path / "TRVNA.exe") is False


class TestEnsureTRVNARunning:
    def test_raises_on_non_windows(self, tmp_path: Path) -> None:
        with patch("src.tdam.core.process_launcher.sys.platform", "linux"):
            with pytest.raises(TRVNAError, match="only supported"):
                ensure_trvna_running(tmp_path / "TRVNA.exe")

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_rejects_path_outside_allow_list(self, tmp_path: Path) -> None:
        exe = tmp_path / "TRVNA.exe"
        exe.write_bytes(b"")
        with pytest.raises(TRVNAError, match="disallowed path"):
            ensure_trvna_running(exe)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_no_op_when_already_running(self, tmp_path: Path) -> None:
        exe = tmp_path / "TRVNA.exe"
        exe.write_bytes(b"")  # exists but should not be launched
        with patch(
            "src.tdam.core.process_launcher._is_allowed_trvna_path", return_value=True
        ):
            with patch(
                "src.tdam.core.process_launcher.is_process_running", return_value=True
            ):
                with patch(
                    "src.tdam.core.process_launcher.subprocess.Popen"
                ) as mock_popen:
                    ensure_trvna_running(exe)
                    mock_popen.assert_not_called()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_raises_when_exe_missing(self, tmp_path: Path) -> None:
        exe = tmp_path / "missing.exe"
        with patch(
            "src.tdam.core.process_launcher._is_allowed_trvna_path", return_value=True
        ):
            with patch(
                "src.tdam.core.process_launcher.is_process_running", return_value=False
            ):
                with pytest.raises(TRVNAError, match="not found"):
                    ensure_trvna_running(exe)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_launches_when_not_running(self, tmp_path: Path) -> None:
        exe = tmp_path / "TRVNA.exe"
        exe.write_bytes(b"")
        with patch(
            "src.tdam.core.process_launcher._is_allowed_trvna_path", return_value=True
        ):
            with patch(
                "src.tdam.core.process_launcher.is_process_running", return_value=False
            ):
                with patch(
                    "src.tdam.core.process_launcher.subprocess.Popen"
                ) as mock_popen:
                    ensure_trvna_running(exe)
                    mock_popen.assert_called_once()
                    args, _ = mock_popen.call_args
                    assert args[0] == [str(exe.resolve())]

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path")
    def test_wraps_oserror_in_trvna_error(self, tmp_path: Path) -> None:
        exe = tmp_path / "TRVNA.exe"
        exe.write_bytes(b"")
        with patch(
            "src.tdam.core.process_launcher._is_allowed_trvna_path", return_value=True
        ):
            with patch(
                "src.tdam.core.process_launcher.is_process_running", return_value=False
            ):
                with patch(
                    "src.tdam.core.process_launcher.subprocess.Popen",
                    side_effect=OSError("permission denied"),
                ):
                    with pytest.raises(TRVNAError, match="Failed to launch"):
                        ensure_trvna_running(exe)
