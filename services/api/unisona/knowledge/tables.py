"""Structured data (CSV/XLSX) → DuckDB, queried with validated read-only SQL.

A spreadsheet of 10,000 orders must not become 10,000 noisy chunks. Tables are loaded
into a per-knowledge-base DuckDB file; the agent gets a `query_table` tool and the
LLM writes SQL that is checked before it runs (single SELECT/WITH, allow-listed table,
no file or extension access, LIMIT enforced, read-only connection).
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from ..config import settings
from ..log import get_logger

log = get_logger("tables")
_FORBIDDEN = re.compile(r"\b(attach|copy|install|load|pragma|export|import|create|insert|update|delete|drop|alter|call|set|read_csv|read_parquet|read_json|glob|httpfs)\b", re.I)


def db_path(kb_id: str) -> Path:
    p = settings.data_path / "tables"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{kb_id}.duckdb"


def safe_name(name: str) -> str:
    base = re.sub(r"\.[a-z0-9]+$", "", name.lower())
    base = re.sub(r"[^a-z0-9_]+", "_", base).strip("_") or "data"
    return ("t_" + base)[:48]


def _load_sync(kb_id: str, table: str, columns: list[str], rows: list[dict]) -> dict:
    import duckdb

    con = duckdb.connect(str(db_path(kb_id)))
    try:
        cols = [re.sub(r"[^A-Za-z0-9_]+", "_", c).strip("_") or f"col{i}" for i, c in enumerate(columns)]
        con.execute(f'DROP TABLE IF EXISTS "{table}"')
        con.execute(f'CREATE TABLE "{table}" (' + ", ".join(f'"{c}" VARCHAR' for c in cols) + ")")
        data = [[("" if r.get(orig) is None else str(r.get(orig))) for orig in columns] for r in rows]
        if data:
            con.executemany(f'INSERT INTO "{table}" VALUES (' + ", ".join("?" for _ in cols) + ")", data)
        # Promote numeric-looking columns so SUM/AVG/comparisons work.
        for c in cols:
            try:
                bad, filled = con.execute(
                    f'SELECT COUNT(*) FILTER (WHERE "{c}" <> \'\' AND TRY_CAST("{c}" AS DOUBLE) IS NULL), '
                    f'COUNT(*) FILTER (WHERE "{c}" <> \'\') FROM "{table}"'
                ).fetchone()
                if filled and not bad:
                    con.execute(f'ALTER TABLE "{table}" ALTER "{c}" TYPE DOUBLE USING TRY_CAST(NULLIF("{c}", \'\') AS DOUBLE)')
            except Exception:
                pass
        schema = con.execute(f"DESCRIBE \"{table}\"").fetchall()
        sample = con.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
        return {
            "table": table,
            "columns": [{"name": s[0], "type": s[1]} for s in schema],
            "sample_rows": [dict(zip([s[0] for s in schema], [str(v) for v in row])) for row in sample],
            "row_count": len(data),
        }
    finally:
        con.close()


async def load_table(kb_id: str, table: str, columns: list[str], rows: list[dict]) -> dict:
    return await asyncio.to_thread(_load_sync, kb_id, table, columns, rows)


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise ValueError("Only one statement is allowed.")
    if not re.match(r"^(select|with)\b", s, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if _FORBIDDEN.search(s):
        raise ValueError("Query uses a forbidden keyword.")
    referenced = {t.strip('"').lower() for t in re.findall(r'\b(?:from|join)\s+("?[A-Za-z_][\w]*"?)', s, re.I)}
    ctes = {c.lower() for c in re.findall(r"\b([A-Za-z_]\w*)\s+as\s*\(", s, re.I)}
    unknown = referenced - {t.lower() for t in allowed_tables} - ctes
    if unknown:
        raise ValueError(f"Unknown table(s): {', '.join(sorted(unknown))}")
    if not re.search(r"\blimit\s+\d+\s*$", s, re.I):
        s += " LIMIT 50"
    return s


def _run_sync(kb_id: str, sql: str) -> dict:
    import duckdb

    con = duckdb.connect(str(db_path(kb_id)), read_only=True)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(50)
        return {"columns": cols, "rows": [dict(zip(cols, [v if isinstance(v, (int, float)) or v is None else str(v) for v in r])) for r in rows]}
    finally:
        con.close()


async def run_query(kb_id: str, sql: str, allowed_tables: set[str]) -> dict:
    checked = validate_sql(sql, allowed_tables)
    result = await asyncio.to_thread(_run_sync, kb_id, checked)
    result["sql"] = checked
    return result
