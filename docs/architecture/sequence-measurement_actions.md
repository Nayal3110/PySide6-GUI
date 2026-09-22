# Sequence Diagram — Measurement (action view)

Plain-language view of the measurement flow. Shows **what each step does**
rather than which function is called. Pair this with
`sequence-measurement_classes.md` when handing the project over: read this
first to understand the *story*, then the class diagram to see the *code*.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as GUI
    participant W as WorkerThread
    participant S as State
    participant DB as DataBase
    participant L as Log
    participant Seq as MeasurementRun
    participant Ser as Serial
    participant V as VNA

    User->>UI: click Start (with place, mean count, interval)
    UI->>W: emit "start" signal
    activate W

    W->>S: try to claim the measurement slot
    alt slot was free
        S-->>W: granted

        W->>W: re-read measurement settings from TOML
        Note over W: lets the user edit the config<br/>between runs without restarting

        opt database enabled
            W->>DB: open new measurement session
            DB-->>W: session id
        end
        W->>L: write "session start" banner

        W->>Seq: build a measurement sequence<br/>(devices, commands, config)
        W->>Seq: execute it
        activate Seq
        Seq->>Seq: generate a unique measure id
        Note over Seq: timestamp string
        Seq->>L: write #35;START_MEASURE marker

        loop each block of commands
            Seq->>S: stop requested?
            loop each command in the block
                Seq->>S: stop requested?
                alt simple device command (reset, temp, current, ROM)
                    Seq->>Ser: send the raw command
                    Ser-->>Seq: device response
                    Seq->>L: log the response
                else CA command
                    Seq->>Ser: send command CA-X
                    Ser-->>Seq: response
                    Note over Seq: remember whether every<br/>antenna in this block<br/>configured successfully
                else SA command
                    Seq->>Ser: send command SA
                    opt all antennas were configured OK
                        Seq->>V: confirm VNA is ready
                        Seq->>V: trigger sweep and read S-parameters
                        V-->>Seq: frequency + S11 + S21 arrays
                        Note over Seq: keep this block of data<br/>for the final TSV
                    end
                else TS/TC command
                    Seq->>Ser: pass it through to the board
                end
            end
        end

        Seq->>L: write #35;STOP_MEASURE marker
        Seq-->>W: full measurement result
        deactivate Seq

        opt at least one acquisition succeeded
            W->>W: save result as TSV in data/measures
            Note over W: filename is the measure id<br/>full 2-port format (S12=S21, S22=S11)
        end
        opt database enabled
            W->>DB: close the session
        end
        W-->>UI: emit "measurement complete" signal
        Note over UI: refresh the measure-id label
    else slot already taken
        S-->>W: denied
        Note over W: an auto-trigger raced the manual click —<br/>just unlock the UI and bail out
    end

    Note over W: always runs (success or failure)
    W->>S: release the measurement slot
    W-->>UI: emit "sequence finished" signal
    deactivate W
    UI->>UI: re-enable Start button
```

## Stop semantics

The worker checks for a stop request **twice per command** — once before
starting a new block and once before each command in the block. A stop
request lets the current command finish (no mid-command abort) and then exits
both loops cleanly. The result reports whether the run completed normally
or was interrupted.

## What can go wrong

If anything inside the measurement raises an unexpected error, the worker:

1. Marks the closing banner as `#ERROR` instead of `#STOP_MEASURE`.
2. Writes the error to the log with type `VNA_SCPI_ERROR`.
3. Sends "Measurement aborted. See log for details." to the UI as a popup.
4. Still runs the cleanup steps — closes the database session, releases the
   slot, emits "sequence finished" — so the UI never gets stuck on Stop.

## When to read this vs the class view

- **This file (actions):** first read for a new contributor or non-developer
  stakeholder. Tells the story of "what happens when the user clicks Start"
  without naming any Python function.
- **`sequence-measurement_classes.md`:** for the engineer who needs to find
  the code. Same flow, but every arrow names the actual class, method, or
  module function being called.
