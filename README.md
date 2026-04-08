# NL2SQL Demo

A self-contained demo that translates **natural language** into **SQL queries**
using an **LLM** (Azure OpenAI) by default, with a **rule-based fallback** engine,
a Streamlit UI with chat history and auto-visualization, a Microsoft Teams bot,
and optional golden-SQL evaluation.

> **Status:** Demo / educational project – not for production use.
> All data is synthetic.  Translations may be incomplete or inaccurate.

---

## Architecture

```
                         ┌─────────────────────────┐
                         │     Microsoft Teams      │
                         │      (Bot Framework)     │
                         └────────────┬────────────┘
                                      │ HTTPS
                         ┌────────────▼────────────┐
                         │   Azure App Service      │
                         │   (webapp.py + bot.py)   │
                         │   Managed Identity auth  │
                         └────────────┬────────────┘
                                      │
 ┌────────────────────────────────────┐│┌──────────────────────────┐
 │       Streamlit UI  (app.py)      │││   Azure OpenAI Service   │
 │                                   ││└──────────────────────────┘
 │  Chat history + Auto-viz + Eval   │├──────────┐
 │  az login (local dev auth)        ││          │
 └────────────────┬──────────────────┘│          │
                  │                   │          │
         ┌────────▼────────┐  ┌───────▼──────┐  │
         │  LLM Engine     │  │ Rule-based   │  │
         │  (llm_engine.py)│  │ (engine.py)  │  │
         └────────┬────────┘  └──────┬───────┘  │
                  └──────────┬───────┘          │
                       ┌─────▼─────┐            │
                       │  SQLite   │            │
                       │ (db.py)   │            │
                       └─────┬─────┘            │
                       ┌─────▼─────┐            │
                       │ visualize │            │
                       │   .py     │            │
                       └───────────┘            │
```

### Component summary

| Module | Purpose |
|--------|---------|
| `nl2sql/schema.py` | Defines tables, columns, aliases, and join relationships from the schema CSV. |
| `nl2sql/db.py` | Creates the SQLite database, runs DDL, and loads seed CSVs. Provides `execute_sql()` for safe read-only queries. |
| `nl2sql/llm_engine.py` | Sends NL + schema to Azure OpenAI Chat Completions API. Supports both Entra ID (managed identity / `az login`) and API key auth. |
| `nl2sql/engine.py` | Rule-based NL to SQL translator using regex pattern matching. Fallback engine. |
| `nl2sql/eval.py` | Golden-SQL evaluation: loads reference pairs, runs the engine, compares results. |
| `nl2sql/visualize.py` | Suggests the best chart type (bar, line, pie, scatter, area) based on data shape and query intent. |
| `app.py` | Streamlit chat-style app with conversation history, auto-visualization, and evaluation sidebar. |
| `webapp.py` | aiohttp web server entry-point for the Teams bot (deployed to Azure App Service). |
| `bot.py` | Bot Framework `ActivityHandler` that processes Teams messages, translates to SQL, returns Adaptive Cards. |
| `function_app/teams-manifest/` | Teams app manifest template. Replace `{{MICROSOFT_APP_ID}}` with your App ID before packaging. |

---

## Azure resources required

| Resource | Purpose | SKU / Tier |
|----------|---------|------------|
| **Azure OpenAI Service** or **Azure AI Foundry** | LLM for NL-to-SQL translation | Any tier with a chat deployment (e.g. GPT-4o-mini). Models can be provisioned through Azure OpenAI directly or via an Azure AI Foundry project. |
| **App Registration** (Entra ID) | Bot identity for Bot Framework auth | Single-tenant or multi-tenant |
| **Azure Bot** | Routes messages between Teams and the App Service | Free (F0) or Standard (S1) |
| **Azure App Service** (Linux) | Hosts the bot web server (`webapp.py`) | B1 or higher (Python 3.11, Linux) |
| **App Service Plan** | Compute plan for the App Service | Basic B1 (Linux) |

