"""
schema.py - Schema definitions auto-loaded from the Snowflake column metadata CSV.

Instead of hard-coding table definitions, this module parses
``data/snowflake_table_columns.csv`` at import time and builds
``TABLES``, ``JOIN_RELATIONS``, and helper functions dynamically.

The CSV is the single source of truth for the schema.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_CSV = _PROJECT_ROOT / "data" / "snowflake_table_columns.csv"

# Snowflake fully-qualified prefix used in the source data.
DATABASE = "COLLINS_ANALYTICS"
SCHEMA_NAME = "COL_PUBLISHED"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ColumnDef:
    """Description of a single column."""
    name: str
    data_type: str          # TEXT, NUMBER, FLOAT, DATE, TIMESTAMP_LTZ, etc.
    ordinal_position: int


@dataclass
class TableDef:
    """Description of a single database table."""
    name: str                       # e.g. "AIML_OPEN_PURCHASE_ORDERS"
    columns: dict[str, ColumnDef]   # column_name -> ColumnDef (ordered)
    fq_name: str = ""              # Fully-qualified Snowflake name

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(self.columns.keys())

    @property
    def date_columns(self) -> list[str]:
        return [c.name for c in self.columns.values()
                if c.data_type in ("DATE", "TIMESTAMP_LTZ", "TIMESTAMP_NTZ")]

    @property
    def numeric_columns(self) -> list[str]:
        return [c.name for c in self.columns.values()
                if c.data_type in ("NUMBER", "FLOAT")]

    @property
    def text_columns(self) -> list[str]:
        return [c.name for c in self.columns.values()
                if c.data_type == "TEXT"]


@dataclass(frozen=True)
class JoinRelation:
    """Describes how two tables can be joined."""
    left_table: str
    right_table: str
    left_col: str
    right_col: str


# ---------------------------------------------------------------------------
# Parse CSV -> TABLES dict
# ---------------------------------------------------------------------------

def _load_tables_from_csv(csv_path: Path) -> dict[str, TableDef]:
    """Read the Snowflake metadata CSV and build a dict of TableDefs."""
    tables: dict[str, TableDef] = {}

    if not csv_path.exists():
        return tables

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            tname = row["object_name"]
            col_name = row["column_name"]
            dtype = row["data_type"]
            ordinal = int(row["ordinal_position"])
            fq = f"{row['database']}.{row['schema']}.{tname}"

            if tname not in tables:
                tables[tname] = TableDef(name=tname, columns={}, fq_name=fq)

            tables[tname].columns[col_name] = ColumnDef(
                name=col_name, data_type=dtype, ordinal_position=ordinal
            )

    return tables


TABLES: dict[str, TableDef] = _load_tables_from_csv(SCHEMA_CSV)


# ---------------------------------------------------------------------------
# Join relations (curated from the SAP/Snowflake schema)
# ---------------------------------------------------------------------------

JOIN_RELATIONS: list[JoinRelation] = [
    # Business views
    JoinRelation("AIML_OPEN_PURCHASE_ORDERS", "CORE_PLANT", "PLANT_ID", "PLANT_ID"),
    JoinRelation("EDW_INVENTORY_SEGMENTATION_SNAPSHOT", "CORE_PLANT", "PLANT_ID", "PLANT_ID"),
    # SAP PO header -> PO item -> schedule line
    JoinRelation("EKKO", "EKPO", "EBELN", "EBELN"),
    JoinRelation("EKPO", "EKET", "EBELN", "EBELN"),
    JoinRelation("EKES", "EKPO", "EBELN", "EBELN"),
    # PO -> vendor
    JoinRelation("EKKO", "LFA1", "LIFNR", "LIFNR"),
    # Material master chain
    JoinRelation("MARA", "MAKT", "MATNR", "MATNR"),
    JoinRelation("MARA", "MARC", "MATNR", "MATNR"),
    JoinRelation("MARC", "MARD", "MATNR", "MATNR"),
    JoinRelation("MARC", "MBEW", "MATNR", "MATNR"),
    # Plant master
    JoinRelation("T001W", "MARC", "WERKS", "WERKS"),
    # Company code
    JoinRelation("T001", "EKKO", "BUKRS", "BUKRS"),
    JoinRelation("T001K", "MBEW", "BWKEY", "BWKEY"),
    # Reference tables
    JoinRelation("T023T", "EKPO", "MATKL", "MATKL"),
    JoinRelation("T024", "EKKO", "EKGRP", "EKGRP"),
    # Delivery
    JoinRelation("LIPS", "EKPO", "VGBEL", "EBELN"),
]


# ---------------------------------------------------------------------------
# Key business tables (most likely to be queried by users)
# ---------------------------------------------------------------------------

KEY_TABLES = [
    "AIML_OPEN_PURCHASE_ORDERS",
    "CORE_PLANT",
    "EDW_INVENTORY_SEGMENTATION_SNAPSHOT",
    "EDW_MATL_LOC_DEMAND_INFO",
]


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def all_table_names() -> set[str]:
    """Return the set of valid table names."""
    return set(TABLES.keys())


def all_column_names() -> set[str]:
    """Return every column across all tables."""
    cols: set[str] = set()
    for tbl in TABLES.values():
        cols.update(tbl.columns.keys())
    return cols


def columns_for(table: str) -> tuple[str, ...]:
    """Return column names for *table*, or empty tuple if unknown."""
    tdef = TABLES.get(table)
    return tdef.column_names if tdef else ()


def find_join(left: str, right: str) -> JoinRelation | None:
    """Return the join relation between two tables, or None."""
    for jr in JOIN_RELATIONS:
        if (jr.left_table == left and jr.right_table == right) or \
           (jr.left_table == right and jr.right_table == left):
            return jr
    return None


def schema_for_llm() -> str:
    """Return a complete schema description optimised for the LLM prompt.

    Shows all columns with types so the LLM can write accurate SQL.
    """
    lines: list[str] = []
    for tname, tdef in TABLES.items():
        cols = [f"{c.name} {c.data_type}" for c in tdef.columns.values()]
        lines.append(f"{tname}({', '.join(cols)})")

    lines.append("")
    lines.append("Join relationships:")
    for jr in JOIN_RELATIONS:
        lines.append(f"  {jr.left_table}.{jr.left_col} = {jr.right_table}.{jr.right_col}")

    return "\n".join(lines)
