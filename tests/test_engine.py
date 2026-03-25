"""tests/test_engine.py - Unit tests for the NL2SQL rule-based engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2sql.db import init_db, execute_sql
from nl2sql.engine import translate

_DB: Path | None = None


@pytest.fixture(scope="session", autouse=True)
def _setup_db(tmp_path_factory: pytest.TempPathFactory) -> None:
    global _DB
    _DB = tmp_path_factory.mktemp("db") / "test.sqlite"
    init_db(db_path=_DB)


# ---------------------------------------------------------------------------
# Result equivalence tests
# ---------------------------------------------------------------------------

RESULT_CASES = [
    ("List all open purchase orders", "SELECT * FROM AIML_OPEN_PURCHASE_ORDERS"),
    ("Show all plants", "SELECT * FROM CORE_PLANT"),
    ("Count of open purchase orders", "SELECT COUNT(*) FROM AIML_OPEN_PURCHASE_ORDERS"),
]


@pytest.mark.parametrize(
    "nl, expected_sql", RESULT_CASES, ids=[c[0][:40] for c in RESULT_CASES]
)
def test_result_equivalence(nl: str, expected_sql: str) -> None:
    generated = translate(nl)
    gen_rows = execute_sql(generated, _DB)
    exp_rows = execute_sql(expected_sql, _DB)
    assert len(gen_rows) == len(exp_rows), (
        f"Row count mismatch: {len(gen_rows)} vs {len(exp_rows)}"
        f"\nNL: {nl}\nGenerated: {generated}\nExpected: {expected_sql}"
    )


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

SMOKE_INPUTS = [
    "Show purchase orders for vendor Honeywell Aerospace",
    "Count of purchase orders",
    "Show inventory snapshots",
    "Show demand information",
    "Show plants",
    "List vendor details",
    "Show material master data",
]


@pytest.mark.parametrize("nl", SMOKE_INPUTS, ids=[s[:40] for s in SMOKE_INPUTS])
def test_smoke_translate(nl: str) -> None:
    sql = translate(nl)
    assert isinstance(sql, str)
    assert len(sql) > 10
    assert sql.upper().startswith("SELECT")


def test_empty_input() -> None:
    sql = translate("")
    assert sql.upper().startswith("SELECT")


def test_generated_sql_is_executable() -> None:
    for nl in SMOKE_INPUTS:
        sql = translate(nl)
        execute_sql(sql, _DB)
