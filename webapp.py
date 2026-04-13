"""
webapp.py – aiohttp entry-point for the Teams bot (Azure App Service).

Exposes a /api/messages POST endpoint for the Bot Framework Service.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback

from aiohttp import web

# Ensure this script's directory is on the path so function_app is importable
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)
os.chdir(_THIS_DIR)

from dotenv import load_dotenv

load_dotenv()

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity

from bot import NL2SQLBot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot Framework adapter
# ---------------------------------------------------------------------------

_SETTINGS = BotFrameworkAdapterSettings(
    app_id=os.getenv("MICROSOFT_APP_ID", ""),
    app_password=os.getenv("MICROSOFT_APP_PASSWORD", ""),
    channel_auth_tenant=os.getenv("MICROSOFT_APP_TENANT_ID", ""),
)

_ADAPTER = BotFrameworkAdapter(_SETTINGS)


async def _on_error(context: TurnContext, error: Exception) -> None:
    logger.error("Bot encountered an error: %s", error)
    logger.error(traceback.format_exc())
    await context.send_activity("Sorry, something went wrong. Please try again.")


_ADAPTER.on_turn_error = _on_error
_BOT = NL2SQLBot()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


async def messages(req: web.Request) -> web.Response:
    if "application/json" not in (req.content_type or ""):
        return web.Response(status=415)

    body = await req.text()
    activity = Activity().deserialize(json.loads(body))
    auth_header = req.headers.get("Authorization", "")

    response = await _ADAPTER.process_activity(
        activity,
        auth_header,
        _BOT.on_turn,
    )

    if response:
        return web.json_response(data=response.body, status=response.status)

    return web.Response(status=200)


async def health(req: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


app = web.Application()
app.router.add_post("/api/messages", messages)
app.router.add_get("/health", health)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8000)
