"""TDAM log ingestion — parses ``log.log`` files into a SQLite database.

Intended for deployments where ``.exe`` rigs ship their file logs back: this
script ingests them into a central ``tdam.db`` for querying and dashboards.

Usage
-----
    python scripts/tdam_ingest.py path/to/log.log [more.log ...]
    python scripts/tdam_ingest.py data/log/log.log --db-path /srv/tdam/tdam.db
    python scripts/tdam_ingest.py data/log/*.log --dry-run

Idempotency
-----------
Sessions are deduplicated on the session id (= start timestamp). Re-running the
same file does not create duplicate sessions, so this script is safe to run
on a cron / on every return.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow running this script directly from the repo root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tdam.core.database import SessionDB  # noqa: E402

# ── Log-format grammar ──────────────────────────────────────────────────
# Session banners use em-dashes (U+2014). The timestamp on the SESSION line is
# also the session's database id; it may carry a ``~N`` disambiguation suffix.
_SESSION_START_RE = re.compile(
    r"^─── SESSION (?P<place>.+?) — "
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}(?:~\d+)?) "
    r"(?P<tz>UTC|[+-]\d{2,4}) ───$"
)
_SESSION_END_RE = re.compile(
    r"^─── SESSION END — Reason: (?P<closing>.+?) — "
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) "
    r"(?P<tz>UTC|[+-]\d{2,4}) ───$"
)
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \| "
    r"(?P<level>\w+)\s+\| "
    r"(?:\[(?P<error_type>\w+)\] )?"
    r"(?P<message>.+)$"
)


@dataclass
class _ParsedSession:
    place: str
    started_at: str  # also the session id
    ended_at: str | None = None
    closing_msg: str | None = None
    entries: list[dict] = field(default_factory=list)


def parse_log_file(path: Path) -> list[_ParsedSession]:
    """Parse a TDAM log file into a list of sessions with their entries.

    Lines that don't match the grammar (e.g. raw markers like
    ``#START_MEASURE``) are silently skipped — they belong to the TSV format,
    not the structured log.
    """
    sessions: list[_ParsedSession] = []
    current: _ParsedSession | None = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue

            # Check end first — start regex would otherwise greedily match
            # the literal "END" token as a session id.
            m = _SESSION_END_RE.match(line)
            if m and current is not None:
                current.closing_msg = m["closing"]
                current.ended_at = m["ts"]
                sessions.append(current)
                current = None
                continue

            m = _SESSION_START_RE.match(line)
            if m:
                if current is not None:
                    # Previous session never closed (likely a crash) — flush as-is
                    sessions.append(current)
                current = _ParsedSession(place=m["place"], started_at=m["ts"])
                continue

            m = _LOG_LINE_RE.match(line)
            if m and current is not None:
                entry = {
                    "timestamp": m["ts"],
                    "level": m["level"],
                    "message": m["message"],
                }
                if m["error_type"]:
                    entry["error_type"] = m["error_type"]
                current.entries.append(entry)

    if current is not None:
        sessions.append(current)

    return sessions


def ingest_sessions(db: SessionDB, sessions: list[_ParsedSession]) -> tuple[int, int]:
    """Insert sessions and their log entries into the database.

    Returns ``(inserted, skipped)``. Dedup is keyed on the session start
    timestamp (which is the session id), so re-running on the same file is a
    no-op. (If two genuinely different sessions ever shared a millisecond, the
    second to be ingested would be skipped — accepted; the file logs remain
    the source of truth.)
    """
    inserted = 0
    skipped = 0

    for sess in sessions:
        if db.session_exists(sess.started_at):
            skipped += 1
            continue

        db.import_session(
            place=sess.place,
            started_at=sess.started_at,
            ended_at=sess.ended_at,
            closing_msg=sess.closing_msg,
            entries=sess.entries,
        )
        inserted += 1

    return inserted, skipped


def _expand_paths(raw_paths: list[str]) -> list[Path]:
    """Expand glob patterns and de-duplicate the resulting file list."""
    out: list[Path] = []
    seen: set[Path] = set()
    for pattern in raw_paths:
        p = Path(pattern)
        # If the literal path exists, take it as-is; otherwise treat as glob
        if p.exists():
            candidates = [p]
        else:
            candidates = list(Path().glob(pattern))
        for c in candidates:
            resolved = c.resolve()
            if resolved not in seen:
                seen.add(resolved)
                out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest TDAM log.log files into a SQLite database."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="log file path(s) or glob patterns (e.g. data/log/*.log)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite file path (default: TDAM_DB_PATH env var or data/tdam.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report counts; do not write to the database",
    )
    args = parser.parse_args(argv)

    files = _expand_paths(args.paths)
    if not files:
        print("No matching log files.", file=sys.stderr)
        return 1

    db: SessionDB | None = None
    if not args.dry_run:
        try:
            db = SessionDB(db_path=args.db_path)
        except Exception as exc:
            print(f"Could not open the database: {exc}", file=sys.stderr)
            return 2

    totals = {"sessions": 0, "entries": 0, "inserted": 0, "skipped": 0}

    try:
        for path in files:
            print(f"\n{path}")
            sessions = parse_log_file(path)
            entry_count = sum(len(s.entries) for s in sessions)
            totals["sessions"] += len(sessions)
            totals["entries"] += entry_count
            print(f"  parsed: {len(sessions)} sessions, {entry_count} entries")

            if db is not None:
                inserted, skipped = ingest_sessions(db, sessions)
                totals["inserted"] += inserted
                totals["skipped"] += skipped
                print(f"  ingested: {inserted} new, {skipped} already in DB")
    finally:
        if db is not None:
            db.close()

    print()
    print("--- Summary ---")
    print(f"  Files processed: {len(files)}")
    print(f"  Sessions parsed: {totals['sessions']} ({totals['entries']} entries)")
    if not args.dry_run:
        print(f"  New in DB:       {totals['inserted']}")
        print(f"  Skipped (dup):   {totals['skipped']}")
    else:
        print("  (dry run -- nothing written)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
