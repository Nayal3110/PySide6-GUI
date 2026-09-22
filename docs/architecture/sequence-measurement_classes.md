# Sequence Diagram — User clicks Start

Hot path. Triggered when the user clicks **Start** with a place name and
mean/interval values; ends with the `sequence_finished` signal returning the
UI to the idle state.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as TDAMMainWindow
    participant W as MeasurementWorker
    participant S as AppState
    participant DB as SessionDB
    participant L as TDAMLogger
    participant Seq as MeasurementSequence
    participant Ser as SerialDevice
    participant V as VNAClient

    User->>UI: click Start
    UI->>W: _sig_start(place, mean_count, interval_s)
    activate W

    W->>S: try_start_measurement()
    alt ticket granted
        S-->>W: True

        W->>W: core/config.load_meas_config(meas_config.toml)
        Note over W: re-read so user edits<br/>between sessions are honoured

        opt SessionDB available
            W->>DB: create_session(place, config_snapshot)
            DB-->>W: session_id
        end
        W->>L: session_start(session_id, place)

        W->>Seq: MeasurementSequence(serial, vna, commands, cfg, state, logger, place)
        W->>Seq: run()
        activate Seq
        Seq->>Seq: core/measurement.new_measure_id()
        Note over Seq: timestamp ID
        Seq->>L: log_marker(#35;START_MEASURE id)

        loop each block in commands
            Seq->>S: is_stop_requested()
            loop each cmd in block
                Seq->>S: is_stop_requested()
                alt cmd in {RS, TM, GC, SR}
                    Seq->>Ser: send_command(cmd.raw)
                    Ser-->>Seq: response
                    Seq->>L: log(kind --> response)
                else cmd is CA
                    Seq->>Ser: send_command(cmd.raw)
                    Ser-->>Seq: response
                    Note over Seq: track config_all_ok flag,<br/>WARN log on failure
                else cmd is SA
                    Seq->>Ser: send_command(SA)
                    opt config_all_ok and antennas configured
                        Seq->>V: assert_ready(timeout_s=3)
                        Seq->>V: trigger_and_read(npoints, mean_count)
                        V-->>Seq: MeasurementData
                        Note over Seq: append to result.data_blocks
                    end
                else cmd in {TS, TC}
                    Seq->>Ser: send_command(cmd.raw)
                end
            end
        end

        Seq->>L: log_marker(#35;STOP_MEASURE)
        Seq-->>W: MeasurementResult
        deactivate Seq

        opt result.data_blocks not empty
            W->>W: core/measurement.save_tsv(result, data/measures)
            Note over W: writes {measure_id}.tsv<br/>full 2-port (S12=S21, S22=S11)
        end
        opt SessionDB available
            W->>DB: close_session(session_id, #STOP_MEASURE)
        end
        W-->>UI: measurement_complete(result)
        Note over UI: updates measure_id label
    else ticket already held
        S-->>W: False
        Note over W: auto-trigger raced manual click —<br/>skip straight to sequence_finished<br/>so UI unlocks
    end

    Note over W: finally (always runs)
    W->>S: finish_measurement()
    W-->>UI: sequence_finished
    deactivate W
    UI->>UI: unlock UI (re-enable Start)
```

## Stop semantics

`is_stop_requested()` is checked at two cancellation points per command —
once before each block and once before each command within a block. A stop
request lets the current command finish (no mid-SCPI abort) and then exits
both loops. The `MeasurementResult.finished_clean` flag in the return value
encodes whether the run completed normally or was interrupted.

## Error path

If anything inside `start_measurement` raises:

1. `closing_msg` becomes `#ERROR`.
2. Logger writes `Measurement error: ...` with `error_type=VNA_SCPI_ERROR`.
3. UI receives `error_occurred("Measurement aborted. See log for details.")`.
4. The `finally` block still runs — DB session closes, ticket releases,
   `sequence_finished` emits — so the UI always returns to the idle state.
