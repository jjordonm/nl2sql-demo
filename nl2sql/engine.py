"""
engine.py – Rule-based Natural Language → SQL translator.

Design overview
----------------
1. **Tokenise & normalise** the input string.
2. **Detect intent** (select, count, sum, average).
3. **Identify tables** mentioned (directly or via column context).
4. **Extract columns** requested for projection.
5. **Parse filters** (WHERE clauses) – equality, comparison, LIKE, BETWEEN,
   date helpers.
6. **Parse aggregation / GROUP BY** hints.
7. **Parse sorting** (ORDER BY, ASC/DESC) and LIMIT (top-N).
8. **Determine joins** if multiple tables are involved.
9. **Assemble** a SQL string, strictly white-listing identifiers from the
   schema to prevent injection.

Extending the engine
---------------------
* **New filter patterns**: add entries to ``_FILTER_PATTERNS`` or the
  ``_extract_filters`` function.
* **New aggregation verbs**: extend ``_AGGREGATE_MAP``.
* **Swap in an LLM**: replace ``translate()`` with a call to your LLM and
  keep the same signature so callers don't change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nl2sql.schema import (
    COLUMN_ALIASES,
    JOIN_RELATIONS,
    TABLES,
    all_column_names,
    all_table_names,
    columns_for,
    find_join,
    resolve_table_alias,
)

# ---------------------------------------------------------------------------
# Constants / mappings
# ---------------------------------------------------------------------------

# Words that signal a SELECT intent.
_SELECT_VERBS = {"show", "list", "find", "get", "display", "fetch", "retrieve"}

# Aggregate function keywords.
_AGGREGATE_MAP: dict[str, str] = {
    "count": "COUNT",
    "sum": "SUM",
    "average": "AVG",
    "avg": "AVG",
    "total": "SUM",
    "minimum": "MIN",
    "min": "MIN",
    "maximum": "MAX",
    "max": "MAX",
}

# Comparison operators the user might say.
_COMP_WORDS: dict[str, str] = {
    "equals": "=",
    "equal to": "=",
    "equal": "=",
    "is": "=",
    "greater than": ">",
    "more than": ">",
    "above": ">",
    "over": ">",
    "less than": "<",
    "below": "<",
    "under": "<",
    "at least": ">=",
    "at most": "<=",
}

# Date-phrase → SQLite expression mapping.
_DATE_PHRASES: dict[str, str] = {
    "today": "date('now')",
    "yesterday": "date('now', '-1 day')",
    "last 7 days": "date('now', '-7 days')",
    "last 30 days": "date('now', '-30 days')",
    "last 90 days": "date('now', '-90 days')",
    "this week": "date('now', 'weekday 0', '-7 days')",
    "this month": "date('now', 'start of month')",
    "this year": "date('now', 'start of year')",
}


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------

@dataclass
class _QueryPlan:
    """Intermediate representation built while parsing."""

    tables: list[str] = field(default_factory=list)
    select_cols: list[str] = field(default_factory=list)
    where_clauses: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None
    aggregate_fn: str | None = None
    aggregate_col: str | None = None
    joins: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def translate(nl: str) -> str:
    """Translate a natural-language question into a SQL query.

    Parameters
    ----------
    nl : str
        The user's natural language input (e.g. "Show all orders").

    Returns
    -------
    str
        A SQL SELECT string safe to execute against the demo DB.

    Raises
    ------
    ValueError
        When the input cannot be meaningfully parsed.
    """
    tokens = _tokenize(nl)
    text = nl.lower().strip()
    plan = _QueryPlan()

    # 1. Detect tables
    _detect_tables(tokens, text, plan)

    # 2. Detect aggregate intent
    _detect_aggregate(tokens, text, plan)

    # 3. Detect columns
    _detect_columns(tokens, text, plan)

    # 4. Detect filters (WHERE)
    _detect_filters(tokens, text, plan)

    # 5. Detect GROUP BY
    _detect_group_by(tokens, text, plan)

    # 6. Detect ORDER BY + LIMIT
    _detect_order_and_limit(tokens, text, plan)

    # 7. Detect joins
    _detect_joins(plan)

    # 8. Assemble SQL
    return _assemble(plan)


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lower-case, strip punctuation, split into tokens."""
    cleaned = re.sub(r"[^\w\s'.]", " ", text.lower())
    return cleaned.split()


