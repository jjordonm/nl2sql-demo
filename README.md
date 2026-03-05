# NL2SQL Demo

A self-contained demo that translates **natural language** into **SQL queries**
using a rule-based engine, with a Streamlit UI and optional golden-SQL
evaluation.

> **Status:** Demo / educational project – not for production use.  
> All data is synthetic.  Translations may be incomplete or inaccurate.

---

## Architecture

```
 ┌────────────────────────────────────────────────────┐
 │                  Streamlit UI  (app.py)            │
 │  ┌──────────┐  ┌───────────┐  ┌────────────────┐  │
 │  │ NL Input │→ │ engine.py │→ │ Generated SQL  │  │
 │  └──────────┘  └───────────┘  └───────┬────────┘  │
 │                                       │ (optional) │
 │                                       ▼            │
 │                               ┌──────────────┐    │
 │                               │  SQLite DB   │    │
 │                               │ (db.py)      │    │
 │                               └──────────────┘    │
 │                                                    │
 │  Sidebar: [Init DB] [Run Eval] [Toggle Execute]   │
 └────────────────────────────────────────────────────┘

 nl2sql/
   schema.py   – Table/column definitions & helpers
   db.py       – SQLite bootstrap & seed-data loader
   engine.py   – Rule-based NL → SQL translator
   eval.py     – Golden-SQL comparison & reporting

 data/
   seed/       – CSV files loaded into SQLite
   golden/     – JSONL file with NL→SQL reference pairs
```

### Component summary

| Module | Purpose |
|--------|---------|
| `nl2sql/schema.py` | Defines tables, columns, aliases, and join relationships. Acts as the single source of truth the engine validates against. |
| `nl2sql/db.py` | Creates the SQLite database, runs DDL, and loads seed CSVs. Provides `execute_sql()` for safe read-only queries. |
| `nl2sql/engine.py` | Tokenises the NL input, detects tables/columns/filters/aggregations/sorting, builds a query plan, and assembles safe SQL. |
| `nl2sql/eval.py` | Loads golden examples, runs the engine, and compares results (string or result-set mode). Produces an accuracy report. |
| `app.py` | Streamlit single-page app tying everything together. |

---

## Quick start

```bash
# 1. Clone and enter the repo
cd nl2sql-demo

# 2. Create a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch the app
streamlit run app.py
```

The database is auto-created on first run. Click **Initialize DB** in the
sidebar to reset it at any time.

---

## Running tests

```bash
pytest -v
```

Tests use a temporary SQLite database so they don't interfere with your main
`data/demo.sqlite`.

---

## Example queries to try

| # | Natural language input |
|---|------------------------|
| 1 | List all customers |
| 2 | Show orders placed in the last 30 days |
| 3 | Find the top 5 products by total sales |
| 4 | Count of orders where status equals shipped |
| 5 | Average order amount for each customer |
| 6 | Orders for customer named Alice Johnson in 2025 |
| 7 | Total revenue by product category in descending order |
| 8 | List products priced above 100 sorted by price desc |
| 9 | Top 3 customers by total spend |
| 10 | Orders with quantity between 2 and 5 |
| 11 | Show orders created today |
| 12 | Find customers with gmail.com emails |
| 13 | Average product price |
| 14 | Show the most expensive product |
| 15 | Count of products in each category |

---

## Schema

```
customers(id, name, email, created_at)
products(id, name, category, price)
orders(id, customer_id, product_id, quantity, total_amount, status, created_at)
```

Seed data: 20 customers, 20 products, 45 orders — all synthetic.

---

## Extensibility

### Adding new rules to the engine

1. Open `nl2sql/engine.py`.
2. Pattern matching happens in dedicated `_detect_*` functions (tables,
   aggregates, columns, filters, group-by, ordering).
3. To handle a new phrase, add a regex or keyword check in the appropriate
   function and update the `_QueryPlan`.
4. Add corresponding golden examples in `data/golden/golden.sql.jsonl` and
   run `pytest` to verify.

### Swapping in an LLM

Replace the body of `translate()` in `engine.py` with a call to your LLM
(e.g. Azure OpenAI, local Ollama). Keep the same function signature
`translate(nl: str) -> str` so the rest of the stack is unchanged.

```python
# Example LLM hook (off by default)
def translate(nl: str) -> str:
    if os.getenv("USE_LLM"):
        return _call_llm(nl)
    return _rule_based_translate(nl)
```

### Extending the schema

1. Add a `TableDef` to `TABLES` in `nl2sql/schema.py`.
2. Add join relationships in `JOIN_RELATIONS` if applicable.
3. Create a seed CSV in `data/seed/`.
4. Add DDL in `nl2sql/db.py._DDL`.
5. Re-initialise: click **Initialize DB** or call `init_db(force=True)`.

---

## Limitations & Responsible AI

- **Demo only** – This is an educational prototype, not production software.
- **Rule-based** – The engine handles common patterns but will fail on
  complex or ambiguous queries. It does *not* understand free-form English.
- **Synthetic data** – All names, emails, and transactions are fake. No
  personally identifiable information (PII) is used.
- **No authentication / authorisation** – The app exposes a raw SQL
  execution path (read-only). Do not deploy on an untrusted network without
  additional safeguards.
- **SQL injection mitigation** – Table and column names are strictly
  white-listed from the schema. User-supplied *values* in filters are
  embedded as literals (not parameterised) for simplicity; a production
  system should use parameterised queries throughout.
- **Accuracy** – Translations are best-effort. Always review generated SQL
  before using results for any decision-making.

---

## License

This project is provided as-is for demonstration purposes.
