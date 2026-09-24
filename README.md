# TDAM Acquisition Suite

Desktop acquisition application for a crosshole-radar measurement bench: it
drives a **vector network analyser** and an **STM32** microcontroller over
serial, runs long unattended measurement campaigns, and stores each sweep with
its metadata.

Built during a research placement at **SUPSI — Istituto sistemi e elettronica
applicata (ISEA)**, Lugano. Version 1.0.3.

## What it does

A campaign is a long, repetitive, error-prone sequence: position the antenna
array, trigger a sweep, read S-parameters off the VNA, advance the motor, write
the result somewhere it will not be lost, and do it again for hours. The
application turns that into one configured run, with a live plot, a log the
operator can read while it runs, and a database that survives a crash halfway
through.

## Architecture

```
src/tdam/
  main.py              entry point
  core/
    config.py          typed configuration, validated on load
    state.py           shared application state behind a lock
    vna_client.py      VNA command protocol
    serial_device.py   serial transport for the STM32
    measurement.py     sweep orchestration and data model
    worker.py          the QThread that owns all hardware I/O
    database.py        SQLite persistence
    logger.py          structured logging to file and to the UI
    process_launcher.py  external process control
  ui/
    main_window.py     frameless main window
    widgets/           control panel, instruments header, log panel,
                       status bar, custom title bar
    splash.py, theme.py
```

The split is the design: **`core/` never imports from `ui/`**. Hardware I/O
happens on the worker thread and reaches the interface only through Qt signals,
which is what keeps the window responsive through a multi-hour campaign and
what makes `core/` testable without a running Qt application.

### Threading invariants

Qt concurrency bugs do not fail a test suite — they surface as a frozen window
or a silent data race weeks later. The ten rules this codebase holds itself to
are therefore written down and audited on every change by a purpose-built
review agent rather than left to memory:

- no blocking call on the UI thread
- all hardware I/O on the worker `QThread`, never on the UI thread
- cross-thread communication by signal/slot only
- `sqlite3` connections respect thread affinity
- shared state is only touched under the `AppState` lock
- long loops check their stop flag and shut down cleanly
- no `return` inside a `finally` block
- `QMessageBox` and other dialogs only from the UI thread

## Testing

**146 test functions across 12 files**, on `pytest` with `pytest-qt` for the
widget and signal tests and `pytest-cov` for coverage:

| Area | Tests |
|---|---|
| `test_config` | 19 |
| `test_process_launcher` | 16 |
| `test_database` | 14 |
| `test_logger`, `test_serial_device`, `test_state` | 13 each |
| `test_measurement` | 11 |
| `test_ingest`, `test_vna_client`, `test_widgets_title_bar` | 10 each |
| `test_widgets_control_panel` | 9 |
| `test_worker` | 8 |

```bash
uv sync --extra dev
uv run pytest
uv run pytest --cov
uv run ruff check .
```

## Running and packaging

```bash
uv sync
uv run tdam                 # or: uv run python tdam_launcher.py
```

Packaged for operators as a single Windows executable:

```bash
uv run pyinstaller tdam.spec
```

`tdam.spec` and `tdam.ico` are checked in so the build is reproducible; the
launcher exists as a stable entry point for it.

## Requirements

Python 3.14 or later. Runtime dependencies are `PySide6`, `pyserial`,
`pyqtgraph` and `numpy`; development adds `pytest`, `pytest-qt`, `pytest-cov`,
`ruff` and `pyinstaller`. Configuration lives in `config/`.

Hardware — the VNA and the STM32 board — is not simulated. Without it the
application starts and the suite passes, but no campaign will run.