# ---------------------------------------------------------------------------
# Step 1 – Table detection
# ---------------------------------------------------------------------------

def _detect_tables(tokens: list[str], text: str, plan: _QueryPlan) -> None:
    """Identify which tables the query refers to."""
    for tok in tokens:
        resolved = resolve_table_alias(tok)
        if resolved and resolved not in plan.tables:
            plan.tables.append(resolved)

    # Also check for column aliases → infer table
    for alias, (tbl, _col) in COLUMN_ALIASES.items():
        if alias in text and tbl not in plan.tables:
            plan.tables.append(tbl)

    # If "revenue" or "sales" appear and refer to joins
    if any(w in text for w in ("revenue", "sales", "sold")):
        for t in ("orders", "products"):
            if t not in plan.tables:
                plan.tables.append(t)
    # "spend" relates to orders.total_amount (no need for products)
    if "spend" in text:
        if "orders" not in plan.tables:
            plan.tables.append("orders")
        if "customers" not in plan.tables:
            plan.tables.append("customers")

    # Default to orders if nothing detected
    if not plan.tables:
        plan.tables.append("orders")


# ---------------------------------------------------------------------------
# Step 2 – Aggregate detection
# ---------------------------------------------------------------------------

def _detect_aggregate(tokens: list[str], text: str, plan: _QueryPlan) -> None:
    """Detect aggregate function intent (COUNT, SUM, AVG …).

    Handles compound phrases like "total revenue" → SUM(total_amount) and
    guards against false positives when "total" is part of a column name.
    """

    # --- 1. Compound phrase detection (highest priority) -----------------
    _COMPOUND_AGGREGATES: list[tuple[str, str, str]] = [
        # (phrase_in_text, agg_fn, target_column)
        ("total revenue", "SUM", "total_amount"),
        ("total sales", "SUM", "total_amount"),
        ("total spend", "SUM", "total_amount"),
        ("total sold", "SUM", "total_amount"),
        ("average order amount", "AVG", "total_amount"),
        ("average amount", "AVG", "total_amount"),
        ("avg order amount", "AVG", "total_amount"),
        ("average product price", "AVG", "price"),
        ("average price", "AVG", "price"),
        ("avg price", "AVG", "price"),
    ]

    for phrase, fn, col in _COMPOUND_AGGREGATES:
        if phrase in text:
            plan.aggregate_fn = fn
            plan.aggregate_col = col
            # Ensure the table owning this column is included.
            for alias, (tbl, acol) in COLUMN_ALIASES.items():
                if acol == col:
                    if tbl not in plan.tables:
                        plan.tables.append(tbl)
                    break
            return  # compound match wins

    # --- 2. Single-keyword detection -------------------------------------
    for word, fn in _AGGREGATE_MAP.items():
        # Skip "total" if it's part of a column alias in the text
        # (e.g. "total amount" is a column, not an aggregation keyword).
        if word == "total" and "total amount" in text:
            continue

        if word in tokens or (word + " of") in text:
            plan.aggregate_fn = fn

            # COUNT always defaults to * ("count of orders" = COUNT(*))
            if fn == "COUNT":
                plan.aggregate_col = "*"
                break

            # --- try to find the target column ---------------------------
            after_agg = _text_after(text, word)

            # Check column aliases first (multi-word like "total amount")
            for alias, (tbl, col) in COLUMN_ALIASES.items():
                if alias in after_agg:
                    plan.aggregate_col = col
                    if tbl not in plan.tables:
                        plan.tables.append(tbl)
                    break

            # Single-word column
            if not plan.aggregate_col:
                for col in all_column_names():
                    if col in after_agg.split():
                        plan.aggregate_col = col
                        break

            break  # only first aggregate


def _text_after(text: str, word: str) -> str:
    """Return the portion of *text* after the first occurrence of *word*."""
    idx = text.find(word)
    if idx == -1:
        return ""
    return text[idx + len(word) :]


# ---------------------------------------------------------------------------
# Step 3 – Column detection
# ---------------------------------------------------------------------------

