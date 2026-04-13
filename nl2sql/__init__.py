"""
nl2sql - Natural Language to SQL translator.

This package provides:
- schema: Schema definitions and introspection helpers
- db: SQLite database setup and seed-data loader
- engine: Rule-based NL to SQL translation engine
- llm_engine: LLM-powered NL to SQL translation engine (default)
- eval: Golden-SQL evaluation and comparison utilities
- visualize: Auto-visualization suggestions for query results
"""

from nl2sql.engine import translate  # noqa: F401
from nl2sql.llm_engine import translate_llm, is_llm_available  # noqa: F401
from nl2sql.visualize import suggest_chart  # noqa: F401