### Required role assignments

| Principal | Role | Scope | When |
|-----------|------|-------|------|
| App Service managed identity | **Cognitive Services OpenAI User** | Azure OpenAI resource | Using Azure OpenAI directly |
| App Service managed identity | **Azure AI Developer** | Azure AI Foundry project | Using a model deployed via AI Foundry |
| Your user account (local dev) | **Cognitive Services OpenAI User** | Azure OpenAI resource | Using Azure OpenAI directly |
| Your user account (local dev) | **Azure AI Developer** | Azure AI Foundry project | Using a model deployed via AI Foundry |

---

## Quick start (Streamlit UI)

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

# 4. Configure the LLM
cp .env.example .env
# Edit .env and set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT

# 5. Authenticate to Azure (for Entra ID auth)
az login

# 6. Launch the app
streamlit run app.py
```

The database is auto-created on first run. Click **Initialize DB** in the
sidebar to reset it at any time.

### Engine modes

| Mode | How it works | Requires |
|------|-------------|----------|
| **LLM (default)** | Sends the NL question + schema to Azure OpenAI Chat Completions API | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` in `.env` + `az login` |
| **Rule-based** | Local pattern-matching, no network calls | Nothing — works offline |

The sidebar has a radio toggle to switch between engines. If Azure OpenAI
configuration is missing, the app automatically falls back to rule-based mode.

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Yes (LLM mode) | — | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Yes (LLM mode) | — | Azure OpenAI deployment name |
| `AZURE_OPENAI_API_VERSION` | No | `2024-02-01` | Azure OpenAI API version |
| `AZURE_OPENAI_API_KEY` | No | — | API key (fallback if Entra ID is unavailable) |
| `MICROSOFT_APP_ID` | Yes (Teams bot) | — | Bot App Registration client ID |
| `MICROSOFT_APP_PASSWORD` | Yes (Teams bot) | — | Bot App Registration client secret |
| `MICROSOFT_APP_TENANT_ID` | Yes (Teams bot) | — | Azure AD tenant ID (for single-tenant bots) |

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

The bot is deployed as an Azure App Service running an aiohttp web server (`webapp.py` + `bot.py`). Users can chat with the NL2SQL agent directly in Microsoft Teams. The bot returns results as Adaptive Cards with SQL, data tables, and visualization suggestions.

#### Bot commands

| Command | Description |
|---------|-------------|
| *(any question)* | Translates to SQL, executes, and returns results as an Adaptive Card |
| `help` | Shows available commands and example queries |
| `history` | Shows recent queries for the conversation |
| `clear history` | Clears conversation history |

---

## Teams bot deployment

### Prerequisites

1. An **App Registration** in Entra ID (Azure AD) with a client secret
2. An **Azure Bot** resource linked to the App Registration
3. An **Azure App Service** (Linux, Python 3.11) with system-assigned managed identity
4. The managed identity granted **Cognitive Services OpenAI User** on your Azure OpenAI resource

### Step 1 — Create the App Registration

1. Azure Portal → **App registrations** → **New registration**
2. Name: e.g. `NL2SQL Bot`
3. Supported account types: **Single tenant** (or multi-tenant)
4. Click **Register**
5. Note the **Application (client) ID** and **Directory (tenant) ID**
6. Go to **Certificates & secrets** → **New client secret** → copy the **Value**

### Step 2 — Create the Azure Bot

1. Azure Portal → **Create a resource** → search **Azure Bot**
2. Bot handle: e.g. `nl2sql-teams-bot`
3. Type of App: match your App Registration (Single Tenant / Multi Tenant)
4. Use existing app registration: paste your **App ID**
5. Click **Create**
6. Go to the bot → **Channels** → click **Microsoft Teams** → **Apply**

### Step 3 — Create and deploy the App Service

