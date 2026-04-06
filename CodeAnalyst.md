# NL2SQL Demo Architecture Analysis

## Diagram Index

| Diagram Name | Type | Primary Files/Evidence |
|---|---|---|
| System Context | flowchart | app.py, nl2sql/llm_engine.py, nl2sql/engine.py, nl2sql/db.py, README.md |
| Container View | flowchart | app.py, nl2sql/db.py, nl2sql/schema.py, nl2sql/eval.py, data/* |
| Package Dependency | flowchart | app.py, nl2sql/*.py, tests/* |
| Component View | flowchart | app.py, nl2sql/engine.py, nl2sql/llm_engine.py, nl2sql/db.py, nl2sql/eval.py, nl2sql/schema.py |
| Sequence 1: LLM Query Flow | sequenceDiagram | app.py, nl2sql/llm_engine.py, nl2sql/db.py |
| Sequence 2: Rule-Based Query Flow | sequenceDiagram | app.py, nl2sql/engine.py, nl2sql/db.py, nl2sql/schema.py |
| Sequence 3: Golden Evaluation Flow | sequenceDiagram | app.py, nl2sql/eval.py, nl2sql/engine.py, data/golden/golden.sql.jsonl |
| Activity: Rule Translation Pipeline | flowchart | nl2sql/engine.py |
| Activity: DB Bootstrap and Seeding | flowchart | nl2sql/db.py, data/seed/*, nl2sql/schema.py |
| Domain and Schema Classes | classDiagram | nl2sql/schema.py, nl2sql/eval.py |
| Data Flow | flowchart | app.py, generate_seed_data.py, nl2sql/db.py, nl2sql/eval.py, data/* |
| Local Deployment Topology | flowchart | README.md, app.py, .streamlit/config.toml, requirements.txt |
| AuthN/AuthZ Flow (AAD) | sequenceDiagram | nl2sql/llm_engine.py, README.md, requirements.txt |
| Trust Boundaries | flowchart | app.py, nl2sql/llm_engine.py, nl2sql/db.py, .env.example |
| CI/CD Pipeline | N/A | No CI pipeline files found |
| Observability Topology | N/A | No logging/metrics/tracing stack found |
| Zoom-In: Evaluation Comparison Internals | flowchart | nl2sql/eval.py |

## Evidence Map

### 1) Repo purpose summary (from docs and entrypoints)
- The repository is a demo NL2SQL application with Streamlit UI, rule-based fallback translation, optional Azure OpenAI translation, and golden-set evaluation.
- Evidence: README.md, app.py, nl2sql/eval.py.

### 2) Entrypoints identified
- Streamlit web app entrypoint: app.py.
- Seed data generation script: generate_seed_data.py.
- Optional AAD API demo script: nl2sql/demo_aad.py.

### 3) Core layers identified
- UI / orchestration: app.py.
- Translation services:
	- Rule engine: nl2sql/engine.py.
	- LLM engine: nl2sql/llm_engine.py.
- Persistence and execution: nl2sql/db.py.
- Schema/domain metadata: nl2sql/schema.py.
- Evaluation pipeline: nl2sql/eval.py.

### 4) Dependencies identified
- Internal imports tie UI -> translators/db/eval and services -> schema/db.
- External runtime dependencies: streamlit, pandas, openai, azure-identity, python-dotenv.
- External systems: Azure OpenAI and Microsoft Entra ID for AAD token flow.
- Evidence: requirements.txt, nl2sql/llm_engine.py, app.py.

### 5) Data models identified
- In-code dataclasses:
	- ColumnDef, TableDef, JoinRelation in nl2sql/schema.py.
	- CaseResult, EvalReport in nl2sql/eval.py.
- Persistence artifacts:
	- Schema source CSV: data/snowflake_table_columns.csv.
	- Seed CSVs: data/seed/*.csv.
	- SQLite DB: data/demo.sqlite.
	- Golden dataset: data/golden/golden.sql.jsonl.

---

## A) High-Level Architecture

### A1) System Context

Why it exists:
- Answers what users and external systems interact with this app.

```mermaid
flowchart LR
		User[Analyst/User]
		App[NL2SQL Streamlit App]
		AzureAD[Microsoft Entra ID]
		AzureOpenAI[Azure OpenAI Chat Completions]
		SQLite[(SQLite demo.sqlite)]
		SeedCSV[(Seed CSV Files)]
		Golden[(Golden SQL JSONL)]

		User -->|asks NL question| App
		App -->|rule-based translation| App
		App -->|LLM translation request| AzureOpenAI
		App -->|AAD token via credential chain| AzureAD
		App -->|execute SELECT/WITH| SQLite
		SeedCSV -->|initial load| SQLite
		App -->|run evaluation| Golden
		App -->|show SQL and results| User
```

Notes + assumptions:
- Single Streamlit process hosts UI and orchestration.
- Rule-based translation can operate without cloud services.

Pointers:
- app.py
- nl2sql/llm_engine.py
- nl2sql/db.py
- nl2sql/eval.py

### A2) Container Diagram

Why it exists:
- Answers how responsibilities are split into major executable/logical containers.

```mermaid
flowchart TB
		subgraph UI
			A[app.py Streamlit UI]
		end

		subgraph Core Package nl2sql
			B[engine.py Rule Translator]
			C[llm_engine.py AzureOpenAI Translator]
			D[schema.py Metadata Registry]
			E[db.py SQLite Bootstrap and Query]
			F[eval.py Golden Evaluator]
		end

		subgraph Data
			G[(data/snowflake_table_columns.csv)]
			H[(data/seed/*.csv)]
			I[(data/demo.sqlite)]
			J[(data/golden/golden.sql.jsonl)]
		end

		K[Azure OpenAI]
		L[Microsoft Entra ID]

		A -->|translate rules| B
		A -->|translate llm| C
		A -->|execute SQL| E
		A -->|run eval| F
		B -->|table metadata lookup| D
		C -->|build prompt from schema| D
		E -->|DDL generation from table defs| D
		F -->|translate| B
		F -->|execute both SQLs| E
		D --> G
		E --> H
		E --> I
		F --> J
		C -->|token acquisition chain| L
		C -->|chat completions| K
```

Notes + assumptions:
- Evaluator currently uses rule translator only.

Pointers:
- app.py
- nl2sql/eval.py
- nl2sql/schema.py
- nl2sql/db.py

---

## B) Code and Module Structure

### B1) Package/Module Dependency Diagram

Why it exists:
- Answers how code-level dependencies flow across modules.

```mermaid
flowchart LR
		App[app.py]
		DB[nl2sql.db]
		Engine[nl2sql.engine]
		LLM[nl2sql.llm_engine]
		Eval[nl2sql.eval]
		Schema[nl2sql.schema]
		Seed[generate_seed_data.py]
		TestsEngine[tests/test_engine.py]
		TestsEval[tests/test_eval.py]

		App --> DB
		App --> Engine
		App --> LLM
		App --> Eval

		DB --> Schema
		Engine --> Schema
		LLM --> Schema
		Eval --> DB
		Eval --> Engine

		Seed -->|writes seed csv| DB
		TestsEngine --> Engine
		TestsEngine --> DB
		TestsEval --> Eval
		TestsEval --> DB
```

Notes + assumptions:
- Based strictly on imports and direct call paths.

Pointers:
- app.py
- nl2sql/*.py
- tests/*.py

### B2) Component Diagram

Why it exists:
- Answers which internal functions/components collaborate at runtime.

```mermaid
flowchart TB
		UI[Streamlit View and Controls]
		Router[Engine Selection Logic]
		Rule[translate in engine.py]
		LLMCall[translate_llm in llm_engine.py]
		SQLCleaner[_clean_sql]
		DBExec[execute_sql]
		DBInit[init_db]
		EvalRun[run_evaluation]
		GoldenLoad[load_golden]
		ResultCmp[_compare_results]
		SchemaText[schema_for_llm]
		DDLGen[_generate_ddl]

		UI --> Router
		Router -->|rule mode| Rule
		Router -->|llm mode| LLMCall
		LLMCall --> SchemaText
		LLMCall --> SQLCleaner
		UI -->|run execution| DBExec
		UI -->|initialize db| DBInit
		DBInit --> DDLGen
		DDLGen -->|table defs| SchemaText
		UI -->|run golden evaluation| EvalRun
		EvalRun --> GoldenLoad
		EvalRun --> Rule
		EvalRun --> ResultCmp
		ResultCmp --> DBExec
```

Notes + assumptions:
- SchemaText node represents prompt-text generation and schema metadata use.

Pointers:
- app.py
- nl2sql/engine.py
- nl2sql/llm_engine.py
- nl2sql/db.py
- nl2sql/eval.py
- nl2sql/schema.py

---

## C) Runtime Behavior

### C1) Sequence: LLM Query Flow

Why it exists:
- Answers the end-to-end request lifecycle for LLM mode.

```mermaid
sequenceDiagram
		actor U as User
		participant S as Streamlit app.py
		participant L as llm_engine.translate_llm
		participant A as DefaultAzureCredential
		participant O as Azure OpenAI
		participant D as db.execute_sql
		participant Q as SQLite

		U->>S: Enter NL question + click Generate SQL
		S->>L: translate_llm(nl)
		L->>A: get bearer token provider
		A-->>L: AAD token
		L->>O: chat.completions.create(system prompt + nl)
		O-->>L: SQL text
		L-->>S: cleaned SQL
		S->>D: execute_sql(sql)
		D->>Q: execute SELECT/WITH
		Q-->>D: rows
		D-->>S: list of dict rows
		S-->>U: Render SQL + dataframe
```

Notes + assumptions:
- Missing env vars or failed AAD auth exits via exception path in app.py.

Pointers:
- app.py
- nl2sql/llm_engine.py
- nl2sql/db.py

### C2) Sequence: Rule-Based Query Flow

Why it exists:
- Answers deterministic fallback behavior when LLM is not used.

```mermaid
sequenceDiagram
		actor U as User
		participant S as Streamlit app.py
		participant R as engine.translate
		participant X as Detection helpers
		participant D as db.execute_sql
		participant Q as SQLite

		U->>S: Enter NL question + choose Rule-based
		S->>R: translate(nl)
		R->>X: _detect_table/_detect_aggregate/_detect_limit/_detect_where
		X-->>R: query parts
		R-->>S: SELECT statement
		S->>D: execute_sql(sql)
		D->>Q: run query
		Q-->>D: rows
		D-->>S: rows as dicts
		S-->>U: Render SQL + results
```

Notes + assumptions:
- Rule engine handles a narrow pattern subset.

Pointers:
- app.py
- nl2sql/engine.py
- nl2sql/db.py

### C3) Sequence: Golden Evaluation Flow

Why it exists:
- Answers how evaluation metrics and mismatches are computed.

```mermaid
sequenceDiagram
		actor U as User
		participant S as Streamlit app.py
		participant E as eval.run_evaluation
		participant G as eval.load_golden
		participant R as engine.translate
		participant D as db.execute_sql
		participant Q as SQLite

		U->>S: Click Run golden evaluation
		S->>E: run_evaluation(mode=result)
		E->>G: load_golden(jsonl)
		G-->>E: example list
		loop each example
				E->>R: translate(nl)
				R-->>E: generated_sql
				E->>D: execute generated_sql
				D->>Q: query
				Q-->>D: rows
				E->>D: execute golden_sql
				D->>Q: query
				Q-->>D: rows
				E->>E: compare normalized result sets
		end
		E-->>S: EvalReport(total/passed/failed/accuracy/cases)
		S-->>U: Metrics + mismatches
```

Notes + assumptions:
- Result mode ignores column alias names and compares values.

Pointers:
- app.py
- nl2sql/eval.py
- nl2sql/engine.py

### C4) Activity: Rule Translation Pipeline

Why it exists:
- Answers decision ordering in the fallback translator.

```mermaid
flowchart TD
		A["Start translate(nl)"] --> B["Normalize text"]
		B --> C[Detect table]
		C --> D[Detect aggregate]
		D --> E[Detect limit]
		E --> F[Detect where clauses]
		F --> G{Aggregate found?}
		G -- Yes --> H[SELECT agg FROM table]
		G -- No --> I[SELECT * FROM table]
		H --> J{Where found?}
		I --> J
		J -- Yes --> K[Append WHERE]
		J -- No --> L[Skip WHERE]
		K --> M{Limit found?}
		L --> M
		M -- Yes --> N[Append LIMIT]
		M -- No --> O[Skip LIMIT]
		N --> P[Return SQL]
		O --> P
```

Notes + assumptions:
- Detection helpers are sequential and not confidence-scored.

Pointers:
- nl2sql/engine.py

### C5) Activity: DB Bootstrap and Seeding

Why it exists:
- Answers the create/recreate lifecycle of the local SQLite store.

```mermaid
flowchart TD
		A["init_db(force, db_path)"] --> B[Ensure parent dir]
		B --> C{force and db exists?}
		C -- Yes --> D[Delete db file]
		C -- No --> E[Continue]
		D --> E
		E --> F[Open sqlite connection]
		F --> G[Iterate TABLES from schema]
		G --> H[Generate DDL per table]
		H --> I[Execute CREATE TABLE]
		I --> J[Commit]
		J --> K{db existed before init?}
		K -- No --> L[Seed from data/seed csv files]
		K -- Yes --> M[Skip seeding]
		L --> N[Commit]
		M --> O[Close connection]
		N --> O
		O --> P[Return db path]
```

Notes + assumptions:
- Missing CSV for a table is skipped silently.

Pointers:
- nl2sql/db.py
- nl2sql/schema.py
- data/seed/*

---

## D) Data and Schemas

### D1) ER/Class Diagram for Core Models

Why it exists:
- Answers how schema metadata and evaluation objects are represented.

```mermaid
classDiagram
		class ColumnDef {
			+name: str
			+data_type: str
			+ordinal_position: int
		}

		class TableDef {
			+name: str
			+columns: dict[str, ColumnDef]
			+fq_name: str
			+column_names(): tuple[str]
			+date_columns(): list[str]
			+numeric_columns(): list[str]
			+text_columns(): list[str]
		}

		class JoinRelation {
			+left_table: str
			+right_table: str
			+left_col: str
			+right_col: str
		}

		class CaseResult {
			+nl: str
			+golden_sql: str
			+generated_sql: str
			+notes: str
			+match: bool
			+error: str | None
		}

		class EvalReport {
			+cases: list[CaseResult]
			+total: int
			+passed: int
			+failed: int
			+accuracy: float
			+mismatches: list[CaseResult]
			+summary(): str
		}

		TableDef "1" *-- "many" ColumnDef : columns
		EvalReport "1" *-- "many" CaseResult : cases
		JoinRelation ..> TableDef : links table names
```

Notes + assumptions:
- No ORM entities were found; schema is metadata-driven.

Pointers:
- nl2sql/schema.py
- nl2sql/eval.py

### D2) Data Flow Diagram

Why it exists:
- Answers where data comes from, how it is transformed, and where it lands.

```mermaid
flowchart LR
		A[User NL Prompt] --> B[Translator Engine]
		B --> C[Generated SQL]
		C --> D[SQLite Query Execution]
		D --> E[Rows to DataFrame]
		E --> F[UI Result Display]

		G[data/snowflake_table_columns.csv] --> H[schema.py TABLES and joins]
		H --> B
		H --> I[db.py DDL generation]

		J[data/seed/*.csv] --> K[db.py seeding]
		I --> L[(data/demo.sqlite)]
		K --> L
		D --> L

		M[data/golden/golden.sql.jsonl] --> N[eval.py evaluation loop]
		B --> N
		N --> O[EvalReport metrics and mismatches]
		O --> P[Sidebar evaluation display]
```

Notes + assumptions:
- Evaluator currently invokes rule engine translation.

Pointers:
- app.py
- nl2sql/schema.py
- nl2sql/db.py
- nl2sql/eval.py
- data/*

---

## E) Ops and Delivery

### E1) Deployment Diagram (Local)

Why it exists:
- Answers how the repository currently runs in practice.

```mermaid
flowchart TB
		subgraph LocalHost[Developer or Demo Host]
			A[Python runtime]
			B[Streamlit process app.py]
			C[nl2sql package modules]
			D[(data/demo.sqlite)]
			E[(.env settings)]
		end

		subgraph Azure
			F[Microsoft Entra ID]
			G[Azure OpenAI Endpoint]
		end

		A --> B
		B --> C
		C --> D
		C --> E
		C --> F
		C --> G
```

Notes + assumptions:
- No Docker/Kubernetes/IaC pipeline files were found.

Pointers:
- README.md
- app.py
- .streamlit/config.toml
- requirements.txt

### E2) CI/CD Pipeline Diagram

Why it exists:
- Would answer how code moves through automated build/test/deploy.

Not applicable:
- No CI/CD configuration files are present in the repository.
- Only local testing instructions and pytest suites were found.

Pointers:
- README.md
- tests/test_engine.py
- tests/test_eval.py

### E3) Observability Diagram

Why it exists:
- Would answer how logs/metrics/traces and alerts propagate.

Not applicable:
- No observability stack, tracing SDK, metrics exporter, or alerting config was found.

Pointers:
- app.py
- nl2sql/*.py
- requirements.txt

---

## F) Security

### F1) AuthN/AuthZ Flow (AAD)

Why it exists:
- Answers token issuance and authorization path for Azure OpenAI access.

```mermaid
sequenceDiagram
		participant App as llm_engine.translate_llm
		participant Cred as DefaultAzureCredential chain
		participant Entra as Microsoft Entra ID
		participant AOAI as Azure OpenAI Resource

		App->>Cred: Request token for cognitiveservices scope
		Cred->>Entra: Authenticate identity
		Entra-->>Cred: Access token
		Cred-->>App: Bearer token provider
		App->>AOAI: chat.completions with AAD bearer token
		AOAI-->>App: response if identity has resource access
```

Notes + assumptions:
- App-level user authentication is not implemented.
- Access control is enforced at Azure resource/identity policy layer.

Pointers:
- nl2sql/llm_engine.py
- README.md

### F2) Trust Boundaries Diagram

Why it exists:
- Answers where untrusted input enters and where sensitive trust boundaries exist.

```mermaid
flowchart LR
		subgraph UserBoundary[Untrusted User Input]
			U[NL text input]
		end

		subgraph AppBoundary[Trusted App Process]
			A[app.py controls]
			B[engine.py translation]
			C[llm_engine.py translation]
			D[db.execute_sql guard]
			E[(demo.sqlite)]
		end

		subgraph CloudBoundary[External Cloud Trust Domain]
			F[Microsoft Entra ID]
			G[Azure OpenAI]
		end

		U --> A
		A --> B
		A --> C
		B --> D
		C --> D
		D --> E
		C --> F
		C --> G

		H[.env and env vars] --> C
```

Notes + assumptions:
- db.execute_sql enforces SELECT/WITH-only statement restriction.

Pointers:
- app.py
- nl2sql/db.py
- nl2sql/llm_engine.py
- .env.example

---

## Zoom-In Diagram

### Z1) Evaluation Comparison Internals

Why it exists:
- Answers how mode-specific comparison (string vs result) works and where mismatches are emitted.

```mermaid
flowchart TD
		A[run_evaluation] --> B[Ensure DB exists]
		B --> C[Load golden examples]
		C --> D[Loop each example]
		D --> E[Generate SQL via engine.translate]
		E --> F{mode == string?}
		F -- Yes --> G[Normalize generated SQL]
		G --> H[Normalize golden SQL]
		H --> I[Text equality]
		F -- No --> J[Execute generated SQL]
		J --> K[Execute golden SQL]
		K --> L[rows_to_comparable on both]
		L --> M[Result-set equality]
		I --> N[Append CaseResult]
		M --> N
		N --> O{error?}
		O -- Yes --> P[CaseResult.error set]
		O -- No --> Q[CaseResult.match set]
		P --> R[Next example]
		Q --> R
		R --> S[Return EvalReport]
```

Notes + assumptions:
- _rows_to_comparable intentionally ignores alias names by comparing value tuples.

Pointers:
- nl2sql/eval.py

---

## Omitted As Not Applicable (with rationale)

- Background workers/schedulers diagram: no worker framework or scheduler files found.
- API route diagram: no FastAPI/Flask/Django route layer present; UI is Streamlit-based.
- Queue/event-bus diagram: no queue/broker dependencies in requirements or code.
- Multi-environment cloud deployment diagram: no IaC or deployment manifests found.

## Uncertainty Notes

- README still contains one historical phrase referencing OpenAI in a limitations paragraph, but operational code uses Azure OpenAI + AAD in llm_engine.py.
- nl2sql/demo_aad.py appears to be an auxiliary experiment script and is not imported by app.py.
