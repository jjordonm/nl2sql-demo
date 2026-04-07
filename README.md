# NL2SQL Demo

A self-contained demo that translates **natural language** into **SQL queries**
using an **LLM** (Azure OpenAI) by default, with a **rule-based fallback** engine,
a Streamlit UI, and optional golden-SQL evaluation.

> **Status:** Demo / educational project – not for production use.  
> All data is synthetic.  Translations may be incomplete or inaccurate.

---

## Architecture

```
 ┌────────────────────────────────────────────────────┐
 │                  Streamlit UI  (app.py)            │
 │                                                    │
 │  ┌──────────┐  ┌───────────────┐  ┌────────────────┐  │
 │  │ NL Input │→ │  LLM engine  │→ │ Generated SQL  │  │
 │  └──────────┘  │  (default)   │  └───────┬────────┘  │
 │               │───────────────│        │ (optional) │
 │               │ Rule-based   │        ▼            │
 │               │  (fallback)  │  ┌──────────────┐    │
 │               └───────────────┘  │   SQLite DB  │    │
 │                               │   (db.py)    │    │
 │                               └──────────────┘    │
 │                                                    │
 │  Sidebar: [Engine Toggle] [Init DB] [Run Eval]     │
 └────────────────────────────────────────────────────┘

 nl2sql/
   schema.py      – Table/column definitions & helpers
   db.py          – SQLite bootstrap & seed-data loader
   llm_engine.py  – LLM-powered NL → SQL translator (default)
   engine.py      – Rule-based NL → SQL translator (fallback)
   eval.py        – Golden-SQL comparison & reporting

 data/
   seed/          – CSV files loaded into SQLite
   golden/        – JSONL file with NL→SQL reference pairs
```

### Component summary

| Module | Purpose |
|--------|---------|
| `nl2sql/schema.py` | Defines tables, columns, aliases, and join relationships. Acts as the single source of truth the engine validates against. |
| `nl2sql/db.py` | Creates the SQLite database, runs DDL, and loads seed CSVs. Provides `execute_sql()` for safe read-only queries. |
| `nl2sql/llm_engine.py` | Sends NL + schema to Azure OpenAI Chat Completions API (AAD auth). Default engine. |
| `nl2sql/engine.py` | Tokenises the NL input, detects tables/columns/filters/aggregations/sorting, builds a query plan, and assembles safe SQL. Fallback engine. |
| `nl2sql/eval.py` | Loads golden examples, runs the engine, and compares results (string or result-set mode). Produces an accuracy report. |
| `nl2sql/visualize.py` | Analyzes query results and suggests the best chart type (bar, line, pie, scatter, area) based on data shape and query intent. |
| `app.py` | Streamlit chat-style app with history, auto-visualization, and evaluation. |
| `function_app/` | Azure Functions Bot Framework endpoint for Microsoft Teams integration. |

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

# 4. Configure the LLM (default engine)
cp .env.example .env
# Edit .env and add your Azure OpenAI settings

# 5. Launch the app
streamlit run app.py
```

The database is auto-created on first run. Click **Initialize DB** in the
sidebar to reset it at any time.

### Engine modes

| Mode | How it works | Requires |
|------|-------------|----------|
| **LLM (default)** | Sends the NL question + schema to Azure OpenAI Chat Completions API using Entra ID (AAD) | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` in `.env` + Azure login |
| **Rule-based** | Local pattern-matching, no network calls | Nothing — works offline |

The sidebar has a radio toggle to switch between engines. If Azure OpenAI
configuration is missing, the app automatically falls back to rule-based mode.

For local development, authenticate first:

```bash
az login
```

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes (LLM mode) | — | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Yes (LLM mode) | — | Azure OpenAI deployment name |
| `AZURE_OPENAI_API_VERSION` | No | `2024-02-01` | Azure OpenAI API version |
| `MICROSOFT_APP_ID` | Yes (Teams bot) | — | Bot registration App ID |
| `MICROSOFT_APP_PASSWORD` | Yes (Teams bot) | — | Bot registration client secret |

---

## Features

### Chat history

The Streamlit UI uses a conversational chat interface (`st.chat_input` + `st.chat_message`). All questions and responses are stored in `st.session_state` and persist across reruns within the same browser session. Use the **Clear history** button in the sidebar to reset.

### Auto-visualization

When **Auto-visualize results** is enabled (default), the app analyzes each query result and automatically renders the most appropriate chart:

| Chart type | When it's used |
|-----------|----------------|
| **Bar** | Categorical grouping with numeric values (e.g. "total value by plant") |
| **Pie** | Small number of categories with distribution keywords (e.g. "breakdown by vendor") |
| **Line** | Time-series data with trend keywords (e.g. "orders over time") |
| **Scatter** | Two numeric columns with many rows |
| **Area** | Time-series with area-style keywords |

The logic lives in `nl2sql/visualize.py` and uses heuristics based on column types, row count, and NL query keywords.

### Microsoft Teams bot

