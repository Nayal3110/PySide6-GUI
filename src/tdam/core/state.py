"""Thread-safe application state machine for TDAM."""

from __future__ import annotations

import threading
from enum import Enum, auto


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()


class MeasurePhase(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPING = auto()


class AppState:
    """Thread-safe state container shared between UI and worker threads.

    Uses ``threading.Event`` for the stop flag so the worker can efficiently
    block between commands, and ``threading.RLock`` for enum-based state
    transitions to prevent races.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._shutdown_event = threading.Event()
        self._connection = ConnectionState.DISCONNECTED
        self._phase = MeasurePhase.IDLE
        self._auto_armed = False

    # ── Stop flag (Event-based) ─────────────────────────────────────

    def request_stop(self) -> None:
        """Signal the worker to stop at the next safe point.

        The phase transition and the event set must happen under the same
        lock — otherwise ``try_start_measurement`` could win the gap and
        clear the event before this thread sets it.
        """
        with self._lock:
            if self._phase is MeasurePhase.RUNNING:
                self._phase = MeasurePhase.STOPPING
            self._stop_event.set()

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    def wait_for_stop(self, timeout: float) -> bool:
        """Block up to *timeout* seconds.  Returns True if stop was requested."""
        return self._stop_event.wait(timeout)

    # ── Hard shutdown flag (app-exit only) ──────────────────────────

    def request_shutdown(self) -> None:
        """Signal the worker that the application is closing.

        Sets the stop event too so existing cancellation points fire
        immediately. Distinct from ``request_stop`` so the worker can
        skip slow cleanup (file flushes, DB writes) on its way out.
        """
        with self._lock:
            self._shutdown_event.set()
            self._stop_event.set()
            if self._phase is MeasurePhase.RUNNING:
                self._phase = MeasurePhase.STOPPING

    def is_shutdown_requested(self) -> bool:
        return self._shutdown_event.is_set()

    # ── Measurement phase transitions ───────────────────────────────

    def try_start_measurement(self) -> bool:
        """Atomically transition IDLE -> RUNNING.  Returns False if busy."""
        with self._lock:
            if self._phase is not MeasurePhase.IDLE:
                return False
            self._phase = MeasurePhase.RUNNING
            self._stop_event.clear()
            return True

    def finish_measurement(self) -> None:
        """Reset phase to IDLE after measurement completes or is stopped."""
        with self._lock:
            self._phase = MeasurePhase.IDLE
            self._stop_event.clear()

    @property
    def phase(self) -> MeasurePhase:
        with self._lock:
            return self._phase

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._phase is not MeasurePhase.IDLE

    # ── Connection state ────────────────────────────────────────────

    def set_connection(self, state: ConnectionState) -> None:
        with self._lock:
            self._connection = state

    @property
    def connection(self) -> ConnectionState:
        with self._lock:
            return self._connection

    # ── Auto mode ───────────────────────────────────────────────────

    def arm_auto(self) -> None:
        with self._lock:
            self._auto_armed = True

    def disarm_auto(self) -> None:
        with self._lock:
            self._auto_armed = False

    @property
    def auto_armed(self) -> bool:
        with self._lock:
            return self._auto_armed

    # ── Full reset ──────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset all state to initial values."""
        with self._lock:
            self._connection = ConnectionState.DISCONNECTED
            self._phase = MeasurePhase.IDLE
            self._auto_armed = False
            self._stop_event.clear()
            self._shutdown_event.clear()
