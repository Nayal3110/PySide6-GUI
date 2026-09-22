"""Tests for the TitleBar widget."""

from __future__ import annotations

import pytest

from src.tdam.ui.widgets.title_bar import TitleBar


@pytest.fixture
def bar(qtbot) -> TitleBar:
    widget = TitleBar()
    qtbot.addWidget(widget)
    return widget


class TestTitleBar:
    def test_initial_state(self, bar: TitleBar) -> None:
        assert bar._mode_toggle.text() == "Normal"
        assert not bar._mode_toggle.isChecked()
        assert not bar._start_btn.isEnabled()
        assert bar._start_btn.text() == "Start"

    def test_mode_toggle_renames_to_auto(self, bar: TitleBar, qtbot) -> None:
        with qtbot.waitSignal(bar.mode_toggled) as blocker:
            bar._mode_toggle.click()
        assert blocker.args == [True]
        assert bar._mode_toggle.text() == "Auto"
        assert bar._mode_toggle.isChecked()

    def test_mode_toggle_renames_back_to_normal(
        self, bar: TitleBar, qtbot
    ) -> None:
        bar._mode_toggle.click()  # Normal -> Auto
        with qtbot.waitSignal(bar.mode_toggled) as blocker:
            bar._mode_toggle.click()  # Auto -> Normal
        assert blocker.args == [False]
        assert bar._mode_toggle.text() == "Normal"

    def test_start_clicked_emits(self, bar: TitleBar, qtbot) -> None:
        bar.set_start_enabled(True)
        with qtbot.waitSignal(bar.start_clicked):
            bar._start_btn.click()

    def test_theme_clicked_emits(self, bar: TitleBar, qtbot) -> None:
        with qtbot.waitSignal(bar.theme_toggled):
            bar._theme_btn.click()

    def test_set_start_text(self, bar: TitleBar) -> None:
        bar.set_start_text("Stop")
        assert bar._start_btn.text() == "Stop"

    def test_set_start_enabled(self, bar: TitleBar) -> None:
        bar.set_start_enabled(True)
        assert bar._start_btn.isEnabled()
        bar.set_start_enabled(False)
        assert not bar._start_btn.isEnabled()

    def test_set_mode_enabled(self, bar: TitleBar) -> None:
        bar.set_mode_enabled(False)
        assert not bar._mode_toggle.isEnabled()
        bar.set_mode_enabled(True)
        assert bar._mode_toggle.isEnabled()

    def test_set_theme_icon_updates_text_and_tooltip(
        self, bar: TitleBar
    ) -> None:
        bar.set_theme_icon("☀", "Switch to light theme")
        assert bar._theme_btn.text() == "☀"
        assert bar._theme_btn.toolTip() == "Switch to light theme"

    def test_is_mode_checked_reflects_state(self, bar: TitleBar) -> None:
        assert bar.is_mode_checked() is False
        bar._mode_toggle.click()
        assert bar.is_mode_checked() is True
