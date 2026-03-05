"""
app.py – Streamlit UI for the NL2SQL demo.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from nl2sql.db import DB_PATH, execute_sql, init_db
from nl2sql.engine import translate
from nl2sql.eval import run_evaluation

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
        "**Note:** This is a rule-based demo. Translations may be "
        "incomplete or inaccurate.  All data is synthetic."
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
        sql = translate(nl_input)
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
    "NL2SQL Demo · Rule-based translator · Synthetic data · "
    "Not for production use."
)
