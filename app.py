"""
app.py – Streamlit UI for the NL2SQL demo.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from nl2sql.db import DB_PATH, execute_sql, init_db
from nl2sql.engine import translate as translate_rules
from nl2sql.llm_engine import translate_llm, is_llm_available
from nl2sql.eval import run_evaluation
from nl2sql.visualize import suggest_chart

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="NL2SQL Demo", page_icon="🔎", layout="wide")
st.title("🔎 NL → SQL Translator")

# ---------------------------------------------------------------------------
# Session-state initialization (chat history)
# ---------------------------------------------------------------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history: list[dict] = []

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Controls")

    # --- Engine selector ---
    llm_ready = is_llm_available()
    engine_options = ["LLM (Azure OpenAI)", "Rule-based"]
    default_idx = 0 if llm_ready else 1

    engine_choice = st.radio(
        "Translation engine",
        engine_options,
        index=default_idx,
        help="LLM uses Azure OpenAI with Entra ID (requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT, plus az login or managed identity). Rule-based uses local pattern matching.",
    )
    use_llm = engine_choice == "LLM (Azure OpenAI)"

    if use_llm and not llm_ready:
        st.warning(
            "⚠️ AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT not set. "
            "Add them to `.env` or set them as environment variables. "
            "Also authenticate with Azure (for example: az login)."
        )
        use_llm = False

    if use_llm:
        st.caption("🤖 Using LLM engine")
    else:
        st.caption("📏 Using rule-based engine")

    st.divider()

    # --- Initialise / Reset DB ---
    if st.button("Initialize DB", help="Create or recreate the SQLite database with seed data"):
        with st.spinner("Creating database…"):
            path = init_db(force=True)
        st.success(f"Database ready at `{path.name}`")

    st.divider()

    # --- Execution toggle ---
    run_execution = st.toggle("Run execution", value=True, help="Execute the generated SQL and show results")

    # --- Visualization toggle ---
    show_charts = st.toggle("Auto-visualize results", value=True, help="Automatically generate charts from query results")

    st.divider()

    # --- Chat history controls ---
    st.subheader("Chat History")
    if st.button("Clear history", help="Clear all chat history"):
        st.session_state.chat_history = []
        st.rerun()

    st.caption(f"{len(st.session_state.chat_history)} conversation(s)")

    st.divider()

    # --- Golden evaluation ---
    st.subheader("Golden Evaluation")
    if st.button("Run golden evaluation"):
        if not DB_PATH.exists():
            st.warning("Database not found — click **Initialize DB** first.")
        else:
            with st.spinner("Evaluating…"):
                report = run_evaluation()

            st.metric("Accuracy", f"{report.accuracy:.1f}%")
            st.metric("Passed / Total", f"{report.passed} / {report.total}")

            if report.mismatches:
                with st.expander(f"❌ {report.failed} Mismatch(es)", expanded=True):
                    for c in report.mismatches:
                        st.markdown(f"**NL:** {c.nl}")
                        st.code(c.golden_sql, language="sql")
                        st.code(c.generated_sql, language="sql")
                        if c.error:
                            st.error(c.error)
                        st.divider()

    st.divider()

    st.caption(
        "**Note:** Translations may be incomplete or inaccurate. "
        "All data is synthetic."
    )

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

# Ensure DB
if not DB_PATH.exists():
    init_db()

# Example prompts
EXAMPLES = [
    "List all open purchase orders",
    "Show all plants",
    "Top 5 purchase orders by open value in USD",
    "Count of purchase orders by vendor",
    "Total open value by plant",
    "Show purchase orders for vendor Honeywell Aerospace",
    "Show plants in the US",
    "Count of materials by segment",
    "Show purchase orders with open quantity greater than 100",
    "Total open value by material group",
    "Average lead time by plant",
    "Top 3 plants by total open purchase order value",
    "Show materials with lifecycle Active",
    "Show purchase orders with exception message Expedite",
]

with st.expander("💡 Example prompts you can try"):
    for ex in EXAMPLES:
        st.code(ex, language=None)

# ---------------------------------------------------------------------------
# Chart rendering helper
# ---------------------------------------------------------------------------


def _render_chart(chart_spec: dict, df: pd.DataFrame) -> None:
    """Render a chart from the visualization spec."""
    chart_type = chart_spec.get("chart_type")
    x = chart_spec.get("x")
    y = chart_spec.get("y")

    if chart_type == "bar":
        st.bar_chart(df, x=x, y=y)
    elif chart_type == "line":
        st.line_chart(df, x=x, y=y)
    elif chart_type == "area":
        st.area_chart(df, x=x, y=y)
    elif chart_type == "pie":
        import plotly.express as px

        fig = px.pie(df, names=x, values=y, title=chart_spec.get("title", ""))
        st.plotly_chart(fig, use_container_width=True)
    elif chart_type == "scatter":
        st.scatter_chart(df, x=x, y=y)


# ---------------------------------------------------------------------------
# Render chat history
# ---------------------------------------------------------------------------

for entry in st.session_state.chat_history:
    with st.chat_message("user"):
        st.markdown(entry["question"])
    with st.chat_message("assistant"):
        st.code(entry["sql"], language="sql")
        if entry.get("df") is not None and not entry["df"].empty:
            st.dataframe(entry["df"], use_container_width=True)
            if entry.get("chart"):
                _render_chart(entry["chart"], entry["df"])
        elif entry.get("error"):
            st.error(entry["error"])


# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

nl_input = st.chat_input(
    placeholder="Ask a question about your data…",
)

if nl_input:
    # Show user message immediately
    with st.chat_message("user"):
        st.markdown(nl_input)

    # Translate
    with st.chat_message("assistant"):
        try:
            if use_llm:
                sql = translate_llm(nl_input)
            else:
                sql = translate_rules(nl_input)
        except Exception as exc:
            st.error(f"Translation failed: {exc}")
            st.session_state.chat_history.append(
                {"question": nl_input, "sql": "", "df": None, "error": str(exc), "chart": None}
            )
            st.stop()

        st.code(sql, language="sql")

        result_df = None
        error_msg = None
        chart_spec = None

        if run_execution:
            try:
                rows = execute_sql(sql)
                if rows:
                    result_df = pd.DataFrame(rows)
                    st.dataframe(result_df, use_container_width=True)

                    # Auto-visualization
                    if show_charts and result_df is not None and not result_df.empty:
                        chart_spec = suggest_chart(result_df, nl_input)
                        if chart_spec:
                            _render_chart(chart_spec, result_df)
                else:
                    st.info("Query returned no rows.")
            except Exception as exc:
                error_msg = str(exc)
                st.error(f"Execution error: {exc}")

        # Persist to chat history
        st.session_state.chat_history.append(
            {
                "question": nl_input,
                "sql": sql,
                "df": result_df,
                "error": error_msg,
                "chart": chart_spec,
            }
        )

st.markdown("---")
st.caption(
    "NL2SQL Demo · LLM + Rule-based translator · Synthetic data · "
    "Not for production use."
)
