# Sequence Diagram — TDAMMainWindow lifecycle (action view)

Plain-language view of the application window: how it starts up, how it
reacts to clicks, the auto-mode loop, and how it shuts down. Pair with
`sequence-window_classes.md` for the code-oriented version.

The connect and measurement flows themselves are collapsed here — see the
`sequence-connect_actions.md` and `sequence-measurement_actions.md` files
for the story of what happens *inside* those operations.

## Startup & wiring

```mermaid
sequenceDiagram
    autonumber
    participant App as Qt
    participant W as MainWindow
    participant S as State
    participant TB as TitleBar
    participant CP as ControlPanel
    participant LP as LogPanel
    participant SB as StatusBar
    participant T as Thread
    participant Wk as WorkerThread

    App->>W: create main window
    activate W
    W->>S: create shared state
    W->>W: make sure default config files exist
    W->>W: build the widgets
    W->>TB: title bar (theme / mode / start buttons)
    W->>CP: control panel (IP, place, intervals, Connect, Open file)
    W->>LP: log panel
    W->>SB: status bar (measure id)
    W->>W: apply colors and stylesheet
    W->>W: read VNA settings from TOML
    W->>CP: show those VNA settings as labels
    W->>W: build the worker thread
    W->>T: create background thread
    W->>Wk: create worker and move it to that thread
    Note over W,Wk: wire the signals so clicks reach the worker<br/>and the worker can talk back (logs, status, errors)
    W->>T: start running
    deactivate W
```

## What clicks do

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant TB as TitleBar
    participant CP as ControlPanel
    participant W as MainWindow
    participant S as State
    participant Wk as WorkerThread

    Note over User,Wk: switch theme
    User->>TB: click sun/moon
    TB-->>W: theme toggled
    W->>W: swap palette and re-apply stylesheet

    Note over User,Wk: switch between Normal and Auto
    User->>TB: click mode switch
    TB-->>W: mode toggled
    W->>S: arm or disarm auto mode

    Note over User,Wk: Connect or Disconnect
    User->>CP: click Connect
    CP-->>W: connect requested
    alt already connected
        W->>CP: show "Disconnecting..."
        W-->>Wk: ask worker to disconnect
    else not connected
        W->>CP: show "Connecting..."
        W-->>Wk: ask worker to connect (with IP)

    Note over Wk: see sequence-connect_actions.md
    Wk-->>W: connection result (serial OK?, VNA OK?)
    W->>CP: relabel the button (Disconnect / Connect)
    W->>TB: enable or disable the Start button
    opt connection succeeded
        W->>CP: refresh VNA labels with the actual settings used
    end
    end

    Note over User,Wk: Start or Stop a measurement
    User->>TB: click Start/Stop
    TB-->>W: button pressed
    alt a measurement is already running
        W-->>Wk: ask worker to stop
        W->>TB: show "Stopping..."
    else idle
        W->>W: lock the UI (disable inputs, relabel Start → Stop)
        W-->>Wk: ask worker to start (with place, mean count, interval)

    Note over Wk: see sequence-measurement_actions.md
    Wk-->>W: measurement complete (with the result)
    W->>W: show the measure id in the status bar
    Wk-->>W: sequence finished
    W->>W: unlock the UI
    end
```

## Auto-mode loop

```mermaid
sequenceDiagram
    autonumber
    participant Wk as WorkerThread
    participant W as MainWindow
    participant S as State
    participant CP as ControlPanel
    participant Q as Timer

    Wk-->>W: sequence finished
    W->>S: is auto mode armed?
    opt yes, and we're still connected
        W->>CP: how many seconds between runs?
        CP-->>W: interval
        W->>Q: schedule the next run after that interval
        Note over Q: timer waits in the background<br/>without blocking the UI
        Q-->>W: time's up
        W->>S: still armed and still connected?
        opt yes
            W->>W: lock the UI
            W-->>Wk: ask worker to start the next measurement
        end
    end
```

Auto mode runs until: the user disarms it, the user disconnects (the worker
clears the auto flag on disconnect), or any error puts the connection in the
ERROR state.

## Open a measurement file

```mermaid
sequenceDiagram
    actor User
    participant CP as ControlPanel
    participant W as MainWindow
    participant FD as FileDialog
    participant OS as DefaultViewer

    User->>CP: click Open Measurement
    CP-->>W: open requested
    W->>FD: show file picker (limited to TSV files in data/measures)
    FD-->>W: chosen path (or empty if cancelled)
    opt user picked a file
        W->>W: check the path is really inside data/measures
        alt path is safe
            W->>OS: open the file with the system's default app
        else path escaped the sandbox
            W->>W: show a warning popup and refuse to open
        end
    end
```

## Log, warning, error popups

```mermaid
sequenceDiagram
    participant Wk as WorkerThread
    participant W as MainWindow
    participant LP as LogPanel
    participant MB as Popup

    Wk-->>W: log line (with level: INFO / WARNING / ERROR)
    alt level is WARNING
        W->>LP: append in yellow
    else level is ERROR
        W->>LP: append in red
    else
        W->>LP: append in default color
    end

    Wk-->>W: warning (only for popup-worthy cases)
    W->>MB: show a yellow warning popup (work continues)

    Wk-->>W: error
    W->>MB: show a red error popup (operation aborted)
```

Most warnings are log-only (yellow line in the log panel). The popup
warning channel is reserved for cases the user must acknowledge —
intentionally **not** used for advisory issues during connect (e.g. log
file unavailable, VNA temperature unreadable), which would otherwise
stack on top of any later error popup.

## Closing the window

```mermaid
sequenceDiagram
    actor User
    participant W as MainWindow
    participant S as State
    participant Wk as WorkerThread
    participant T as Thread

    User->>W: close the window
    opt a measurement is running
        W->>S: request stop
    end
    opt instruments are connected
        W->>Wk: detach the connection-status slot
        Note over W: late updates can't reach<br/>widgets that are being destroyed
        W-->>Wk: ask worker to disconnect
    end
    W->>T: tell the thread to quit
    W->>T: wait up to 10 seconds for it to finish
    alt thread finished cleanly
        T-->>W: done
    else timeout
        Note over W: print a warning and exit anyway —<br/>we never force-kill the thread<br/>(could leave the VNA in a bad state)
    end
    W->>W: let Qt finish closing the window
```

## When to read this vs the class view

- **This file (actions):** first read for a new contributor or non-developer
  stakeholder. Tells the story of "what the application window does, from
  startup to shutdown" without naming Qt classes or Python methods.
- **`sequence-window_classes.md`:** for the engineer who needs to find the
  code. Same flow, but every arrow names the actual widget, signal, slot,
  or method involved.
