"""
eval.py – Golden-SQL evaluation and comparison utilities.

This module loads golden NL→SQL examples from a JSONL file, generates SQL
for each NL prompt using the engine, and compares results.  Two comparison
modes are supported:

1. **String comparison** – normalise whitespace and compare SQL text.
2. **Result comparison** (recommended) – execute both the generated and
   golden SQL against the same SQLite database and compare the result sets.

Usage
-----
>>> from nl2sql.eval import run_evaluation
>>> report = run_evaluation()
>>> print(report.summary())
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from nl2sql.db import DB_PATH, execute_sql, init_db
from nl2sql.engine import translate

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = _PROJECT_ROOT / "data" / "golden" / "golden.sql.jsonl"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """Result of evaluating one NL→SQL example."""

    nl: str
    golden_sql: str
    generated_sql: str
    notes: str = ""
    match: bool = False
    error: str | None = None


@dataclass
class EvalReport:
    """Aggregate evaluation report."""

    cases: list[CaseResult] = field(default_factory=list)

    # -- Computed properties ------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.match)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def accuracy(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0

    @property
    def mismatches(self) -> list[CaseResult]:
        return [c for c in self.cases if not c.match]

    def summary(self) -> str:
        lines = [
            f"Evaluation Report",
            f"-----------------",
            f"Total : {self.total}",
            f"Passed: {self.passed}",
            f"Failed: {self.failed}",
            f"Accuracy: {self.accuracy:.1f}%",
        ]
        if self.mismatches:
            lines.append("")
            lines.append("Mismatches:")
            for c in self.mismatches:
                lines.append(f"  NL       : {c.nl}")
                lines.append(f"  Golden   : {c.golden_sql}")
                lines.append(f"  Generated: {c.generated_sql}")
                if c.error:
                    lines.append(f"  Error    : {c.error}")
                lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_golden(path: Path | None = None) -> list[dict]:
    """Load the golden examples from JSONL.

    Each line is a JSON object with keys: nl, sql, notes (optional).
    """
    p = path or GOLDEN_PATH
    examples: list[dict] = []
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def run_evaluation(
    *,
    golden_path: Path | None = None,
    db_path: Path | None = None,
    mode: str = "result",
) -> EvalReport:
    """Run the full evaluation suite.

    Parameters
    ----------
    golden_path : Path | None
        Path to the golden JSONL file.
    db_path : Path | None
        Path to the SQLite database (will be initialised if missing).
    mode : str
        ``"result"`` compares query result-sets; ``"string"`` compares
        normalised SQL text.

    Returns
    -------
    EvalReport
    """
    # Ensure DB exists
    effective_db = db_path or DB_PATH
    if not effective_db.exists():
        init_db(db_path=effective_db)

    examples = load_golden(golden_path)
    report = EvalReport()

    for ex in examples:
        nl = ex["nl"]
        golden_sql = ex["sql"]
        notes = ex.get("notes", "")

        # Generate SQL
        try:
            generated_sql = translate(nl)
        except Exception as exc:
            report.cases.append(
                CaseResult(
                    nl=nl,
                    golden_sql=golden_sql,
                    generated_sql="",
                    notes=notes,
                    match=False,
                    error=f"Translation error: {exc}",
                )
            )
            continue

        # Compare
        if mode == "string":
            match = _normalise_sql(generated_sql) == _normalise_sql(golden_sql)
        else:
            match, error = _compare_results(generated_sql, golden_sql, effective_db)
            if error:
                report.cases.append(
                    CaseResult(
                        nl=nl,
                        golden_sql=golden_sql,
                        generated_sql=generated_sql,
                        notes=notes,
                        match=False,
                        error=error,
                    )
                )
                continue

        report.cases.append(
            CaseResult(
                nl=nl,
                golden_sql=golden_sql,
                generated_sql=generated_sql,
                notes=notes,
                match=match,
            )
        )

    return report


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _normalise_sql(sql: str) -> str:
    """Collapse whitespace and lowercase for string comparison."""
    return re.sub(r"\s+", " ", sql.strip().lower())


def _compare_results(
    gen_sql: str, golden_sql: str, db_path: Path
) -> tuple[bool, str | None]:
    """Execute both queries and compare result sets.

    Returns ``(match: bool, error_msg: str | None)``.
    """
    try:
        gen_rows = execute_sql(gen_sql, db_path)
    except Exception as exc:
        return False, f"Generated SQL error: {exc}"

    try:
        gold_rows = execute_sql(golden_sql, db_path)
    except Exception as exc:
        return False, f"Golden SQL error: {exc}"

    # Normalize rows: sort each row's keys and the overall list
    gen_set = _rows_to_comparable(gen_rows)
    gold_set = _rows_to_comparable(gold_rows)

    return gen_set == gold_set, None


def _rows_to_comparable(rows: list[dict]) -> list[tuple]:
    """Convert rows to a sorted list of tuples for comparison.

    Compares values only (ignoring column alias names) so that
    ``SELECT COUNT(*) AS count`` matches ``SELECT COUNT(*) AS cnt``.
    """
    result = []
    for row in rows:
        # Sort by key for deterministic ordering within each row,
        # then just keep the values tuple.
        sorted_vals = tuple(v for _, v in sorted(row.items()))
        result.append(sorted_vals)
    # Sort the entire list so row order doesn't matter.
    try:
        result.sort()
    except TypeError:
        pass  # mixed types – compare as-is
    return result
