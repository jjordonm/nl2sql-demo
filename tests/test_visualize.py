"""Tests for the auto-visualization suggestion engine."""

import pandas as pd
import pytest

from nl2sql.visualize import suggest_chart


class TestSuggestChart:
    """Tests for suggest_chart()."""

    def test_returns_none_for_empty_dataframe(self):
        df = pd.DataFrame()
        assert suggest_chart(df, "") is None

    def test_returns_none_for_none(self):
        assert suggest_chart(None, "") is None

    def test_returns_none_for_single_scalar(self):
        df = pd.DataFrame({"count": [42]})
        assert suggest_chart(df, "") is None

    def test_returns_none_for_no_numeric_columns(self):
        df = pd.DataFrame({"name": ["A", "B"], "city": ["X", "Y"]})
        assert suggest_chart(df, "") is None

    def test_bar_chart_for_categorical_grouping(self):
        df = pd.DataFrame({
            "PLANT": [f"P{i}" for i in range(15)],
            "TOTAL": [i * 100 for i in range(15)],
        })
        result = suggest_chart(df, "total value per plant")
        assert result is not None
        assert result["chart_type"] == "bar"
        assert result["x"] == "PLANT"
        assert result["y"] == "TOTAL"

    def test_pie_chart_for_distribution(self):
        df = pd.DataFrame({"VENDOR": ["A", "B", "C"], "COUNT": [10, 20, 30]})
        result = suggest_chart(df, "breakdown by vendor")
        assert result is not None
        assert result["chart_type"] == "pie"

    def test_line_chart_for_trend(self):
        df = pd.DataFrame({
            "ORDER_DATE": ["2024-01", "2024-02", "2024-03"],
            "VALUE": [100, 150, 200],
        })
        result = suggest_chart(df, "orders over time by month")
        assert result is not None
        assert result["chart_type"] == "line"

    def test_scatter_for_two_numeric_columns(self):
        df = pd.DataFrame({
            "QTY": range(10),
            "VALUE": range(0, 100, 10),
        })
        result = suggest_chart(df, "qty vs value")
        assert result is not None
        assert result["chart_type"] == "scatter"

    def test_chart_spec_has_required_keys(self):
        df = pd.DataFrame({"PLANT": ["P1", "P2"], "TOTAL": [100, 200]})
        result = suggest_chart(df, "total by plant")
        assert result is not None
        assert "chart_type" in result
        assert "x" in result
        assert "y" in result
        assert "title" in result

    def test_many_rows_still_returns_chart(self):
        df = pd.DataFrame({
            "ITEM": [f"Item_{i}" for i in range(50)],
            "VALUE": range(50),
        })
        result = suggest_chart(df, "all items by value")
        assert result is not None
