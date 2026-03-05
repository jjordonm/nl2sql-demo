"""
schema.py – Fake schema definition and introspection helpers.

This module describes the demo database schema (customers, products, orders)
and exposes helper functions for looking up valid table names, column names,
and join relationships.  The engine uses these to whitelist identifiers and
avoid SQL injection.

To extend the schema
---------------------
1. Add a new ``TableDef`` entry to ``TABLES``.
2. If the new table can be joined to existing tables, add entries in
   ``JOIN_RELATIONS``.
3. Re-seed the database (``nl2sql.db.init_db(force=True)``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Table / column definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TableDef:
    """Immutable description of a single database table."""

    name: str
    columns: tuple[str, ...]
    # Aliases a user might say that should resolve to this table.
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Master list of tables in the demo schema.
TABLES: dict[str, TableDef] = {
    "customers": TableDef(
        name="customers",
        columns=("id", "name", "email", "created_at"),
        aliases=("customer",),
    ),
    "products": TableDef(
        name="products",
        columns=("id", "name", "category", "price"),
        aliases=("product",),
    ),
    "orders": TableDef(
        name="orders",
        columns=(
            "id",
            "customer_id",
            "product_id",
            "quantity",
            "total_amount",
            "status",
            "created_at",
        ),
        aliases=("order",),
    ),
}

# ---------------------------------------------------------------------------
# Join relationships  (table_a, table_b) → (a_col, b_col)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JoinRelation:
    """Describes how two tables can be joined."""

    left_table: str
    right_table: str
    left_col: str
    right_col: str


JOIN_RELATIONS: list[JoinRelation] = [
    JoinRelation("orders", "customers", "customer_id", "id"),
    JoinRelation("orders", "products", "product_id", "id"),
]


# ---------------------------------------------------------------------------
# Convenience helpers (used by engine.py)
# ---------------------------------------------------------------------------

# Column aliases: what the user might say → (table, real_column)
# Extend this mapping when you add new user-facing names.
COLUMN_ALIASES: dict[str, tuple[str, str]] = {
    "customer name": ("customers", "name"),
    "customer email": ("customers", "email"),
    "product name": ("products", "name"),
    "product price": ("products", "price"),
    "product category": ("products", "category"),
    "category": ("products", "category"),
    "price": ("products", "price"),
    "total amount": ("orders", "total_amount"),
    "total_amount": ("orders", "total_amount"),
    "order status": ("orders", "status"),
    "status": ("orders", "status"),
    "quantity": ("orders", "quantity"),
    "email": ("customers", "email"),
}


def all_table_names() -> set[str]:
    """Return the set of valid table names."""
    return set(TABLES.keys())


def all_column_names() -> set[str]:
    """Return every column across all tables."""
    cols: set[str] = set()
    for tbl in TABLES.values():
        cols.update(tbl.columns)
    return cols


def columns_for(table: str) -> tuple[str, ...]:
    """Return columns belonging to *table*, or empty tuple if unknown."""
    tdef = TABLES.get(table)
    return tdef.columns if tdef else ()


def resolve_table_alias(token: str) -> str | None:
    """Map a token to a canonical table name, or ``None`` if unrecognised."""
    token_lower = token.lower()
    if token_lower in TABLES:
        return token_lower
    for tname, tdef in TABLES.items():
        if token_lower in tdef.aliases:
            return tname
    return None


def find_join(left: str, right: str) -> JoinRelation | None:
    """Return the join relation between two tables, or ``None``."""
    for jr in JOIN_RELATIONS:
        if (jr.left_table == left and jr.right_table == right) or (
            jr.left_table == right and jr.right_table == left
        ):
            return jr
    return None