def _detect_columns(tokens: list[str], text: str, plan: _QueryPlan) -> None:
    """Identify requested projection columns.

    Only project specific columns when the user explicitly asks for them
    (e.g. "show customer names and emails").  Columns that only appear in
    a filter context ("products priced above 100") are NOT projected — those
    queries default to ``SELECT *``.
    """
    if plan.aggregate_fn:
        return  # aggregation handles its own projection

    # We look for explicit column-list patterns:
    # "show/list [col] and [col]", "[col] and [col] from/of …"
    # Only add to select_cols when ≥ 2 column aliases are connected by "and"
    # or commas (indicating a column-projection intent).

    # Filter keywords that disqualify a column mention from being a projection.
    _filter_context = {
        "where", "with", "above", "below", "over", "under", "priced",
        "equals", "equal", "greater", "less", "between", "before", "after",
        "named", "called", "status", "like", "gmail", "today", "yesterday",
        "pending", "shipped", "delivered",
    }

    # Gather column aliases present in text that are NOT in a filter context.
    projection_candidates: list[tuple[str, str, str]] = []  # (alias, table, col)
    for alias, (tbl, col) in COLUMN_ALIASES.items():
        if alias not in text:
            continue
        # Check if alias is near a filter keyword (within a few words).
        idx = text.find(alias)
        surrounding = text[max(0, idx - 30): idx + len(alias) + 30]
        words_around = set(surrounding.split())
        if words_around & _filter_context:
            continue
        projection_candidates.append((alias, tbl, col))

    # Only project if ≥2 candidate columns found (explicit multi-column request)
    if len(projection_candidates) >= 2:
        for _alias_str, tbl, col in projection_candidates:
            prefix = _table_prefix(tbl, plan)
            qualified = f"{prefix}.{col}" if prefix else col
            if qualified not in plan.select_cols:
                plan.select_cols.append(qualified)
            if tbl not in plan.tables:
                plan.tables.append(tbl)


# ---------------------------------------------------------------------------
# Step 4 – Filter / WHERE detection
# ---------------------------------------------------------------------------