```bash
# Create an App Service Plan (Linux)
az appservice plan create \
  --name nl2sql-bot-plan \
  --resource-group <your-rg> \
  --location <region> \
  --sku B1 \
  --is-linux

# Create the Web App
az webapp create \
  --name <your-app-name> \
  --resource-group <your-rg> \
  --plan nl2sql-bot-plan \
  --runtime "PYTHON:3.11"

# Enable managed identity
az webapp identity assign \
  --name <your-app-name> \
  --resource-group <your-rg>

# Set the startup command
az webapp config set \
  --name <your-app-name> \
  --resource-group <your-rg> \
  --startup-file "python webapp.py"

# Set environment variables
az webapp config appsettings set \
  --name <your-app-name> \
  --resource-group <your-rg> \
  --settings \
    MICROSOFT_APP_ID=<your-app-id> \
    MICROSOFT_APP_PASSWORD=<your-client-secret> \
    MICROSOFT_APP_TENANT_ID=<your-tenant-id> \
    AZURE_OPENAI_ENDPOINT=<your-openai-endpoint> \
    AZURE_OPENAI_DEPLOYMENT=<your-deployment-name> \
    WEBSITES_PORT=8000 \
    WEBSITES_CONTAINER_START_TIME_LIMIT=600

# Deploy the code
az webapp up \
  --name <your-app-name> \
  --resource-group <your-rg> \
  --runtime "PYTHON:3.11"
```

### Step 4 — Grant the managed identity access to Azure OpenAI

In the Azure Portal, go to your **Azure OpenAI resource** → **Access control (IAM)** → **Add role assignment**:

- Role: **Cognitive Services OpenAI User**
- Assign access to: **Managed identity** → **App Service** → select your app
- Click **Review + assign**

### Step 5 — Set the messaging endpoint

In the **Azure Bot** resource → **Configuration** → set **Messaging endpoint** to:

```
https://<your-app-name>.azurewebsites.net/api/messages
```

### Step 6 — Install the bot in Teams

#### Option A: Sideload (development)

1. Copy `function_app/teams-manifest/manifest.json` and replace `{{MICROSOFT_APP_ID}}` with your actual App ID
2. Add two icon files to the same folder:
   - `color.png` — 192×192 px full-color icon
   - `outline.png` — 32×32 px transparent-background white outline icon
3. Zip the three files (manifest.json + color.png + outline.png) into a single ZIP — files must be at the root of the ZIP, not inside a subfolder
4. In Teams → **Apps** → **Manage your apps** → **Upload a custom app** → select the ZIP file

#### Option B: Admin deployment (organization-wide)

1. Prepare the ZIP as described above
2. Go to [Teams Admin Center](https://admin.teams.microsoft.com) → **Teams apps** → **Manage apps** → **Upload new app**
3. Upload the ZIP file
4. Set app policies to control which users can access the bot

#### Option C: Test in Azure Portal

1. Go to the **Azure Bot** resource → **Test in Web Chat**
2. Type a query to verify the bot responds before deploying to Teams

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

Seed data: 10 plants, 30 POs, 40 inventory snapshots, 25 demand records — all synthetic dummy values.

---

## Extensibility

### Configuring the LLM engine

The LLM engine uses the `openai` Python package with the AzureOpenAI client.
Authentication order:

1. If `AZURE_OPENAI_API_KEY` is set → uses API key auth
2. Otherwise → uses `DefaultAzureCredential` (managed identity in Azure, `az login` locally)

### Customising the LLM prompt

Edit the `_SYSTEM_PROMPT` in `nl2sql/llm_engine.py` to adjust the
instructions, add few-shot examples, or change the output format.

### Updating the schema

1. Replace `data/snowflake_table_columns.csv` with an updated export.
2. The schema is parsed automatically at import time — no code changes needed.
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
- **No authentication / authorisation** – The Streamlit app exposes a raw SQL
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
