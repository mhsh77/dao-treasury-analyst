"""Telegram adapter. Thin: all behavior lives in QuestionService and the agent."""

from __future__ import annotations

import asyncio
import hashlib

import structlog
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from dao_analyst.interfaces.service import QuestionService

log = structlog.get_logger(__name__)

EXAMPLES = (
    "- What was the treasury's UNI balance at the end of 2024?\n"
    "- Who were the top 5 recipients of UNI from the treasury?\n"
    "- Compare UNI outflows in 2024 and 2025.\n"
    "- How much UNI went to the Uniswap Foundation in total?"
)


def user_key(user_id: int) -> str:
    """Pseudonymous id for logs and rate limiting."""
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:12]


def build_app(
    token: str, service: QuestionService, intro: str, allowed_users: set[int] | None = None
) -> Application:  # type: ignore[type-arg]
    def permitted(update: Update) -> bool:
        user = update.effective_user
        return allowed_users is None or (user is not None and user.id in allowed_users)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                f"{intro}\n\nTry:\n{EXAMPLES}", disable_web_page_preview=True
            )

    async def question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        if msg is None or msg.text is None or update.effective_user is None:
            return
        if not permitted(update):
            await msg.reply_text("This bot is private.")
            return
        await msg.chat.send_action(ChatAction.TYPING)
        reply = await asyncio.to_thread(service.ask, user_key(update.effective_user.id), msg.text)
        await msg.reply_text(reply.text, disable_web_page_preview=True)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, question))
    return app