def _detect_filters(tokens: list[str], text: str, plan: _QueryPlan) -> None:
    """Parse WHERE-clause patterns from the natural language."""

    # --- Named entity filter: "named 'X'" / "customer named X" -----------
    name_match = re.search(
        r"(?:for customer named|for customer|named|called)\s+'?([^']+?)'?\s*(?:in\b|$)",
        text,
    )
    if not name_match:
        name_match = re.search(
            r"(?:named|called|for customer|for customer named)\s+'?([A-Z][a-z]+(?: [A-Z][a-z]+)*)",
            nl_original := text,  # text is already lower
        )
    # Try with original casing preserved (we need it for names)
    if not name_match:
        name_match = re.search(
            r"(?:named|called|for customer named?)\s+'?([^']+?)'?(?:\s+in\b|\s*$)",
            text,
        )

    if name_match:
        name_val = name_match.group(1).strip().strip("'\"")
        # Title-case the name
        name_val = name_val.title()
        tbl_prefix = _table_prefix("customers", plan)
        col = f"{tbl_prefix}.name" if tbl_prefix else "name"
        plan.where_clauses.append(f"{col} = '{name_val}'")
        if "customers" not in plan.tables:
            plan.tables.append("customers")

    # --- Status filter: "status equals shipped" / "with status pending" ---
    status_match = re.search(
        r"(?:status\s+(?:equals?|is|=)\s*['\"]?(\w+)['\"]?|with\s+status\s+['\"]?(\w+)['\"]?)",
        text,
    )
    if status_match:
        val = (status_match.group(1) or status_match.group(2)).strip()
        plan.where_clauses.append(f"status = '{val}'")

    # --- Category filter: "in the X category" / "category X" -------------
    # Guard: words like "descending", "ascending" are not category names.
    _NOT_CATEGORIES = {"descending", "ascending", "desc", "asc", "each", "every"}
    cat_match = re.search(
        r"(?:in\s+(?:the\s+)?(\w[\w\s]*?)\s+category|category\s+(?:equals?|is|=)?\s*'?(\w[\w\s]*?)'?\s*(?:$|sorted|order))",
        text,
    )
    if cat_match:
        val = (cat_match.group(1) or cat_match.group(2)).strip().title()
        # Reject known non-category words (e.g. "In Descending")
        if not any(d in val.lower() for d in _NOT_CATEGORIES):
            tbl_prefix = _table_prefix("products", plan)
            col = f"{tbl_prefix}.category" if tbl_prefix else "category"
            plan.where_clauses.append(f"{col} = '{val}'")
            if "products" not in plan.tables:
                plan.tables.append("products")

    # --- Numeric comparison: "price above 100", "total amount > 50" -------
    for col_alias, (tbl, col) in COLUMN_ALIASES.items():
        for comp_word, op in _COMP_WORDS.items():
            pattern = rf"{col_alias}\s+{comp_word}\s+(\d+(?:\.\d+)?)"
            m = re.search(pattern, text)
            if m:
                val = m.group(1)
                prefix = _table_prefix(tbl, plan)
                qcol = f"{prefix}.{col}" if prefix else col
                clause = f"{qcol} {op} {val}"
                if clause not in plan.where_clauses:
                    plan.where_clauses.append(clause)
                if tbl not in plan.tables:
                    plan.tables.append(tbl)

    # Also: "priced above 100" → price > 100
    priced_match = re.search(r"priced\s+(?:above|over|greater than|more than)\s+(\d+(?:\.\d+)?)", text)
    if priced_match:
        val = priced_match.group(1)
        prefix = _table_prefix("products", plan)
        col = f"{prefix}.price" if prefix else "price"
        clause = f"{col} > {val}"
        if clause not in plan.where_clauses:
            plan.where_clauses.append(clause)
        if "products" not in plan.tables:
            plan.tables.append("products")

    priced_below = re.search(r"priced\s+(?:below|under|less than)\s+(\d+(?:\.\d+)?)", text)
    if priced_below:
        val = priced_below.group(1)
        prefix = _table_prefix("products", plan)
        col = f"{prefix}.price" if prefix else "price"
        clause = f"{col} < {val}"
        if clause not in plan.where_clauses:
            plan.where_clauses.append(clause)
        if "products" not in plan.tables:
            plan.tables.append("products")

    # Generic "total amount greater than X" when not caught by aliases
    for comp_word, op in _COMP_WORDS.items():
        m = re.search(rf"total.amount\s+{comp_word}\s+(\d+(?:\.\d+)?)", text)
        if m:
            val = m.group(1)
            clause = f"total_amount {op} {val}"
            if not any("total_amount" in c for c in plan.where_clauses):
                plan.where_clauses.append(clause)

    # --- BETWEEN filter: "quantity between 2 and 5" -----------------------
    between_match = re.search(
        r"(\w+)\s+between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)", text
    )
    if between_match:
        col_word = between_match.group(1)
        lo, hi = between_match.group(2), between_match.group(3)
        # resolve column
        real_col = _resolve_column(col_word, plan)
        if real_col:
            plan.where_clauses.append(f"{real_col} BETWEEN {lo} AND {hi}")

    # --- LIKE filter: "with gmail.com emails" -----------------------------
    like_match = re.search(r"with\s+([\w.@]+)\s+emails?", text)
    if like_match:
        pattern_val = like_match.group(1)
        prefix = _table_prefix("customers", plan)
        col = f"{prefix}.email" if prefix else "email"
        plan.where_clauses.append(f"{col} LIKE '%{pattern_val}%'")
        if "customers" not in plan.tables:
            plan.tables.append("customers")

    # --- Date filters: "in the last 30 days", "today", "yesterday" --------
    for phrase, expr in _DATE_PHRASES.items():
        if phrase in text:
            date_col = _resolve_date_column(plan)
            if "last" in phrase or "this" in phrase:
                plan.where_clauses.append(f"{date_col} >= {expr}")
            else:
                plan.where_clauses.append(f"{date_col} = {expr}")
            break  # only first date phrase

    # --- Year filter: "in 2025" -------------------------------------------
    year_match = re.search(r"\bin\s+(20\d{2})\b", text)
    if year_match:
        year = year_match.group(1)
        date_col = _resolve_date_column(plan)
        next_year = str(int(year) + 1)
        plan.where_clauses.append(f"{date_col} >= '{year}-01-01'")
        plan.where_clauses.append(f"{date_col} < '{next_year}-01-01'")


# ---------------------------------------------------------------------------
# Step 5 – GROUP BY detection
# ---------------------------------------------------------------------------

