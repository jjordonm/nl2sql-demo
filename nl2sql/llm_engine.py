"""
llm_engine.py - LLM-powered Natural Language to SQL translator.

Uses the Azure OpenAI Chat Completions API to translate natural-language
questions into SQL.

Configuration (via environment variables or .env file)
------------------------------------------------------
AZURE_OPENAI_ENDPOINT      - Required. Endpoint URL, e.g.
                             https://<resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT    - Required. Azure OpenAI deployment name.
AZURE_OPENAI_API_VERSION   - Optional. API version
                             (default: "2024-02-01").

Authentication uses Microsoft Entra ID (AAD) via DefaultAzureCredential.
For local development, run: az login

The schema definition is injected into the system prompt so the LLM knows
which tables/columns are available.
"""

from __future__ import annotations

import os
import re

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

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
# Cached client (created once per process)
# ---------------------------------------------------------------------------

_client: AzureOpenAI | None = None
_client_endpoint: str | None = None

_MAX_INPUT_LENGTH = 1000


def _get_client() -> AzureOpenAI:
    """Return a cached AzureOpenAI client, creating one if needed."""
    global _client, _client_endpoint

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "")

    # Recreate if endpoint changed (e.g. env var updated)
    if _client and _client_endpoint == endpoint:
        return _client

    if api_key:
        _client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            api_key=api_key,
        )
    else:
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        _client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
        )

    _client_endpoint = endpoint
    return _client


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
        If required Azure OpenAI settings are missing or input is invalid.
    RuntimeError
        If the LLM call fails.
    """
    if not nl or not isinstance(nl, str):
        raise ValueError("Query must be a non-empty string.")

    nl = nl.strip()
    if len(nl) > _MAX_INPUT_LENGTH:
        raise ValueError(
            f"Query is too long ({len(nl)} chars). "
            f"Maximum is {_MAX_INPUT_LENGTH} characters."
        )

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    if not endpoint:
        raise ValueError(
            "AZURE_OPENAI_ENDPOINT is not set. Add it to your .env file or "
            "set it as an environment variable."
        )
    if not deployment:
        raise ValueError(
            "AZURE_OPENAI_DEPLOYMENT is not set. Add it to your .env file or "
            "set it as an environment variable."
        )

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": nl},
            ],
            temperature=0.0,
            max_completion_tokens=512,
        )
    except Exception as exc:
        raise RuntimeError(
            "LLM API call failed. Ensure your Azure identity can access the "
            "Azure OpenAI resource (for local dev, run 'az login'). "
            f"Details: {exc}"
        ) from exc

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
    """Return True if required Azure OpenAI settings are configured."""
    return bool(
        os.getenv("AZURE_OPENAI_ENDPOINT")
        and os.getenv("AZURE_OPENAI_DEPLOYMENT")
    )
