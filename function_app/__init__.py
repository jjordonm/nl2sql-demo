"""
function_app – Azure Functions entry-point for the Teams bot.

This module implements a Bot Framework messaging endpoint as an Azure
Function (HTTP trigger).  It receives Activity payloads from the Bot
Framework Service, processes them through the NL2SQL bot logic, and
returns the response.

Required environment variables
-------------------------------
MICROSOFT_APP_ID          – Bot registration App ID
MICROSOFT_APP_PASSWORD    – Bot registration client secret
AZURE_OPENAI_ENDPOINT     – Azure OpenAI endpoint URL
AZURE_OPENAI_DEPLOYMENT   – Azure OpenAI deployment name
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback

import azure.functions as func

# Ensure the project root is on sys.path so ``nl2sql`` is importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity

from function_app.bot import NL2SQLBot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot Framework adapter (created once per cold start)
# ---------------------------------------------------------------------------

_SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.getenv("MICROSOFT_APP_ID", ""),
    app_password=os.getenv("MICROSOFT_APP_PASSWORD", ""),
)

_ADAPTER = BotFrameworkAdapter(_SETTINGS)


async def _on_error(context: TurnContext, error: Exception) -> None:
    """Global error handler for the adapter."""
    logger.error("Bot encountered an error: %s", error)
    logger.error(traceback.format_exc())
    await context.send_activity("Sorry, something went wrong. Please try again.")


_ADAPTER.on_turn_error = _on_error

_BOT = NL2SQLBot()

# ---------------------------------------------------------------------------
# Azure Function entry-point
# ---------------------------------------------------------------------------


async def main(req: func.HttpRequest) -> func.HttpResponse:
    """Handle incoming Bot Framework messages."""
    if req.method != "POST":
        return func.HttpResponse(status_code=405)

    body = req.get_body().decode("utf-8")
    if not body:
        return func.HttpResponse("Request body is empty", status_code=400)

    activity = Activity().deserialize(json.loads(body))
    auth_header = req.headers.get("Authorization", "")

    response = await _ADAPTER.process_activity(
        activity,
        auth_header,
        _BOT.on_turn,
    )

    if response:
        return func.HttpResponse(
            body=json.dumps(response.body),
            status_code=response.status,
            headers={"Content-Type": "application/json"},
        )

    return func.HttpResponse(status_code=200)
