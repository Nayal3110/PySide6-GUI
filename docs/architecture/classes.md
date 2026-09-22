# Class Diagram

Static structure of the TDAM core. Shows the seven runtime classes, the two
state enums, and the dataclasses that flow between them.

```mermaid
classDiagram
    direction LR

    class TDAMMainWindow {
        +closeEvent()
        -_on_connect()
        -_on_start_stop()
        -_on_log()
        -_on_connection_status()
        -_on_measurement_complete()
        -_on_sequence_finished()
        -_on_error()
        -_on_warning()
    }

    class MeasurementWorker {
        +connect_instruments(ip)
        +disconnect_instruments()
        +start_measurement(place, n, dt)
        +request_stop()
        +vna_config
    }

    class AppState {
        +try_start_measurement() bool
        +finish_measurement()
        +request_stop()
        +is_stop_requested() bool
        +set_connection(state)
        +arm_auto()
        +disarm_auto()
        +reset()
        +phase
        +connection
        +auto_armed
        +is_busy
    }

    class MeasurementSequence {
        +run() MeasurementResult
    }

    class TDAMLogger {
        +log(msg, level, error_type)
        +log_marker(marker)
        +warn_ui(ui_msg, log_msg)
        +session_start(sid, place)
        +session_end(closing_msg)
        +close()
        +file_ok
        +session_id
    }

    class SerialDevice {
        +discover() SerialDevice$
        +send_command(cmd) str
        +close()
    }

    class VNAClient {
        +connect() str
        +configure(cfg)
        +assert_ready(timeout_s)
        +trigger_and_read(npoints, n) MeasurementData
        +get_temperature() float
        +get_id() str
        +close()
    }

    class SessionDB {
        <<SQLite — data/tdam.db; id = start timestamp>>
        +create_session(place, snapshot) str
        +log_entry(sid, msg, level, error_type)
        +close_session(sid, closing_msg)
        +session_exists(started_at) bool
        +import_session(place, started_at, ended_at, closing_msg, entries) str
        +query_sessions() list
        +query_session_errors(sid) list
        +close()
    }

    class ConnectionState {
        <<enumeration>>
        DISCONNECTED
        CONNECTING
        CONNECTED
        ERROR
    }

    class MeasurePhase {
        <<enumeration>>
        IDLE
        RUNNING
        STOPPING
    }

    class VNAConfig {
        <<dataclass>>
        +fstart_hz
        +fstop_hz
        +npoints
        +power_dbm
        +ifbw_hz
        +mean_count
        +interval_s
        +refvalue
    }

    class MeasurementData {
        <<dataclass>>
        +freq_hz
        +s21
        +s11
    }

    class MeasurementResult {
        <<dataclass>>
        +measure_id
        +place
        +data_blocks
        +antenna_configs
        +finished_clean
    }

    %% UI owns runtime
    TDAMMainWindow *-- AppState
    TDAMMainWindow *-- MeasurementWorker

    %% Worker owns hardware + persistence
    MeasurementWorker *-- SerialDevice
    MeasurementWorker *-- VNAClient
    MeasurementWorker *-- SessionDB
    MeasurementWorker *-- TDAMLogger
    MeasurementWorker --> AppState : reads/writes
    MeasurementWorker ..> VNAConfig : holds
    MeasurementWorker ..> MeasurementSequence : creates per session

    %% Sequence borrows everything it needs
    MeasurementSequence ..> SerialDevice : uses
    MeasurementSequence ..> VNAClient : uses
    MeasurementSequence ..> AppState : uses
    MeasurementSequence ..> TDAMLogger : uses
    MeasurementSequence ..> VNAConfig : uses
    MeasurementSequence ..> MeasurementResult : produces

    %% Logger writes to optional DB
    TDAMLogger ..> SessionDB : optional sink

    %% Enums grouped under AppState
    AppState ..> ConnectionState
    AppState ..> MeasurePhase

    %% VNA returns dataclass
    VNAClient ..> MeasurementData : produces

    %% Cross-thread Qt signal wiring
    TDAMMainWindow ..> MeasurementWorker : sig_connect / sig_start / sig_stop / sig_disconnect
    MeasurementWorker ..> TDAMMainWindow : log_message(line,level) / connection_status / measurement_complete / sequence_finished / error_occurred / warning_occurred
    TDAMLogger ..> MeasurementWorker : log_signal(line,level) / ui_warning_signal
```

## How to read this

- **Filled diamond `◆--`** — composition: the owner constructs and disposes the
  child. `MeasurementWorker` instantiates `SerialDevice`, `VNAClient`,
  `SessionDB`, and `TDAMLogger` inside `connect_instruments()` and tears them
  down in `_close_all()`.
- **Solid arrow `->`** — runtime read/write association without ownership.
  `MeasurementWorker` mutates `AppState` it does not own (the window owns it).
- **Dashed arrow `-->`** — dependency / "uses" / "produces". `MeasurementSequence`
  holds borrowed references for the lifetime of one `run()` call.
- **Dashed arrows labelled with signal names** — Qt signal/slot wiring (the
  three-hop log chain is documented at `src/tdam/core/logger.py` + `core/worker.py`).


