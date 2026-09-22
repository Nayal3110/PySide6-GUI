"""Tests for the ControlPanel widget."""

from __future__ import annotations

import pytest

from src.tdam.core.config import VNAConfig
from src.tdam.ui.widgets.control_panel import ControlPanel


@pytest.fixture
def panel(qtbot) -> ControlPanel:
    widget = ControlPanel()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def cfg() -> VNAConfig:
    return VNAConfig(
        fstart_mhz=50.0,
        fstop_mhz=400.0,
        npoints=1001,
        ifbw_hz=1000.0,
        power_dbm=-30.0,
        average=4,
        interval_s=120,
        mean_count=8,
        refvalue=-40,
    )


class TestControlPanel:
    def test_initial_defaults(self, panel: ControlPanel) -> None:
        assert panel.place() == "Airolo"
        assert panel.ip_address() == "127.0.0.1"
        assert panel.mean_count() == 10
        assert panel.interval_s() == 180

    def test_place_strips_whitespace(self, panel: ControlPanel) -> None:
        panel._location_edit.setText("   Lugano  ")
        assert panel.place() == "Lugano"

    def test_place_falls_back_to_unknown_when_blank(
        self, panel: ControlPanel
    ) -> None:
        panel._location_edit.setText("   ")
        assert panel.place() == "Unknown"

    def test_set_vna_labels_populates_all_fields(
        self, panel: ControlPanel, cfg: VNAConfig
    ) -> None:
        panel.set_vna_labels(cfg)
        assert panel._power_lbl.text() == "-30"
        assert panel._npoints_lbl.text() == "1001"
        assert panel._if_filter_lbl.text() == "1000"
        assert panel._freq_start_lbl.text() == "50"
        assert panel._freq_stop_lbl.text() == "400"
        assert panel._average_lbl.text() == "4"

    def test_apply_vna_config_syncs_spin_boxes(
        self, panel: ControlPanel, cfg: VNAConfig
    ) -> None:
        panel.apply_vna_config(cfg)
        assert panel.mean_count() == cfg.mean_count
        assert panel.interval_s() == cfg.interval_s
        # And labels are populated too
        assert panel._npoints_lbl.text() == str(cfg.npoints)

    def test_connect_clicked_signal(
        self, panel: ControlPanel, qtbot
    ) -> None:
        with qtbot.waitSignal(panel.connect_clicked):
            panel._connect_btn.click()

    def test_open_measurement_clicked_signal(
        self, panel: ControlPanel, qtbot
    ) -> None:
        with qtbot.waitSignal(panel.open_measurement_clicked):
            panel._open_meas_btn.click()

    def test_set_connect_text_and_enabled(self, panel: ControlPanel) -> None:
        panel.set_connect_text("Disconnect")
        assert panel._connect_btn.text() == "Disconnect"
        panel.set_connect_enabled(False)
        assert not panel._connect_btn.isEnabled()
        panel.set_connect_enabled(True)
        assert panel._connect_btn.isEnabled()

    def test_set_inputs_enabled_toggles_all_inputs(
        self, panel: ControlPanel
    ) -> None:
        panel.set_inputs_enabled(False)
        assert not panel._location_edit.isEnabled()
        assert not panel._nr_meas_spin.isEnabled()
        assert not panel._aq_interval_spin.isEnabled()
        panel.set_inputs_enabled(True)
        assert panel._location_edit.isEnabled()
        assert panel._nr_meas_spin.isEnabled()
        assert panel._aq_interval_spin.isEnabled()
