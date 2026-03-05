"""
tests/test_eval.py – Tests for the golden-SQL evaluator.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nl2sql.db import init_db
from nl2sql.eval import EvalReport, load_golden, run_evaluation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DB: Path | None = None


@pytest.fixture(scope="session", autouse=True)
def _setup_db(tmp_path_factory: pytest.TempPathFactory) -> None:
    global _DB
    _DB = tmp_path_factory.mktemp("evaldb") / "test.sqlite"
    init_db(db_path=_DB)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_load_golden() -> None:
    """Golden JSONL should load as a non-empty list of dicts."""
    examples = load_golden()
    assert len(examples) >= 20
    for ex in examples:
        assert "nl" in ex
        assert "sql" in ex


def test_run_evaluation_returns_report() -> None:
    """Evaluator should run and return an EvalReport with metrics."""
    report = run_evaluation(db_path=_DB)
    assert isinstance(report, EvalReport)
    assert report.total >= 20
    assert 0 <= report.accuracy <= 100
    assert report.passed + report.failed == report.total


def test_report_summary_is_string() -> None:
    """The summary method should produce a readable string."""
    report = run_evaluation(db_path=_DB, mode="string")
    summary = report.summary()
    assert isinstance(summary, str)
    assert "Accuracy" in summary


def test_evaluation_string_mode() -> None:
    """String-comparison mode should also produce a valid report."""
    report = run_evaluation(db_path=_DB, mode="string")
    assert isinstance(report, EvalReport)
    assert report.total >= 20