def _detect_group_by(tokens: list[str], text: str, plan: _QueryPlan) -> None:
    """Detect GROUP BY requirements."""
    # --- "top N [table] by [aggregate]" pattern ---
    # e.g. "top 5 products by total sales" → GROUP BY product name
    top_entity = re.search(r"top\s+\d+\s+(\w+)\s+by\b", text)
    if top_entity and plan.aggregate_fn:
        entity = top_entity.group(1).strip()
        resolved = resolve_table_alias(entity)
        if resolved:
            if "name" in columns_for(resolved):
                prefix = _table_prefix(resolved, plan)
                qcol = f"{prefix}.name" if prefix else "name"
                if qcol not in plan.group_by:
                    plan.group_by.append(qcol)
                if resolved not in plan.tables:
                    plan.tables.append(resolved)
                return

    # "by product category", "for each customer", "by customer", "in each category"
    by_match = re.search(r"(?:by|for each|per|in each)\s+([\w\s]+?)(?:\s+in\s+|\s+sorted|\s+order|\s+desc|\s+asc|$)", text)
    if by_match and plan.aggregate_fn:
        group_text = by_match.group(1).strip()

        # Check multi-word alias
        for alias, (tbl, col) in COLUMN_ALIASES.items():
            if alias in group_text:
                prefix = _table_prefix(tbl, plan)
                qcol = f"{prefix}.{col}" if prefix else col
                if qcol not in plan.group_by:
                    plan.group_by.append(qcol)
                if tbl not in plan.tables:
                    plan.tables.append(tbl)
                return

        # Single-word: "by customer" → customers.name
        for word in group_text.split():
            resolved = resolve_table_alias(word)
            if resolved:
                # Group by the "name" column of that table if it has one
                if "name" in columns_for(resolved):
                    prefix = _table_prefix(resolved, plan)
                    qcol = f"{prefix}.name" if prefix else "name"
                    if qcol not in plan.group_by:
                        plan.group_by.append(qcol)
                    if resolved not in plan.tables:
                        plan.tables.append(resolved)
                elif "category" in columns_for(resolved):
                    prefix = _table_prefix(resolved, plan)
                    qcol = f"{prefix}.category" if prefix else "category"
                    if qcol not in plan.group_by:
                        plan.group_by.append(qcol)
                    if resolved not in plan.tables:
                        plan.tables.append(resolved)
                return

            # Direct column?
            col_resolved = _resolve_column(word, plan)
            if col_resolved and col_resolved not in plan.group_by:
                plan.group_by.append(col_resolved)
                return


# ---------------------------------------------------------------------------
# Step 6 – ORDER BY + LIMIT
# ---------------------------------------------------------------------------

