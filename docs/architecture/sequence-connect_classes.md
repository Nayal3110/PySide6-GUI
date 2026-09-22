# Sequence Diagram — User clicks Connect

Startup orchestration. Triggered when the user clicks **Connect** with an IP
address; ends with the `connection_status` signal flipping the UI into the
"connected" state and unlocking the Start button.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as TDAMMainWindow
    participant W as MeasurementWorker
    participant S as AppState
    participant DB as SessionDB
    participant L as TDAMLogger
    participant V as VNAClient
    participant Ser as SerialDevice

    User->>UI: click Connect
    UI->>W: _sig_connect(ip)
    activate W
    W->>S: set_connection(CONNECTING)
    W->>W: _close_all() (clean slate)

    W->>DB: SessionDB(db_path=data_dir / "tdam.db")
    Note right of DB: OSError/sqlite3.Error prints to stderr<br/>and falls back to file-only

    W->>L: TDAMLogger(log_dir, db)
    Note over W,L: log_signal(line, level) -> log_message<br/>ui_warning_signal -> warning_occurred

    W->>W: core/config.load_vna_config(vna_config.toml)
    Note over W: returns VNAConfig

    W->>W: core/config.load_trvna_path(trvna_path.toml)
    Note over W: returns Path
    W->>W: core/process_launcher.ensure_trvna_running(path)
    Note over W: spawns TRVNA.exe if absent<br/>(Windows only, raises TRVNAError)

    W->>V: VNAClient(ip).connect()
    V-->>W: idn string
    W->>V: assert_ready(12s)
    V-->>W: ready
    W->>V: get_temperature()
    V-->>W: temperature_C
    W->>V: configure(_vna_cfg)

    W->>Ser: SerialDevice.discover()
    Note over Ser: scan COM ports<br/>send "SP", expect "TSP"
    Ser-->>W: connected port

    W->>W: core/config.load_meas_config(meas_config.toml)
    Note over W: returns list[list[MeasCommand]]

    W->>S: set_connection(CONNECTED)
    W->>L: log("CONNECT ALL: READY")
    W-->>UI: connection_status(serial_ok=True, vna_ok=True)
    deactivate W
    UI->>UI: enable Start, set Disconnect label
```

## Failure paths (not drawn)

If any step inside the try-block raises, the worker:

1. Sets `AppState.connection` to `ERROR`.
2. Picks a short user-facing message based on the exception class
   (`SerialError` -> "Serial port not found.", `TRVNAError` -> "Could not
   launch TRVNA.", anything else -> "Could not connect to the VNA.").
3. Calls `_rollback()` (which is `_close_all()`).
4. Emits `error_occurred(short_msg + " See log for details.")`.
5. Emits `connection_status(serial_ok, vna_ok)` with whatever flags were set
   before the failure — partial success surfaces in the indicator LEDs.

See `core/worker.py:160-180` for the exception-to-label mapping.
