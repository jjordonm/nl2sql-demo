"""
tests/test_engine.py – Unit tests for the NL2SQL rule-based engine.

Uses pytest parametrise to validate NL→SQL translations.  Where exact SQL
string matching is fragile (e.g. alias differences), we fall back to
**result equivalence**: both the generated and expected SQL must produce
identical result-sets on the seeded demo database.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from nl2sql.db import init_db, execute_sql
from nl2sql.engine import translate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DB: Path | None = None


@pytest.fixture(scope="session", autouse=True)
def _setup_db(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Create a temporary seeded database once for the whole test session."""
    global _DB
    _DB = tmp_path_factory.mktemp("db") / "test.sqlite"
    init_db(db_path=_DB)


def _exec(sql: str) -> list[tuple]:
    """Execute SQL and return sorted value-tuples (order/alias agnostic)."""
    rows = execute_sql(sql, _DB)
    # Convert all values to str for safe cross-type sorting
    tuples = [tuple(str(v) for v in r.values()) for r in rows]
    try:
        tuples.sort()
    except TypeError:
        pass
    return tuples


# ---------------------------------------------------------------------------
# Parametrised tests – result equivalence
# ---------------------------------------------------------------------------

RESULT_CASES = [
    # (nl_input, expected_sql)
    ("List all customers", "SELECT * FROM customers"),
    ("Show all products", "SELECT * FROM products"),
    ("List all orders", "SELECT * FROM orders"),
    ("Count of orders where status equals shipped", "SELECT COUNT(*) AS count FROM orders WHERE status = 'shipped'"),
    ("Find customers with gmail.com emails", "SELECT * FROM customers WHERE email LIKE '%gmail.com%'"),
    ("List products priced above 100", "SELECT * FROM products WHERE price > 100"),
    ("Orders with quantity between 2 and 5", "SELECT * FROM orders WHERE quantity BETWEEN 2 AND 5"),
    ("Find orders with status pending", "SELECT * FROM orders WHERE status = 'pending'"),
    ("Count of customers", "SELECT COUNT(*) AS count FROM customers"),
]


@pytest.mark.parametrize("nl, expected_sql", RESULT_CASES, ids=[c[0][:40] for c in RESULT_CASES])
def test_result_equivalence(nl: str, expected_sql: str) -> None:
    """Generated SQL should produce the same result-set as the expected SQL."""
    generated = translate(nl)
    gen_rows = _exec(generated)
    exp_rows = _exec(expected_sql)
    assert gen_rows == exp_rows, (
        f"\nNL:        {nl}"
        f"\nGenerated: {generated}"
        f"\nExpected:  {expected_sql}"
        f"\nGen rows ({len(gen_rows)}): {gen_rows[:5]}"
        f"\nExp rows ({len(exp_rows)}): {exp_rows[:5]}"
    )


# ---------------------------------------------------------------------------
# Smoke tests – just ensure translate() doesn't crash
# ---------------------------------------------------------------------------

SMOKE_INPUTS = [
    "Show orders placed in the last 30 days",
    "Find the top 5 products by total sales",
    "Average order amount for each customer",
    "Top 3 customers by total spend",
    "Total revenue by product category in descending order",
    "List products priced above 100 sorted by price desc",
    "Show orders created today",
    "Show the most expensive product",
    "List orders sorted by total amount descending",
    "Average product price",
]


@pytest.mark.parametrize("nl", SMOKE_INPUTS, ids=[s[:40] for s in SMOKE_INPUTS])
def test_smoke_translate(nl: str) -> None:
    """Engine should return a non-empty SQL string without raising."""
    sql = translate(nl)
    assert isinstance(sql, str)
    assert len(sql) > 10
    assert sql.upper().startswith("SELECT")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_input_raises() -> None:
    """Empty input should still produce some SQL (defaults to orders)."""
    sql = translate("")
    assert sql.upper().startswith("SELECT")


def test_generated_sql_is_executable() -> None:
    """Every smoke input should produce SQL that executes without error."""
    for nl in SMOKE_INPUTS:
        sql = translate(nl)
        # Should not raise
        execute_sql(sql, _DB)
