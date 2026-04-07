"""
visualize.py - Auto-visualization suggestions for query results.

Analyzes a DataFrame's shape and column types to suggest the most appropriate
chart type.  The suggestion is returned as a dict spec that the Streamlit UI
can render with its built-in charting helpers (bar, line, area, scatter) or
Plotly (pie).
"""

from __future__ import annotations

import re

import pandas as pd

# ---------------------------------------------------------------------------
# Heuristic chart suggestion
# ---------------------------------------------------------------------------

_AGG_KEYWORDS = re.compile(
    r"\b(count|total|sum|average|avg|max|min|top|bottom)\b",
    re.IGNORECASE,
)

_TREND_KEYWORDS = re.compile(
    r"\b(trend|over time|by month|by year|by date|by week|monthly|yearly|daily|timeline)\b",
    re.IGNORECASE,
)

_DISTRIBUTION_KEYWORDS = re.compile(
    r"\b(distribution|breakdown|proportion|share|percent|percentage|composition|by)\b",
    re.IGNORECASE,
)


def suggest_chart(df: pd.DataFrame, nl_query: str = "") -> dict | None:
    """Suggest a chart type and axes for *df* based on its shape and *nl_query*.

    Returns
    -------
    dict | None
        ``{"chart_type": ..., "x": ..., "y": ..., "title": ...}`` or ``None``
        if no chart is appropriate (e.g. single-row scalar result).
    """
    if df is None or df.empty:
        return None

    nrows, ncols = df.shape

    # Single scalar value — nothing to chart
    if nrows == 1 and ncols == 1:
        return None

    # Classify columns
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

    # Not enough structure to chart
    if not numeric_cols:
        return None

    # --- Decide chart type ---

    # 1. Trend / time-series: date-like x-axis
    date_col = _find_date_column(df, non_numeric_cols)
    if date_col and _TREND_KEYWORDS.search(nl_query):
        y_col = numeric_cols[0]
        return {
            "chart_type": "line",
            "x": date_col,
            "y": y_col,
            "title": f"{y_col} over {date_col}",
        }

    # 2. Pie chart: small number of categories + single numeric column + distribution query
    if (
        len(non_numeric_cols) == 1
        and len(numeric_cols) == 1
        and 2 <= nrows <= 12
        and _DISTRIBUTION_KEYWORDS.search(nl_query)
    ):
        return {
            "chart_type": "pie",
            "x": non_numeric_cols[0],
            "y": numeric_cols[0],
            "title": f"{numeric_cols[0]} by {non_numeric_cols[0]}",
        }

    # 3. Bar chart: categorical x + numeric y (aggregation or top-N)
    if non_numeric_cols and numeric_cols:
        x_col = non_numeric_cols[0]
        y_col = numeric_cols[0]
        unique_ratio = df[x_col].nunique() / max(nrows, 1)

        # Use bar chart when there's a clear categorical grouping
        if unique_ratio > 0.5 and nrows <= 50:
            return {
                "chart_type": "bar",
                "x": x_col,
                "y": y_col,
                "title": f"{y_col} by {x_col}",
            }

    # 4. Scatter: two numeric columns, many rows
    if len(numeric_cols) >= 2 and nrows > 5:
        return {
            "chart_type": "scatter",
            "x": numeric_cols[0],
            "y": numeric_cols[1],
            "title": f"{numeric_cols[1]} vs {numeric_cols[0]}",
        }

    # 5. Fallback bar chart for simple aggregation results
    if non_numeric_cols and numeric_cols and nrows <= 50:
        return {
            "chart_type": "bar",
            "x": non_numeric_cols[0],
            "y": numeric_cols[0],
            "title": f"{numeric_cols[0]} by {non_numeric_cols[0]}",
        }

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_date_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first column that looks like a date."""
    date_hints = re.compile(r"(date|time|month|year|day|period|week)", re.IGNORECASE)
    for col in candidates:
        if date_hints.search(col):
            return col
    # Try parsing
    for col in candidates:
        try:
            pd.to_datetime(df[col], errors="raise")
            return col
        except (ValueError, TypeError):
            continue
    return None
