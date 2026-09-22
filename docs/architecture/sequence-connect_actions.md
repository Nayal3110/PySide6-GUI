# Sequence Diagram — Connect (action view)

Plain-language view of the connect flow. Shows **what each step does** rather
than which function is called. Pair this with `sequence-connect_classes.md`
when handing the project over: read this first to understand the *story*, then
the class diagram to see the *code*.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as GUI
    participant W as WorkerThread
    participant S as State
    participant DB as DataBase
    participant L as Log
    participant V as VNA
    participant Ser as Serial

    User->>UI: click Connect (with IP)
    UI->>W: emit "connect" signal
    activate W
    W->>S: mark state as CONNECTING
    W->>W: close any leftover handles (clean slate)

    W->>DB: open the local SQLite session DB (data/tdam.db)
    Note right of DB: if the file path is unwritable,<br/>keep going with file logging only

    W->>L: open log file and wire signals
    Note over W,L: log lines will reach the UI<br/>and the SQLite DB (if open)

    W->>W: read VNA settings from TOML
    Note over W: frequency range, power,<br/>averaging, npoints...

    W->>W: read TRVNA executable path from TOML
    W->>W: launch TRVNA.exe (if not running)
    Note over W: Windows only —<br/>path must be allow-listed

    W->>V: open TCP connection to VNA
    V-->>W: instrument identity string
    W->>V: wait until VNA is ready (up to 12s)
    V-->>W: ready
    W->>V: read internal temperature
    V-->>W: Temperature °C
    W->>V: apply full VNA configuration commands

    W->>Ser: discover STM32 board on COM ports
    Note over Ser: broadcast "SP" on each port,<br/>accept the one that replies "TSP"
    Ser-->>W: connected port name

    W->>W: read measurement command sequence from TOML
    Note over W: list of commands <br/>that drive each measure

    W->>S: mark state as CONNECTED
    W->>L: write "CONNECT ALL: READY"
    W-->>UI: emit "connection status" signal (serial OK, VNA OK)
    deactivate W
    UI->>UI: enable Start button, relabel Connect → Disconnect
```

## What can go wrong

If any step above fails, the worker:

1. Marks the connection state as **ERROR**.
2. Picks a short user-facing message based on what failed:
   - serial discovery → "Serial port not found."
   - TRVNA launch → "Could not launch TRVNA."
   - anything else (VNA connect, config load, ...) → "Could not connect to the VNA."
3. Closes every handle it managed to open (rollback).
4. Sends that short message to the UI as an error popup.
5. Sends a connection-status update reflecting whatever was opened before the
   failure — so the LEDs show partial success (e.g. VNA green, serial red).

## When to read this vs the class view

- **This file (actions):** first read for a new contributor or non-developer
  stakeholder. Tells the story of "what happens when the user clicks Connect"
  without naming any Python function.
- **`sequence-connect_classes.md`:** for the engineer who needs to find the
  code. Same flow, but every arrow names the actual class, method, or module
  function being called.
