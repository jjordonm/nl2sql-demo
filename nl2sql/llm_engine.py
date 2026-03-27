"""
llm_engine.py - LLM-powered Natural Language to SQL translator.

Uses the OpenAI Chat Completions API (compatible with OpenAI, Azure OpenAI,
and any OpenAI-compatible endpoint) to translate natural-language questions
into SQL.

Configuration (via environment variables or .env file)
------------------------------------------------------
OPENAI_API_KEY      - Required. Your OpenAI (or Azure) API key.
OPENAI_MODEL        - Optional. Model name (default: "gpt-4o-mini").
OPENAI_BASE_URL     - Optional. Custom base URL for Azure OpenAI or
                      compatible providers.

The schema definition is injected into the system prompt so the LLM knows
which tables/columns are available.
"""

from __future__ import annotations

import os
import re

from openai import OpenAI

from nl2sql.schema import TABLES, JOIN_RELATIONS, KEY_TABLES, schema_for_llm

# ---------------------------------------------------------------------------
# System prompt (built at import time from the schema CSV)
# ---------------------------------------------------------------------------

_SCHEMA_TEXT = schema_for_llm()

_SYSTEM_PROMPT = f"""\
You are a SQL query generator for a SQLite database that mirrors a Snowflake
analytics schema.  The database is: DEMO_ANALYTICS.DEMO_PUBLISHED

Schema (table_name(column_name data_type, ...)):

{_SCHEMA_TEXT}

Key business tables (most commonly queried):
- AIML_OPEN_PURCHASE_ORDERS: Open purchase orders with vendor, plant, material, quantity, value and delivery dates.
- CORE_PLANT: Plant master data with location info (city, region, country).
- EDW_INVENTORY_SEGMENTATION_SNAPSHOT: Inventory snapshots including on-hand, excess, demand, lifecycle, segmentation.
- EDW_MATL_LOC_DEMAND_INFO: Material demand information by plant.

Rules:
- Output ONLY a single valid SQLite SELECT statement.  No explanation, no markdown fences, no comments.
- Use SQLite date functions (e.g. date('now'), date('now', '-30 days')) for date-relative queries.
- Use single quotes for string literals.
- For "today" use date('now').
- When joining tables, use short aliases (e.g. po for AIML_OPEN_PURCHASE_ORDERS, p for CORE_PLANT).
- When asked for "top N" use ORDER BY ... DESC LIMIT N.
- For text search use LIKE with % wildcards.
- Only produce SELECT queries.
- If the question cannot be answered from the schema, respond with: SELECT 'Query not supported' AS error
- Column and table names are UPPER CASE.
- Monetary values in USD use OPEN_VALUE_IN_USD, STANDARD_PRICE_USD, and similar _USD columns.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def translate_llm(nl: str) -> str:
    """Translate a natural-language question into SQL using an LLM.

    Parameters
    ----------
    nl : str
        The user's natural language input.

    Returns
    -------
    str
        A SQL SELECT string.

    Raises
    ------
    ValueError
        If the API key is not configured.
    RuntimeError
        If the LLM call fails.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to your .env file or "
            "set it as an environment variable."
        )

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL")  # None → default OpenAI endpoint

    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": nl},
            ],
            temperature=0.0,
            max_tokens=512,
        )
    except Exception as exc:
        raise RuntimeError(f"LLM API call failed: {exc}") from exc

    raw = response.choices[0].message.content or ""
    sql = _clean_sql(raw)

    if not sql:
        raise RuntimeError("LLM returned an empty response.")

    return sql


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_sql(raw: str) -> str:
    """Strip markdown fences, comments, and trailing semicolons from LLM output."""
    text = raw.strip()

    # Remove markdown code fences (```sql ... ``` or ``` ... ```)
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    # Remove trailing semicolons
    text = text.strip().rstrip(";").strip()

    return text


def is_llm_available() -> bool:
    """Return True if the LLM engine is configured (API key is set)."""
    return bool(os.getenv("OPENAI_API_KEY"))
