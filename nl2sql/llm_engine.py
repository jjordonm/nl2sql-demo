"""
llm_engine.py – LLM-powered Natural Language → SQL translator.

Uses the OpenAI Chat Completions API (compatible with OpenAI, Azure OpenAI,
and any OpenAI-compatible endpoint) to translate natural-language questions
into SQL.

Configuration (via environment variables or .env file)
------------------------------------------------------
OPENAI_API_KEY      – Required. Your OpenAI (or Azure) API key.
OPENAI_MODEL        – Optional. Model name (default: "gpt-4o-mini").
OPENAI_BASE_URL     – Optional. Custom base URL for Azure OpenAI or
                      compatible providers.

The schema definition is injected into the system prompt so the LLM knows
which tables/columns are available.
"""

from __future__ import annotations

import os
import re

from openai import OpenAI

from nl2sql.schema import TABLES, JOIN_RELATIONS, all_table_names, all_column_names

# ---------------------------------------------------------------------------
# Schema prompt builder
# ---------------------------------------------------------------------------

def _build_schema_description() -> str:
    """Build a human-readable schema description for the system prompt."""
    lines: list[str] = []
    for tname, tdef in TABLES.items():
        cols = ", ".join(tdef.columns)
        lines.append(f"  {tname}({cols})")

    lines.append("")
    lines.append("  Relationships:")
    for jr in JOIN_RELATIONS:
        lines.append(
            f"    {jr.left_table}.{jr.left_col} → {jr.right_table}.{jr.right_col}"
        )

    return "\n".join(lines)


_SYSTEM_PROMPT = f"""\
You are a SQL query generator for a SQLite database with the following schema:

{_build_schema_description()}

Rules:
- Output ONLY a single valid SQLite SELECT statement. No explanation, no markdown fences, no comments.
- Use SQLite date functions (e.g. date('now'), date('now', '-30 days')) for date-relative queries.
- Use single quotes for string literals.
- For "today" use date('now'). Current date context is provided by the user implicitly.
- When joining tables, use short aliases (e.g. o for orders, c for customers, p for products).
- When asked for "top N" use ORDER BY ... DESC LIMIT N.
- For text search use LIKE with % wildcards.
- Only produce SELECT queries — never INSERT, UPDATE, DELETE, DROP, etc.
- If the question cannot be answered from the schema, respond with: SELECT 'Query not supported' AS error
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
