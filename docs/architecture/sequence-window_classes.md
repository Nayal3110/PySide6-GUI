# Sequence Diagram — TDAMMainWindow lifecycle (class view)

UI-thread view of the application: window construction, signal wiring, the
event handlers that translate clicks into worker signals, and shutdown. Pair
with `sequence-window_actions.md` for the plain-language version.

The hot paths inside the worker (connect, measurement) are intentionally
collapsed here — see `sequence-connect_classes.md` and
`sequence-measurement_classes.md` for those.

## Construction & wiring

```mermaid
sequenceDiagram
    autonumber
    participant App as QApplication
    participant W as TDAMMainWindow
    participant S as AppState
    participant TB as TitleBar
    participant CP as ControlPanel
    participant LP as LogPanel
    participant SB as StatusBar
    participant T as QThread
    participant Wk as MeasurementWorker

    App->>W: TDAMMainWindow()
    activate W
    W->>S: AppState()
    W->>W: core/config.ensure_default_configs(_CONFIG_DIR)
    W->>W: _build_ui()
    W->>TB: TitleBar() + connect theme/mode/start signals
    W->>CP: ControlPanel() + connect open/connection signals
    W->>LP: LogPanel()
    W->>SB: StatusBar()
    W->>W: _apply_theme()
    Note over W: build_stylesheet(get_colors(mode))<br/>QApplication.setStyleSheet(...)
    W->>W: _load_initial_vna_config()
    W->>W: core/config.load_vna_config(vna_config.toml)
    W->>CP: apply_vna_config(cfg)
    W->>W: _setup_worker()
    W->>T: QThread()
    W->>Wk: MeasurementWorker(state, config_dir, data_dir)
    W->>Wk: moveToThread(thread)
    Note over W,Wk: signals UI → worker:<br/>_sig_connect / _sig_disconnect /<br/>_sig_start / _sig_stop
    Note over W,Wk: signals worker → UI:<br/>log_message(line, level), connection_status,<br/>measurement_complete, sequence_finished,<br/>error_occurred, warning_occurred
    W->>T: start()
    deactivate W
```

## User input handlers

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant TB as TitleBar
    participant CP as ControlPanel
    participant W as TDAMMainWindow
    participant S as AppState
    participant Wk as MeasurementWorker

    Note over User,Wk: theme toggle
    User->>TB: click theme button
    TB-->>W: theme_toggled
    W->>W: _toggle_theme()
    W->>W: _apply_theme()

    Note over User,Wk: mode toggle (Normal / Auto)
    User->>TB: click mode switch
    TB-->>W: mode_toggled(checked)
    W->>S: arm_auto() / disarm_auto()

    Note over User,Wk: Connect / Disconnect
    User->>CP: click Connect
    CP-->>W: connect_clicked
    W->>W: _on_connect()
    alt state.connection is CONNECTED
        W->>CP: set_connect_text("Disconnecting...")
        W-->>Wk: _sig_disconnect()
    else not connected
        W->>CP: set_connect_text("Connecting...")
        W-->>Wk: _sig_connect(ip_address)
    Note over Wk: see sequence-connect_classes.md
    Wk-->>W: connection_status(serial_ok, vna_ok)
    W->>W: _on_connection_status(...)
    W->>CP: set_connect_text("Disconnect" / "Connect")
    W->>TB: set_start_enabled(connected)
    opt connected
        W->>CP: set_vna_labels(worker.vna_config)
    end
    end

    Note over User,Wk: Start / Stop
    User->>TB: click Start/Stop
    TB-->>W: start_clicked
    W->>W: _on_start_stop()
    alt state.is_busy
        W-->>Wk: _sig_stop()
        W->>TB: set_start_text("Stopping...")
    else idle
        W->>W: _lock_ui()
        W-->>Wk: _sig_start(place, mean_count, interval_s)
    Note over Wk: see sequence-measurement_classes.md
    Wk-->>W: measurement_complete(result)
    W->>W: _on_measurement_complete(result)
    W->>SB: set_measure_id(result.measure_id)
    Wk-->>W: sequence_finished
    W->>W: _on_sequence_finished()
    W->>W: _unlock_ui()
    end
```

## Auto-mode loop

```mermaid
sequenceDiagram
    autonumber
    participant Wk as MeasurementWorker
    participant W as TDAMMainWindow
    participant S as AppState
    participant CP as ControlPanel
    participant Q as QTimer

    Wk-->>W: sequence_finished
    W->>W: _on_sequence_finished()
    W->>S: auto_armed?
    opt auto_armed and connection is CONNECTED
        W->>CP: interval_s()
        CP-->>W: seconds
        W->>Q: singleShot(interval_s * 1000, _auto_trigger)
        Note over Q: Qt timer fires on the UI thread
        Q-->>W: _auto_trigger()
        W->>S: auto_armed?
        W->>S: connection is CONNECTED?
        opt both still true
            W->>W: _lock_ui()
            W-->>Wk: _sig_start(place, mean_count, interval_s)
        end
    end
```

## Open measurement file

```mermaid
sequenceDiagram
    actor User
    participant CP as ControlPanel
    participant W as TDAMMainWindow
    participant FD as QFileDialog
    participant OS as os.startfile / xdg-open

    User->>CP: click Open Measurement
    CP-->>W: open_measurement_clicked
    W->>FD: getOpenFileName(_MEASURES_DIR, "*.tsv")
    FD-->>W: path or ""
    opt path is non-empty
        W->>W: _is_safe_measure_path(path, _MEASURES_DIR)
        alt path inside measures dir
            W->>OS: launch default viewer
        else escaped sandbox
            W->>W: QMessageBox.warning("Refusing to open ...")
        end
    end
```

## Log / error / warning relays

```mermaid
sequenceDiagram
    participant Wk as MeasurementWorker
    participant W as TDAMMainWindow
    participant LP as LogPanel
    participant MB as QMessageBox

    Wk-->>W: log_message(line, level)
    W->>LP: append(message, level)
    Note over LP: WARNING -> yellow,<br/>ERROR -> red,<br/>INFO/MARKER/DATA -> default

    Wk-->>W: warning_occurred(str)
    W->>MB: warning("TDAM — Warning", message)
    Note over Wk: only emitted for popup-worthy<br/>warnings — advisory connect-time<br/>issues now use log() at WARNING level

    Wk-->>W: error_occurred(str)
    W->>MB: critical("TDAM — Error", message)
```

## Close

```mermaid
sequenceDiagram
    actor User
    participant W as TDAMMainWindow
    participant S as AppState
    participant Wk as MeasurementWorker
    participant T as QThread

    User->>W: closeEvent(event)
    opt state.is_busy
        W->>S: request_stop()
    end
    opt state.connection is CONNECTED
        W->>Wk: connection_status.disconnect(_on_connection_status)
        Note over W: detach so a late status update<br/>can't reach widgets being torn down
        W-->>Wk: _sig_disconnect()
    end
    W->>T: quit()
    W->>T: wait(10000)
    alt thread finished in time
        T-->>W: True
    else timeout
        Note over W: print warning to stderr,<br/>exit anyway — never terminate()<br/>(would leave VNA in bad state)
    end
    W->>W: super().closeEvent(event)
```
