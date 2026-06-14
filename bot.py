#!/usr/bin/env python3
"""gdoc — Group Doctor Telegram Moderator Bot entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from ai import AIClassifier
from config import Config
from context import BotContext
from database import Database
from handlers import (
    callback_router,
    handle_message,
    handle_my_chat_member,
    help_command,
    panel_command,
    start_command,
    superadmin_command,
)
from moderation import ModerationEngine
from notification_queue import NotificationQueue
from redis_cache import RedisCache

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
)
logger = logging.getLogger("gdoc")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception while processing update: %s", context.error)


async def post_init(application: Application) -> None:
    db = Database()
    cache = RedisCache()
    await db.connect()
    await cache.connect()
    await db.ensure_super_admin(Config.SUPER_ADMIN_ID)

    api_key = await db.get_ai_api_key()
    ai_settings = await db.get_ai_settings()
    ai = AIClassifier(
        api_key=ai_settings["api_key"],
        provider=ai_settings["provider"],
        model=ai_settings["model"],
        base_url=ai_settings["base_url"] or None,
    )
    await ai.start()

    moderation = ModerationEngine(db, cache, ai)
    notify_queue = NotificationQueue(application.bot)
    await notify_queue.start()

    application.bot_data["ctx"] = BotContext(
        db=db,
        cache=cache,
        moderation=moderation,
        ai=ai,
        notify_queue=notify_queue,
    )
    logger.info(
        "gdoc bot initialized (provider=%s, model=%s, ai_configured=%s)",
        ai.provider,
        ai.model,
        bool(ai.api_key),
    )


async def post_shutdown(application: Application) -> None:
    ctx: BotContext = application.bot_data.get("ctx")
    if not ctx:
        return
    await ctx.notify_queue.stop()
    await ctx.ai.close()
    await ctx.cache.close()
    await ctx.db.close()
    logger.info("gdoc bot shutdown complete")


def build_application() -> Application:
    Config.validate()

    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )

    application = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("panel", panel_command))
    application.add_handler(CommandHandler("superadmin", superadmin_command))
    application.add_handler(CallbackQueryHandler(callback_router, pattern=r"^gdoc:"))
    application.add_handler(MessageHandler(filters.StatusUpdate.MY_CHAT_MEMBER, handle_my_chat_member))
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS | filters.ChatType.PRIVATE,
            handle_message,
        ),
    )
    application.add_error_handler(error_handler)

    return application


def main() -> None:
    application = build_application()

    if Config.USE_WEBHOOK:
        if not Config.WEBHOOK_URL:
            logger.error("USE_WEBHOOK=true but WEBHOOK_URL is empty")
            sys.exit(1)

        webhook_url = Config.WEBHOOK_URL.rstrip("/") + Config.WEBHOOK_PATH
        logger.info("Starting webhook mode on %s:%s%s", Config.WEBHOOK_HOST, Config.WEBHOOK_PORT, Config.WEBHOOK_PATH)

        application.run_webhook(
            listen=Config.WEBHOOK_HOST,
            port=Config.WEBHOOK_PORT,
            url_path=Config.WEBHOOK_PATH.lstrip("/"),
            webhook_url=webhook_url,
            secret_token=Config.WEBHOOK_SECRET or None,
            drop_pending_updates=True,
        )
    else:
        logger.info("Starting polling mode")
        application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
