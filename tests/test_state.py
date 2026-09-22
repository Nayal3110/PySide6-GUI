"""Tests for thread-safe AppState."""

from __future__ import annotations

import threading
import time

from src.tdam.core.state import AppState, ConnectionState, MeasurePhase


class TestAppState:
    def test_initial_state(self) -> None:
        s = AppState()
        assert s.connection is ConnectionState.DISCONNECTED
        assert s.phase is MeasurePhase.IDLE
        assert not s.is_busy
        assert not s.is_stop_requested()
        assert not s.auto_armed

    def test_connection_transitions(self) -> None:
        s = AppState()
        s.set_connection(ConnectionState.CONNECTING)
        assert s.connection is ConnectionState.CONNECTING
        s.set_connection(ConnectionState.CONNECTED)
        assert s.connection is ConnectionState.CONNECTED

    def test_try_start_measurement(self) -> None:
        s = AppState()
        assert s.try_start_measurement()
        assert s.phase is MeasurePhase.RUNNING
        assert s.is_busy

    def test_double_start_fails(self) -> None:
        s = AppState()
        assert s.try_start_measurement()
        assert not s.try_start_measurement()

    def test_finish_measurement(self) -> None:
        s = AppState()
        s.try_start_measurement()
        s.finish_measurement()
        assert s.phase is MeasurePhase.IDLE
        assert not s.is_busy

    def test_stop_request(self) -> None:
        s = AppState()
        s.try_start_measurement()
        s.request_stop()
        assert s.is_stop_requested()
        assert s.phase is MeasurePhase.STOPPING

    def test_stop_when_idle_just_sets_event(self) -> None:
        s = AppState()
        s.request_stop()
        assert s.is_stop_requested()
        assert s.phase is MeasurePhase.IDLE  # no transition

    def test_wait_for_stop(self) -> None:
        s = AppState()
        # Should return False when timeout expires without stop
        assert not s.wait_for_stop(0.01)
        s.request_stop()
        assert s.wait_for_stop(0.01)

    def test_auto_mode(self) -> None:
        s = AppState()
        assert not s.auto_armed
        s.arm_auto()
        assert s.auto_armed
        s.disarm_auto()
        assert not s.auto_armed

    def test_reset(self) -> None:
        s = AppState()
        s.set_connection(ConnectionState.CONNECTED)
        s.try_start_measurement()
        s.arm_auto()
        s.reset()
        assert s.connection is ConnectionState.DISCONNECTED
        assert s.phase is MeasurePhase.IDLE
        assert not s.auto_armed
        assert not s.is_stop_requested()

    def test_concurrent_start(self) -> None:
        """Only one thread should succeed in starting."""
        s = AppState()
        results = []

        def try_start():
            results.append(s.try_start_measurement())

        threads = [threading.Thread(target=try_start) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sum(results) == 1  # exactly one True

    def test_wait_for_stop_wakes_when_signaled_from_other_thread(self) -> None:
        """A thread blocked on wait_for_stop should unblock as soon as
        another thread calls request_stop — not on timeout."""
        s = AppState()
        s.try_start_measurement()
        woken = threading.Event()

        def waiter() -> None:
            if s.wait_for_stop(2.0):
                woken.set()

        t = threading.Thread(target=waiter)
        t.start()

        # Give the waiter a chance to enter wait_for_stop, then signal.
        time.sleep(0.05)
        s.request_stop()

        t.join(timeout=1.0)
        assert woken.is_set()
        assert not t.is_alive()

    def test_concurrent_start_and_stop_leave_state_consistent(self) -> None:
        """Hammering start + stop from many threads must not corrupt state."""
        s = AppState()
        s.set_connection(ConnectionState.CONNECTED)

        def loop() -> None:
            for _ in range(50):
                if s.try_start_measurement():
                    s.request_stop()
                    s.finish_measurement()

        threads = [threading.Thread(target=loop) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # After everyone finishes, the state machine must be back to a
        # legal idle configuration.
        assert s.phase is MeasurePhase.IDLE
        assert not s.is_busy
        # The connection state should not be perturbed by measurement work.
        assert s.connection is ConnectionState.CONNECTED
