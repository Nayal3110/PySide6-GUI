# Architecture Diagrams

Living reference for TDAM's runtime structure. Diagrams are hand-authored
Mermaid in Markdown — they render inline on GitHub and in any Markdown viewer
that supports the `mermaid` fenced-block extension.

## Diagrams

- **[`classes.md`](classes.md)** — static class diagram. The seven runtime
  classes (UI window, worker, state, sequence, logger, two device clients,
  the SQLite `SessionDB`) with ownership, dependency, and Qt signal-wiring relations.

- **[`sequence-measurement_classes.md`](sequence-measurement_classes.md)** —
  runtime flow of the hot path in code terms: **Start** click →
  `MeasurementSequence.run()` → command loop with `is_stop_requested()`
  checks → VNA `trigger_and_read` → `save_tsv` → `measurement_complete`.
  Every arrow names the actual class, method, or module function being
  called. Read this when you need to find the code.

- **[`sequence-measurement_actions.md`](sequence-measurement_actions.md)** —
  same flow, plain-language view. Each arrow describes *what the step does*
  ("claim the measurement slot", "trigger sweep and read S-parameters")
  without naming any Python function. Read this first for a project handover
  or to brief a non-developer stakeholder.
  
- **[`sequence-connect_classes.md`](sequence-connect_classes.md)** — startup
  orchestration in code terms: **Connect** click → open SQLite session DB →
  TRVNA launch → VNA TCP + assert ready → serial discovery →
  `connection_status`. Every arrow names the actual class, method, or module
  function being called. Read this when you need to find the code.

- **[`sequence-connect_actions.md`](sequence-connect_actions.md)** — same
  flow, plain-language view. Each arrow describes *what the step does*
  ("read VNA settings from TOML", "broadcast SP, accept TSP reply") without
  naming any Python function. Read this first for a project handover or to
  brief a non-developer stakeholder.

- **[`sequence-window_classes.md`](sequence-window_classes.md)** — UI-thread
  view in code terms: `TDAMMainWindow` construction, signal/slot wiring of
  the worker thread, the click-to-signal handlers (theme, mode, connect,
  start/stop, open file), the auto-mode timer loop, and the `closeEvent`
  shutdown path. Read this when you need to find the UI code.

- **[`sequence-window_actions.md`](sequence-window_actions.md)** — same
  lifecycle, plain-language view. Each arrow describes *what the window
  does* ("lock the UI", "show a red error popup") without naming Qt classes
  or methods. Read this first for a project handover.

- **[`state.md`](state.md)** — the two state machines on `AppState`
  (`ConnectionState` and `MeasurePhase`) plus the orthogonal `auto_armed`
  flag.

## Viewing

- **GitHub** renders Mermaid natively in `.md` previews — no setup required.
- **VSCode**: install [`bierner.markdown-mermaid`](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)
  ("Markdown Preview Mermaid Support") and use `Ctrl+Shift+V`. Same renderer
  as GitHub, so parity is high.
- Other Markdown viewers (Obsidian, JetBrains, MarkText) also support
  Mermaid out of the box.


