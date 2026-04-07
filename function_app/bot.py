"""
bot.py – Teams-compatible Bot Framework bot for NL2SQL.

Handles incoming messages, translates natural language to SQL, executes the
query, and returns results as an Adaptive Card in Teams.
"""

from __future__ import annotations

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
        except Exception as exc:
            logger.exception("Translation failed")
            await turn_context.send_activity(f"Translation failed: {exc}")
            return

        # Execute
        result_text = ""
        chart_hint = ""
        try:
            rows = execute_sql(sql)
            if rows:
                df = pd.DataFrame(rows)
                result_text = _df_to_markdown(df)

                chart_spec = suggest_chart(df, user_text)
                if chart_spec:
                    chart_hint = (
                        f"\n\n📊 *Suggested visualization: "
                        f"**{chart_spec['chart_type'].title()} chart** — "
                        f"{chart_spec.get('title', '')}*"
                    )
            else:
                result_text = "_Query returned no rows._"
        except Exception as exc:
            logger.exception("Execution failed")
            result_text = f"Execution error: {exc}"

        # Build Adaptive Card response
        card = _build_adaptive_card(user_text, sql, result_text, chart_hint)
        message = MessageFactory.attachment(card)
        await turn_context.send_activity(message)

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


def _df_to_markdown(df: pd.DataFrame, max_rows: int = 20) -> str:
    """Convert a DataFrame to a Markdown table (truncated for Teams display)."""
    if len(df) > max_rows:
        display_df = df.head(max_rows)
        suffix = f"\n\n_...and {len(df) - max_rows} more rows_"
    else:
        display_df = df
        suffix = ""

    # Limit column width
    truncated = display_df.astype(str).apply(
        lambda col: col.str[:40]
    )
    return truncated.to_markdown(index=False) + suffix


def _build_adaptive_card(
    question: str, sql: str, result: str, chart_hint: str = ""
) -> Attachment:
    """Build a Bot Framework Adaptive Card attachment."""
    card_body = [
        {
            "type": "TextBlock",
            "text": f"**Question:** {question}",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": "**Generated SQL:**",
            "wrap": True,
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": f"```sql\n{sql}\n```",
            "wrap": True,
            "fontType": "Monospace",
        },
        {
            "type": "TextBlock",
            "text": "**Results:**",
            "wrap": True,
            "spacing": "Medium",
        },
        {
            "type": "TextBlock",
            "text": result,
            "wrap": True,
            "fontType": "Monospace",
            "size": "Small",
        },
    ]

    if chart_hint:
        card_body.append(
            {
                "type": "TextBlock",
                "text": chart_hint,
                "wrap": True,
                "spacing": "Medium",
                "isSubtle": True,
            }
        )

    card_content = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": card_body,
    }

    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card_content,
    )