def _detect_order_and_limit(tokens: list[str], text: str, plan: _QueryPlan) -> None:
    """Parse sorting and top-N limits."""
    # "top N …"
    top_match = re.search(r"top\s+(\d+)", text)
    if top_match:
        plan.limit = int(top_match.group(1))

    # --- "top N [table] by [column]" without aggregate → ORDER BY col DESC --
    top_by_col = re.search(r"top\s+\d+\s+\w+\s+by\s+([\w\s]+?)\s*$", text)
    if top_by_col and not plan.aggregate_fn:
        col_text = top_by_col.group(1).strip()
        # Check column aliases
        for alias, (tbl, col) in COLUMN_ALIASES.items():
            if alias in col_text:
                prefix = _table_prefix(tbl, plan)
                qcol = f"{prefix}.{col}" if prefix else col
                if f"{qcol} DESC" not in plan.order_by:
                    plan.order_by.append(f"{qcol} DESC")
                break
        else:
            for word in col_text.split():
                col_resolved = _resolve_column(word, plan)
                if col_resolved:
                    if f"{col_resolved} DESC" not in plan.order_by:
                        plan.order_by.append(f"{col_resolved} DESC")
                    break

    # "most expensive" → ORDER BY price DESC LIMIT 1
    if "most expensive" in text:
        prefix = _table_prefix("products", plan)
        col = f"{prefix}.price" if prefix else "price"
        plan.order_by.append(f"{col} DESC")
        if plan.limit is None:
            plan.limit = 1

    # "sort by X desc/asc" — try with explicit direction first, then without.
    sort_match = re.search(
        r"(?:sort(?:ed)?|order(?:ed)?)\s+by\s+(.+?)\s+(desc(?:ending)?|asc(?:ending)?)\b",
        text,
    )
    if not sort_match:
        # No direction keyword — capture rest of phrase
        sort_match = re.search(
            r"(?:sort(?:ed)?|order(?:ed)?)\s+by\s+([\w\s]+?)(?:\s*$)",
            text,
        )
    if sort_match:
        sort_col_text = sort_match.group(1).strip()
        direction = "DESC" if (sort_match.lastindex and sort_match.lastindex >= 2
                                and sort_match.group(2)
                                and sort_match.group(2).startswith("desc")) else "ASC"

        # Check column aliases
        for alias, (tbl, col) in COLUMN_ALIASES.items():
            if alias in sort_col_text:
                prefix = _table_prefix(tbl, plan)
                qcol = f"{prefix}.{col}" if prefix else col
                plan.order_by.append(f"{qcol} {direction}")
                return

        # Single-word column
        for word in sort_col_text.split():
            col_resolved = _resolve_column(word, plan)
            if col_resolved:
                plan.order_by.append(f"{col_resolved} {direction}")
                return

    # "in descending order" / "in ascending order" with no explicit column
    if "descending order" in text or "in descending" in text:
        if not plan.order_by and plan.aggregate_fn:
            # Sort by the aggregate result
            plan.order_by.append("2 DESC")
        elif not plan.order_by:
            # Default sort by first reasonable column
            pass
    elif "ascending order" in text or "in ascending" in text:
        if not plan.order_by and plan.aggregate_fn:
            plan.order_by.append("2 ASC")

    # If there's a "top N" but no order_by and we have aggregation, sort by agg desc
    if plan.limit and not plan.order_by and plan.aggregate_fn:
        # Will be handled in assembly
        pass


# ---------------------------------------------------------------------------
# Step 7 – Join detection
# ---------------------------------------------------------------------------

def _detect_joins(plan: _QueryPlan) -> None:
    """Add JOIN clauses if the plan involves multiple tables."""
    if len(plan.tables) < 2:
        return

    # Use the first table as the base and join others.
    base = plan.tables[0]
    for other in plan.tables[1:]:
        jr = find_join(base, other)
        if jr:
            # Determine correct ON clause
            if jr.left_table == base:
                clause = f"JOIN {other} {_alias(other)} ON {_alias(base)}.{jr.left_col} = {_alias(other)}.{jr.right_col}"
            else:
                clause = f"JOIN {other} {_alias(other)} ON {_alias(other)}.{jr.left_col} = {_alias(base)}.{jr.right_col}"
            plan.joins.append(clause)
        else:
            # Try transitive: base→orders→other or other→orders→base
            for mid in all_table_names():
                if mid == base or mid == other:
                    continue
                jr1 = find_join(base, mid)
                jr2 = find_join(mid, other)
                if jr1 and jr2:
                    if mid not in plan.tables:
                        plan.tables.insert(1, mid)
                    # add both joins
                    if jr1.left_table == base:
                        c1 = f"JOIN {mid} {_alias(mid)} ON {_alias(base)}.{jr1.left_col} = {_alias(mid)}.{jr1.right_col}"
                    else:
                        c1 = f"JOIN {mid} {_alias(mid)} ON {_alias(mid)}.{jr1.left_col} = {_alias(base)}.{jr1.right_col}"
                    if c1 not in plan.joins:
                        plan.joins.append(c1)
                    if jr2.left_table == mid:
                        c2 = f"JOIN {other} {_alias(other)} ON {_alias(mid)}.{jr2.left_col} = {_alias(other)}.{jr2.right_col}"
                    else:
                        c2 = f"JOIN {other} {_alias(other)} ON {_alias(other)}.{jr2.left_col} = {_alias(mid)}.{jr2.right_col}"
                    if c2 not in plan.joins:
                        plan.joins.append(c2)
                    break


# ---------------------------------------------------------------------------
# Step 8 – SQL assembly
# ---------------------------------------------------------------------------

