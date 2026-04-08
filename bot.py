"""
bot.py – Teams-compatible Bot Framework bot for NL2SQL.

Handles incoming messages, translates natural language to SQL, executes the
query, and returns results as an Adaptive Card in Teams with chart images.
"""

from __future__ import annotations

import base64
import io
import logging
from collections import defaultdict

import pandas as pd
from botbuilder.core import ActivityHandler, MessageFactory, TurnContext
from botbuilder.schema import Attachment, CardAction, ActionTypes

from nl2sql.db import DB_PATH, execute_sql, init_db
from nl2sql.llm_engine import translate_llm, is_llm_available
from nl2sql.engine import translate as translate_rules
from nl2sql.visualize import suggest_chart

logger = logging.getLogger(__name__)

# Per-conversation chat history (in-memory; keyed by conversation ID)
_MAX_HISTORY = 50
_history: dict[str, list[dict]] = defaultdict(list)

# Max columns to show in Teams (keep it readable)
_MAX_DISPLAY_COLS = 8
_MAX_DISPLAY_ROWS = 15


class NL2SQLBot(ActivityHandler):
    """Bot that translates natural-language questions to SQL and returns results."""

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        user_text = (turn_context.activity.text or "").strip()
        conv_id = turn_context.activity.conversation.id

        if not user_text:
            await turn_context.send_activity("Please type a question about your data.")
            return

        # Handle special commands
        if user_text.lower() in ("/help", "help"):
            await self._send_help(turn_context)
            return

        if user_text.lower() in ("/history", "history"):
            await self._send_history(turn_context, conv_id)
            return

        if user_text.lower() in ("/clear", "clear history"):
            _history[conv_id] = []
            await turn_context.send_activity("Chat history cleared.")
            return

        # Ensure DB exists
        if not DB_PATH.exists():
            init_db()

        # Translate
        try:
            if is_llm_available():
                sql = translate_llm(user_text)
            else:
                sql = translate_rules(user_text)
        except ValueError as exc:
            logger.warning("Invalid user input: %s", exc)
            await turn_context.send_activity(f"Invalid query: {exc}")
            return
        except RuntimeError as exc:
            logger.error("Translation service error: %s", exc)
            await turn_context.send_activity(
                "The translation service is temporarily unavailable. Please try again."
            )
            return
        except Exception as exc:
            logger.exception("Unexpected translation error")
            await turn_context.send_activity(
                "An unexpected error occurred. Please try again later."
            )
            return

        # Execute
        result_df = None
        error_msg = None
        try:
            rows = execute_sql(sql)
            if rows:
                result_df = pd.DataFrame(rows)
            else:
                error_msg = "_Query returned no rows._"
        except Exception as exc:
            logger.exception("Execution failed")
            error_msg = "Query execution failed. The generated SQL may be invalid for this dataset."

        # Build chart image if applicable
        chart_image_b64 = None
        chart_spec = None
        synopsis = None
        if result_df is not None and not result_df.empty:
            chart_spec = suggest_chart(result_df, user_text)
            if chart_spec:
                chart_image_b64 = _render_chart_image(chart_spec, result_df)
            # Generate a plain-English synopsis for non-technical users
            synopsis = _generate_synopsis(user_text, result_df)

        # Build and send the Adaptive Card
        card = _build_adaptive_card(
            question=user_text,
            sql=sql,
            df=result_df,
            error=error_msg,
            synopsis=synopsis,
        )
        message = MessageFactory.attachment(card)
        await turn_context.send_activity(message)

        # Send chart as a separate image attachment (Teams doesn't support
        # base64 data URIs inside Adaptive Cards)
        if chart_image_b64 and chart_spec:
            chart_title = chart_spec.get("title", "Chart")
            chart_attachment = Attachment(
                content_type="image/png",
                content_url=f"data:image/png;base64,{chart_image_b64}",
                name=f"{chart_title}.png",
            )
            chart_msg = MessageFactory.attachment(chart_attachment, text=f"📊 {chart_title}")
            await turn_context.send_activity(chart_msg)

        # Save to history
        _history[conv_id].append({"question": user_text, "sql": sql})
        if len(_history[conv_id]) > _MAX_HISTORY:
            _history[conv_id] = _history[conv_id][-_MAX_HISTORY:]

    async def on_members_added_activity(self, members_added, turn_context: TurnContext) -> None:
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 Hello! I'm the **NL2SQL Bot**. Ask me a question about "
                    "your data in plain English, and I'll translate it to SQL "
                    "and return the results.\n\n"
                    "Type **help** to see available commands."
                )

    async def _send_help(self, turn_context: TurnContext) -> None:
        help_text = (
            "**NL2SQL Bot Commands**\n\n"
            "- Just type a question to query your data\n"
            "- **help** — Show this message\n"
            "- **history** — Show recent queries\n"
            "- **clear history** — Clear conversation history\n\n"
            "**Example questions:**\n"
            "- List all open purchase orders\n"
            "- Top 5 purchase orders by open value in USD\n"
            "- Count of purchase orders by vendor\n"
            "- Total open value by plant\n"
        )
        await turn_context.send_activity(help_text)

    async def _send_history(self, turn_context: TurnContext, conv_id: str) -> None:
        entries = _history.get(conv_id, [])
        if not entries:
            await turn_context.send_activity("No chat history yet.")
            return

        lines = ["**Recent queries:**\n"]
        for i, entry in enumerate(entries[-10:], 1):
            lines.append(f"{i}. {entry['question']}")

        await turn_context.send_activity("\n".join(lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Columns to prioritize when trimming wide tables for display
_PRIORITY_COLUMNS = [
    "PURCHASE_ORDER_ID", "PLANT_ID", "VEND_NM", "MATERIAL_ID",
    "MATERIAL_GROUP_DESCRIPTION", "OPEN_QTY", "OPEN_VALUE_IN_USD",
    "PO_SCHD_LINE_DELIVERY_DATE", "EXCPTN_MSG_DESC", "SUPPLIER_TYPE",
    "PLANT_NAME", "CITY", "REGION", "COUNTRY",
    "SEGMENT", "LIFECYCLE", "ON_HAND_QTY", "EXCESS_QTY",
]


def _select_display_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Pick the most useful columns for display, up to _MAX_DISPLAY_COLS."""
    if len(df.columns) <= _MAX_DISPLAY_COLS:
        return df

    # Pick priority columns that exist in the DataFrame
    selected = [c for c in _PRIORITY_COLUMNS if c in df.columns]

    # Fill remaining slots with other columns
    remaining = [c for c in df.columns if c not in selected]
    slots = _MAX_DISPLAY_COLS - len(selected)
    if slots > 0:
        selected.extend(remaining[:slots])

    # If no priority columns matched, take the first N
    if not selected:
        selected = list(df.columns[:_MAX_DISPLAY_COLS])

    return df[selected[:_MAX_DISPLAY_COLS]]


def _df_to_table_rows(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to Adaptive Card table rows."""
    display_df = _select_display_columns(df)

    if len(display_df) > _MAX_DISPLAY_ROWS:
        display_df = display_df.head(_MAX_DISPLAY_ROWS)

    # Format numeric columns
    for col in display_df.select_dtypes(include="number").columns:
        display_df[col] = display_df[col].apply(
            lambda x: f"{x:,.2f}" if abs(x) >= 1000 else f"{x:g}" if pd.notna(x) else ""
        )

    rows = []
    for _, row in display_df.iterrows():
        cells = [{"type": "TableCell", "items": [{"type": "TextBlock", "text": str(v)[:30], "wrap": True, "size": "Small"}]} for v in row.values]
        rows.append({"type": "TableRow", "cells": cells})

    return display_df.columns.tolist(), rows


def _render_chart_image(chart_spec: dict, df: pd.DataFrame) -> str | None:
    """Render a chart as a base64-encoded PNG image."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        chart_type = chart_spec.get("chart_type")
        x = chart_spec.get("x")
        y = chart_spec.get("y")
        title = chart_spec.get("title", "")

        display_df = df.head(25)  # Limit data points for readability

        fig, ax = plt.subplots(figsize=(10, 5))

        if chart_type == "bar":
            ax.barh(display_df[x].astype(str), display_df[y], color="#4A90D9")
            ax.set_xlabel(y)
            ax.set_ylabel(x)
        elif chart_type == "pie":
            ax.pie(
                display_df[y],
                labels=display_df[x].astype(str),
                autopct="%1.0f%%",
                startangle=90,
            )
            ax.set_aspect("equal")
        elif chart_type == "line":
            ax.plot(display_df[x].astype(str), display_df[y], marker="o", color="#4A90D9")
            ax.set_xlabel(x)
            ax.set_ylabel(y)
            plt.xticks(rotation=45, ha="right")
        elif chart_type == "scatter":
            ax.scatter(display_df[x], display_df[y], color="#4A90D9", alpha=0.7)
            ax.set_xlabel(x)
            ax.set_ylabel(y)
        elif chart_type == "area":
            ax.fill_between(range(len(display_df)), display_df[y], alpha=0.3, color="#4A90D9")
            ax.plot(display_df[y].values, color="#4A90D9")
            ax.set_xlabel(x)
            ax.set_ylabel(y)
        else:
            plt.close(fig)
            return None

        ax.set_title(title, fontsize=12, fontweight="bold")
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as exc:
        logger.warning("Chart rendering failed: %s", exc)
        return None


def _generate_synopsis(question: str, df: pd.DataFrame) -> str | None:
    """Ask the LLM to produce a brief plain-English summary of the query results."""
    if not is_llm_available() or df is None or df.empty:
        return None

    try:
        import os
        from nl2sql.llm_engine import _get_client

        client = _get_client()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")

        # Build a compact data sample for the LLM
        sample = df.head(10).to_csv(index=False)
        total_rows = len(df)

        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful data analyst. The user asked a question "
                        "about their business data. You are given the question and "
                        "a sample of the query results. Write a brief 2-3 sentence "
                        "summary in plain English that a non-technical business user "
                        "would understand. Highlight key numbers, trends, or insights. "
                        "Do NOT mention SQL, tables, columns, or technical terms. "
                        "Do NOT use markdown formatting."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n\n"
                        f"Total results: {total_rows} rows\n\n"
                        f"Sample data:\n{sample}"
                    ),
                },
            ],
            temperature=0.3,
            max_completion_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Synopsis generation failed: %s", exc)
        return None


def _build_adaptive_card(
    question: str,
    sql: str,
    df: pd.DataFrame | None,
    error: str | None,
    synopsis: str | None = None,
) -> Attachment:
    """Build a Bot Framework Adaptive Card with synopsis and table."""
    card_body = [
        {
            "type": "TextBlock",
            "text": f"🔎 {question}",
            "wrap": True,
            "weight": "Bolder",
            "size": "Medium",
        },
    ]

    # Synopsis first — the plain-English answer for non-technical users
    if synopsis:
        card_body.append({
            "type": "TextBlock",
            "text": synopsis,
            "wrap": True,
            "spacing": "Small",
        })

    # SQL in a collapsible subtle block
    card_body.append({
        "type": "TextBlock",
        "text": f"```sql\n{sql}\n```",
        "wrap": True,
        "fontType": "Monospace",
        "size": "Small",
        "spacing": "Small",
        "isSubtle": True,
    })

    if error:
        card_body.append({
            "type": "TextBlock",
            "text": error,
            "wrap": True,
            "color": "Attention",
        })
    elif df is not None and not df.empty:
        # Build a proper Adaptive Card Table
        columns, rows = _df_to_table_rows(df)

        header_cells = [
            {"type": "TableCell", "items": [{"type": "TextBlock", "text": col, "weight": "Bolder", "size": "Small", "wrap": True}]}
            for col in columns
        ]

        table = {
            "type": "Table",
            "gridStyle": "accent",
            "firstRowAsHeader": True,
            "showGridLines": True,
            "columns": [{"width": 1} for _ in columns],
            "rows": [{"type": "TableRow", "cells": header_cells, "style": "accent"}] + rows,
        }
        card_body.append(table)

        # Row count summary
        total_rows = len(df)
        shown = min(total_rows, _MAX_DISPLAY_ROWS)
        total_cols = len(df.columns)
        shown_cols = min(total_cols, _MAX_DISPLAY_COLS)
        summary_parts = [f"Showing {shown} of {total_rows} rows"]
        if total_cols > _MAX_DISPLAY_COLS:
            summary_parts.append(f"{shown_cols} of {total_cols} columns")
        card_body.append({
            "type": "TextBlock",
            "text": " · ".join(summary_parts),
            "wrap": True,
            "size": "Small",
            "isSubtle": True,
            "spacing": "Small",
        })

    card_content = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": card_body,
    }

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card_content,
    )
