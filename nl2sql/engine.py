"""
engine.py - Rule-based Natural Language to SQL translator (fallback).

This engine provides a basic rule-based fallback for when the LLM is not
available. Given the complexity of the real Snowflake schema (28 tables,
thousands of columns), the LLM engine is strongly recommended. This module
handles only simple patterns against the key business tables.

For full capabilities, use the LLM engine (``nl2sql.llm_engine``).
"""

from __future__ import annotations

import re

from nl2sql.schema import TABLES, KEY_TABLES, all_table_names


def translate(nl: str) -> str:
    """Translate a natural-language question into SQL using simple rules.

    This is a best-effort fallback. It recognises:
    - Table mentions (maps known table name fragments)
    - Simple SELECT * / COUNT(*) / SUM / AVG patterns
    - Basic WHERE filters
    - LIMIT / TOP N

    For complex queries, use the LLM engine instead.
    """
    text = nl.strip()
    text_lower = text.lower()

    # --- Detect table ---
    table = _detect_table(text_lower)

    # --- Detect aggregate ---
    agg = _detect_aggregate(text_lower)

    # --- Detect limit ---
    limit = _detect_limit(text_lower)

    # --- Detect simple WHERE ---
    where = _detect_where(text_lower, table)

    # --- Assemble ---
    if agg:
        select = f"SELECT {agg} FROM {table}"
    else:
        select = f"SELECT * FROM {table}"

    if where:
        select += f" WHERE {where}"

    if limit:
        select += f" LIMIT {limit}"

    return select


def _detect_table(text: str) -> str:
    """Try to detect which table the user is asking about."""
    # Check for exact or partial table name matches
    text_upper = text.upper()

    # Priority: key business tables
    _TABLE_HINTS = {
        "purchase order": "AIML_OPEN_PURCHASE_ORDERS",
        "open po": "AIML_OPEN_PURCHASE_ORDERS",
        "po ": "AIML_OPEN_PURCHASE_ORDERS",
        "plant": "CORE_PLANT",
        "inventory": "EDW_INVENTORY_SEGMENTATION_SNAPSHOT",
        "segmentation": "EDW_INVENTORY_SEGMENTATION_SNAPSHOT",
        "demand": "EDW_MATL_LOC_DEMAND_INFO",
        "vendor": "LFA1",
        "material master": "MARA",
        "material description": "MAKT",
        "delivery": "LIPS",
        "company code": "T001",
    }

    for hint, tname in _TABLE_HINTS.items():
        if hint in text:
            return tname

    # Check if any full table name appears
    for tname in all_table_names():
        if tname in text_upper:
            return tname

    # Default
    return "AIML_OPEN_PURCHASE_ORDERS"


def _detect_aggregate(text: str) -> str | None:
    """Detect COUNT/SUM/AVG patterns."""
    if re.search(r"\bcount\b", text):
        return "COUNT(*)"
    if re.search(r"\btotal\s+open\s+value\b", text):
        return "SUM(OPEN_VALUE_IN_USD)"
    if re.search(r"\bsum\b.*\bopen.value\b", text):
        return "SUM(OPEN_VALUE_IN_USD)"
    if re.search(r"\baverage\b.*\bopen.value\b|\bavg\b.*\bopen.value\b", text):
        return "AVG(OPEN_VALUE_IN_USD)"
    if re.search(r"\bsum\b.*\bopen.qty\b", text):
        return "SUM(OPEN_QTY)"
    return None


def _detect_limit(text: str) -> int | None:
    """Detect TOP N / LIMIT N."""
    m = re.search(r"\btop\s+(\d+)\b", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\blimit\s+(\d+)\b", text)
    if m:
        return int(m.group(1))
    return None


def _detect_where(text: str, table: str) -> str | None:
    """Detect simple filter patterns."""
    clauses: list[str] = []

    # Vendor name
    m = re.search(r"vendor\s+(?:named?|=|is)\s+['\"]?([^'\"]+)['\"]?", text)
    if m and table == "AIML_OPEN_PURCHASE_ORDERS":
        val = _escape_sql_string(m.group(1).strip())
        clauses.append(f"VEND_NM = '{val}'")

    # Plant ID
    m = re.search(r"plant\s+(?:id\s+)?(?:=\s*)?['\"]?(\w+)['\"]?", text)
    if m:
        val = _escape_sql_string(m.group(1).strip())
        if val.upper() not in ("ID", "NAME", "CATEGORY"):
            clauses.append(f"PLANT_ID = '{val}'")

    # Status
    m = re.search(r"status\s+(?:=|equals?|is)\s+['\"]?(\w+)['\"]?", text)
    if m:
        val = _escape_sql_string(m.group(1).strip())
        clauses.append(f"SUPPLIER_TYPE = '{val}'")

    return " AND ".join(clauses) if clauses else None


def _escape_sql_string(value: str) -> str:
    """Escape single quotes in a value for safe SQL string literal embedding."""
    return value.replace("'", "''")