def _assemble(plan: _QueryPlan) -> str:
    """Build a SQL string from the query plan."""
    if not plan.tables:
        raise ValueError("Could not determine which table to query.")

    base = plan.tables[0]
    use_alias = len(plan.tables) > 1

    # --- SELECT clause ----------------------------------------------------
    if plan.aggregate_fn:
        agg_col = plan.aggregate_col or "*"

        # Qualify aggregate column if needed
        if agg_col != "*" and use_alias:
            agg_col = _qualify_col(agg_col, plan)

        agg_label = f"{plan.aggregate_fn.lower()}_{agg_col}".replace("*", "").replace(".", "_")
        if agg_col == "*":
            agg_label = "count"
        agg_expr = f"{plan.aggregate_fn}({agg_col}) AS {agg_label}"

        if plan.group_by:
            select_parts = plan.group_by + [agg_expr]
        else:
            select_parts = [agg_expr]
    elif plan.select_cols:
        select_parts = plan.select_cols
    else:
        if use_alias:
            # When joining, select from the primary table; for orders+customers show o.*
            select_parts = [f"{_alias(base)}.*"]
        else:
            select_parts = ["*"]

    select_clause = ", ".join(select_parts)

    # --- FROM clause ------------------------------------------------------
    if use_alias:
        from_clause = f"{base} {_alias(base)}"
    else:
        from_clause = base

    # --- JOIN clause ------------------------------------------------------
    join_clause = " ".join(plan.joins) if plan.joins else ""

    # --- WHERE clause -----------------------------------------------------
    where_clause = ""
    if plan.where_clauses:
        where_clause = "WHERE " + " AND ".join(plan.where_clauses)

    # --- GROUP BY ---------------------------------------------------------
    group_clause = ""
    if plan.group_by:
        group_clause = "GROUP BY " + ", ".join(plan.group_by)

    # --- ORDER BY ---------------------------------------------------------
    order_clause = ""
    if plan.order_by:
        order_clause = "ORDER BY " + ", ".join(plan.order_by)
    elif plan.aggregate_fn and plan.group_by and plan.limit:
        # Implicit sort by aggregate desc for top-N aggregations
        agg_col = plan.aggregate_col or "*"
        if agg_col != "*" and use_alias:
            agg_col = _qualify_col(agg_col, plan)
        agg_label = f"{plan.aggregate_fn.lower()}_{agg_col}".replace("*", "").replace(".", "_")
        if agg_col == "*":
            agg_label = "count"
        order_clause = f"ORDER BY {agg_label} DESC"

    # --- LIMIT ------------------------------------------------------------
    limit_clause = f"LIMIT {plan.limit}" if plan.limit else ""

    # --- Combine ----------------------------------------------------------
    parts = [
        f"SELECT {select_clause}",
        f"FROM {from_clause}",
    ]
    if join_clause:
        parts.append(join_clause)
    if where_clause:
        parts.append(where_clause)
    if group_clause:
        parts.append(group_clause)
    if order_clause:
        parts.append(order_clause)
    if limit_clause:
        parts.append(limit_clause)

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _alias(table: str) -> str:
    """Return a short alias for a table name (first letter)."""
    return table[0]

def _table_prefix(table: str, plan: _QueryPlan) -> str:
    """Return the alias to prefix columns with, or '' if only one table."""
    if len(plan.tables) > 1:
        return _alias(table)
    return ""


def _resolve_column(word: str, plan: _QueryPlan) -> str | None:
    """Try to resolve a single word to a qualified column reference."""
    word = word.lower().strip()

    # Check aliases
    if word in COLUMN_ALIASES:
        tbl, col = COLUMN_ALIASES[word]
        prefix = _table_prefix(tbl, plan)
        return f"{prefix}.{col}" if prefix else col

    # Check all columns across tables in the plan
    for t in plan.tables:
        if word in columns_for(t):
            prefix = _table_prefix(t, plan)
            return f"{prefix}.{word}" if prefix else word

    return None


def _qualify_col(col: str, plan: _QueryPlan) -> str:
    """Add a table alias prefix to a bare column if needed."""
    if "." in col:
        return col
    for t in plan.tables:
        if col in columns_for(t):
            return f"{_alias(t)}.{col}"
    return col


def _resolve_date_column(plan: _QueryPlan) -> str:
    """Return the best created_at column reference for date filters."""
    # Prefer orders.created_at, fall back to customers.created_at
    for t in plan.tables:
        if "created_at" in columns_for(t):
            prefix = _table_prefix(t, plan)
            return f"{prefix}.created_at" if prefix else "created_at"
    return "created_at"
