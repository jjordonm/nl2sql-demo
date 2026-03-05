"""
nl2sql – A rule-based Natural Language to SQL translator.

This package provides:
- schema: Schema definitions and introspection helpers
- db: SQLite database setup and seed-data loader
- engine: Rule-based NL→SQL translation engine
- eval: Golden-SQL evaluation and comparison utilities
"""

from nl2sql.engine import translate  # noqa: F401 – public API shortcut
