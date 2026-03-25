"""
db.py - SQLite bootstrap and seed-data loader.

Responsibilities
-----------------
* Dynamically create tables from the schema parsed from the Snowflake
  metadata CSV (``nl2sql.schema``).
* Load seed CSV files from ``data/seed/`` into the database.
* Provide a thin helper to execute arbitrary (read-only) SQL for the UI.

The database file lives at ``data/demo.sqlite`` by default.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from nl2sql.schema import TABLES

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _PROJECT_ROOT / "data" / "demo.sqlite"
SEED_DIR = _PROJECT_ROOT / "data" / "seed"

# ---------------------------------------------------------------------------
# Snowflake -> SQLite type mapping
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, str] = {
    "TEXT": "TEXT",
    "NUMBER": "REAL",
    "FLOAT": "REAL",
    "DATE": "TEXT",                 # stored as ISO strings
    "TIMESTAMP_LTZ": "TEXT",
    "TIMESTAMP_NTZ": "TEXT",
    "BOOLEAN": "INTEGER",
}


def _sqlite_type(snowflake_type: str) -> str:
    """Map a Snowflake type to a SQLite type."""
    return _TYPE_MAP.get(snowflake_type, "TEXT")


# ---------------------------------------------------------------------------
# Dynamic DDL generation
# ---------------------------------------------------------------------------

def _generate_ddl(table_name: str) -> str:
    """Generate a CREATE TABLE IF NOT EXISTS statement from schema metadata."""
    tdef = TABLES.get(table_name)
    if not tdef:
        raise ValueError(f"Unknown table: {table_name}")

    col_defs = []
    for cdef in tdef.columns.values():
        sqlite_t = _sqlite_type(cdef.data_type)
        # Bracket-quote column names that may contain special characters
        col_defs.append(f"    [{cdef.name}] {sqlite_t}")

    cols_sql = ",\n".join(col_defs)
    # Use bracket quoting for table names that may contain special chars (e.g. /SAPLOM/...)
    return f'CREATE TABLE IF NOT EXISTS [{table_name}] (\n{cols_sql}\n);'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection (with Row factory)."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(*, force: bool = False, db_path: Path | None = None) -> Path:
    """Create tables and load seed CSVs.

    Parameters
    ----------
    force : bool
        If ``True``, delete the existing DB file and recreate from scratch.
    db_path : Path | None
        Override the default database path (useful for tests).

    Returns
    -------
    Path
        The path to the initialised database file.
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if force and path.exists():
        path.unlink()

    already_existed = path.exists()
    conn = sqlite3.connect(str(path))

    try:
        # Create all tables from the schema CSV.
        for tname in TABLES:
            ddl = _generate_ddl(tname)
            conn.execute(ddl)
        conn.commit()

        # Only seed when the DB is freshly created (or forced).
        if not already_existed:
            _seed(conn)
    finally:
        conn.close()

    return path


def execute_sql(sql: str, db_path: Path | None = None) -> list[dict]:
    """Execute *sql* against the demo DB and return rows as dicts.

    Only SELECT statements are permitted.

    Raises
    ------
    ValueError
        If the SQL appears to be a write statement.
    """
    trimmed = sql.strip().upper()
    if not trimmed.startswith("SELECT") and not trimmed.startswith("WITH"):
        raise ValueError("Only SELECT / WITH statements are allowed.")

    conn = get_connection(db_path)
    try:
        cur = conn.execute(sql)
        cols = [desc[0] for desc in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _seed(conn: sqlite3.Connection) -> None:
    """Insert rows from CSV files into corresponding tables."""
    for table_name, tdef in TABLES.items():
        csv_path = SEED_DIR / f"{table_name}.csv"
        if not csv_path.exists():
            continue

        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                cols = [c for c in tdef.column_names if c in row]
                placeholders = ", ".join(["?"] * len(cols))
                col_names = ", ".join(cols)
                values = [row[c] for c in cols]
                conn.execute(
                    f"INSERT OR IGNORE INTO {table_name} ({col_names}) VALUES ({placeholders})",
                    values,
                )

    conn.commit()
