from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path(root: Path) -> Path:
    return root / ".agent-buffet" / "agent_buffet.sqlite3"


def connect(root: Path) -> sqlite3.Connection:
    path = db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_db(root: Path) -> None:
    schema = files("agent_buffet.storage").joinpath("schema.sql").read_text(encoding="utf-8")
    with connect(root) as con:
        con.executescript(schema)


def record_agent(root: Path, name: str, config_path: Path, main_path: Path | None = None, notes: str | None = None) -> None:
    with connect(root) as con:
        con.execute(
            """
            insert into agents(name, created_at, config_path, main_path, notes)
            values (?, ?, ?, ?, ?)
            on conflict(name) do update set
              config_path = excluded.config_path,
              main_path = excluded.main_path,
              notes = excluded.notes
            """,
            (name, utc_now(), str(config_path), str(main_path) if main_path else None, notes),
        )


def record_run(
    root: Path,
    run_id: str,
    agent_path: Path,
    opponents: list[str],
    games: int,
    metrics: dict[str, Any],
    report_path: Path | None,
) -> None:
    with connect(root) as con:
        con.execute(
            """
            insert into runs(id, created_at, agent_path, opponents, games, metrics_json, report_path)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                utc_now(),
                str(agent_path),
                ",".join(opponents),
                games,
                json.dumps(metrics, sort_keys=True),
                str(report_path) if report_path else None,
            ),
        )


def latest_run(root: Path) -> dict[str, Any] | None:
    with connect(root) as con:
        row = con.execute("select * from runs order by created_at desc limit 1").fetchone()
    if row is None:
        return None
    result = dict(row)
    result["metrics"] = json.loads(result.pop("metrics_json"))
    return result


def get_run(root: Path, run_id: str) -> dict[str, Any] | None:
    with connect(root) as con:
        row = con.execute("select * from runs where id = ?", (run_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["metrics"] = json.loads(result.pop("metrics_json"))
    return result


def record_mining_note(root: Path, source: str, command: str, output_path: Path, summary: str | None = None) -> None:
    with connect(root) as con:
        con.execute(
            """
            insert into mining_notes(created_at, source, command, output_path, summary)
            values (?, ?, ?, ?, ?)
            """,
            (utc_now(), source, command, str(output_path), summary),
        )


def list_mining_notes(root: Path, limit: int = 20) -> list[dict[str, Any]]:
    with connect(root) as con:
        rows = con.execute(
            "select * from mining_notes order by created_at desc limit ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
