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

load_dotenv()

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="NL2SQL Demo", page_icon="🔎", layout="wide")
st.title("🔎 NL → SQL Translator")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("⚙️ Controls")

    # --- Engine selector ---
    llm_ready = is_llm_available()
    engine_options = ["LLM (OpenAI)", "Rule-based"]
    default_idx = 0 if llm_ready else 1

    engine_choice = st.radio(
        "Translation engine",
        engine_options,
        index=default_idx,
        help="LLM uses OpenAI API (requires OPENAI_API_KEY). Rule-based uses local pattern matching.",
    )
    use_llm = engine_choice == "LLM (OpenAI)"

    if use_llm and not llm_ready:
        st.warning("⚠️ OPENAI_API_KEY not set. Add it to `.env` or set as environment variable.")
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
    "List all customers",
    "Show orders placed in the last 30 days",
    "Find the top 5 products by total sales",
    "Count of orders where status equals shipped",
    "Average order amount for each customer",
    "Orders for customer named Alice Johnson in 2025",
    "Total revenue by product category in descending order",
    "List products priced above 100 sorted by price desc",
    "Top 3 customers by total spend",
    "Orders with quantity between 2 and 5",
    "Show orders created today",
    "Find customers with gmail.com emails",
]

with st.expander("💡 Example prompts you can try"):
    for ex in EXAMPLES:
        st.code(ex, language=None)

nl_input = st.text_input(
    "Enter a natural-language query:",
    placeholder="e.g. Show all orders placed in the last 30 days",
)

if st.button("Generate SQL", type="primary") and nl_input:
    try:
        if use_llm:
            sql = translate_llm(nl_input)
        else:
            sql = translate_rules(nl_input)
    except Exception as exc:
        st.error(f"Translation failed: {exc}")
        st.stop()

    st.subheader("Generated SQL")
    st.code(sql, language="sql")

    if run_execution:
        st.subheader("Query Results")
        try:
            rows = execute_sql(sql)
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Query returned no rows.")
        except Exception as exc:
            st.error(f"Execution error: {exc}")

st.markdown("---")
st.caption(
    "NL2SQL Demo · LLM + Rule-based translator · Synthetic data · "
    "Not for production use."
)