The `function_app/` directory contains a Bot Framework bot deployed as an Azure Function. Users can chat with the NL2SQL agent directly in Microsoft Teams.

#### Teams deployment

1. **Register a bot** in the [Azure Portal](https://portal.azure.com) → Bot Services → Create Azure Bot.
2. Note the **App ID** and create a **client secret**. Add both to your `.env`:

   ```bash
   MICROSOFT_APP_ID=your-app-id
   MICROSOFT_APP_PASSWORD=your-client-secret
   ```

3. **Deploy the Azure Function:**

   ```bash
   cd function_app
   func azure functionapp publish <your-function-app-name>
   ```

4. **Set the messaging endpoint** in the Azure Bot registration to:

   ```
   https://<your-function-app-name>.azurewebsites.net/api/messages
   ```

5. **Install in Teams:**
   - Edit `function_app/teams-manifest/manifest.json` and replace `{{MICROSOFT_APP_ID}}` with your actual App ID.
   - Add 192×192 `color.png` and 32×32 `outline.png` icons to the `teams-manifest/` folder.
   - Zip the manifest folder contents and upload to Teams Admin Center or sideload in Teams.

#### Bot commands

| Command | Description |
|---------|-------------|
| *(any question)* | Translates to SQL, executes, and returns results as an Adaptive Card |
| `help` | Shows available commands and example queries |
| `history` | Shows recent queries for the conversation |
| `clear history` | Clears conversation history |

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
| 1 | List all open purchase orders |
| 2 | Show all plants |
| 3 | Top 5 purchase orders by open value in USD |
| 4 | Count of purchase orders by vendor |
| 5 | Total open value by plant |
| 6 | Show purchase orders for vendor Honeywell Aerospace |
| 7 | Show plants in the US |
| 8 | Count of materials by segment |
| 9 | Show purchase orders with open quantity greater than 100 |
| 10 | Total open value by material group |
| 11 | Average lead time by plant |
| 12 | Top 3 plants by total open purchase order value |
| 13 | Show materials with lifecycle Active |
| 14 | Show purchase orders with exception message Expedite |

---

## Schema

The schema is auto-loaded from `data/snowflake_table_columns.csv` (28 tables
from DEMO_ANALYTICS.DEMO_PUBLISHED). Key business tables:

```
AIML_OPEN_PURCHASE_ORDERS  (47 columns) - Open PO lines with vendor, plant, material, qty, value
CORE_PLANT                 (23 columns) - Plant master data with location info
EDW_INVENTORY_SEGMENTATION_SNAPSHOT (113 columns) - Inventory snapshots
EDW_MATL_LOC_DEMAND_INFO   (24 columns) - Material demand information
```

Plus 24 SAP raw tables (EKKO, EKPO, MARA, MARC, LFA1, etc.).

Seed data: 10 plants, 30 POs, 40 inventory snapshots, 25 demand records - all synthetic dummy values.

---

## Extensibility

### Configuring the LLM engine

The LLM engine uses the `openai` Python package with the AzureOpenAI client.
Set these variables:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- Optional: `AZURE_OPENAI_API_VERSION`

Authentication is via Microsoft Entra ID (AAD) using `DefaultAzureCredential`
from `azure-identity`.

### Customising the LLM prompt

Edit the `_SYSTEM_PROMPT` in `nl2sql/llm_engine.py` to adjust the
instructions, add few-shot examples, or change the output format.

### Updating the schema

1. Replace `data/snowflake_table_columns.csv` with an updated export.
2. The schema is parsed automatically at import time - no code changes needed.
3. Add join relationships in `nl2sql/schema.py` if applicable.
4. Regenerate seed data: `python generate_seed_data.py`
5. Re-initialise: click **Initialize DB** or call `init_db(force=True)`.

### Adding new rules to the rule-based engine

1. Open `nl2sql/engine.py`.
2. Pattern matching happens in dedicated `_detect_*` functions (tables,
   aggregates, columns, filters, group-by, ordering).
3. To handle a new phrase, add a regex or keyword check in the appropriate
   function and update the `_QueryPlan`.
4. Add corresponding golden examples in `data/golden/golden.sql.jsonl` and
   run `pytest` to verify.

### Extending the schema

1. Update `data/snowflake_table_columns.csv` with the new table/column metadata.
2. Add join relationships in `JOIN_RELATIONS` in `nl2sql/schema.py` if applicable.
3. Add seed data generation logic in `generate_seed_data.py`.
4. Run `python generate_seed_data.py` to create CSVs.
5. Re-initialise: click **Initialize DB** or call `init_db(force=True)`.

---

## Limitations & Responsible AI

- **Demo only** – This is an educational prototype, not production software.
- **LLM accuracy** – The LLM engine generally produces better SQL than the
  rule-based engine, but may still hallucinate columns or misinterpret
  ambiguous queries. Always review generated SQL.
- **Rule-based** – The rule-based engine handles common patterns but will
  fail on complex or ambiguous queries.
- **API costs** – LLM mode makes API calls to Azure OpenAI. Each query costs
  a small amount of tokens.
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
