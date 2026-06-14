"""Shared moderation action helpers."""

from __future__ import annotations

import asyncio
import logging

from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from context import BotContext

logger = logging.getLogger(__name__)


async def increment_warning_cached(ctx: BotContext, chat_id: int, user_id: int) -> tuple[int, bool]:
    count, auto_banned = await ctx.db.increment_warning(chat_id, user_id)
    await ctx.cache.set_warning_count(chat_id, user_id, count)
    return count, auto_banned


async def reset_warnings_cached(ctx: BotContext, chat_id: int, user_id: int) -> None:
    await ctx.db.reset_warnings(chat_id, user_id)
    await ctx.cache.set_warning_count(chat_id, user_id, 0)


async def safe_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> bool:
    for attempt in range(3):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except (BadRequest, Forbidden) as exc:
            logger.warning("Could not delete message %s in %s: %s", message_id, chat_id, exc)
            return False
        except TimedOut:
            await asyncio.sleep(1)
    return False


async def ban_user_in_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    reason: str,
    *,
    revoke_messages: bool = False,
    ctx: BotContext | None = None,
) -> None:
    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            revoke_messages=revoke_messages,
        )
        if ctx:
            await ctx.db.set_group_ban(chat_id, user_id, True, reason)
        logger.info("Banned user %s in chat %s: %s", user_id, chat_id, reason)
    except Forbidden:
        logger.warning("Missing permissions to ban user %s in %s", user_id, chat_id)
    except RetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        try:
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                revoke_messages=revoke_messages,
            )
            if ctx:
                await ctx.db.set_group_ban(chat_id, user_id, True, reason)
        except Exception as inner:
            logger.error("Ban retry failed: %s", inner)
    except Exception as exc:
        logger.error("Ban failed for user %s in %s: %s", user_id, chat_id, exc)


async def unban_user_in_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    *,
    ctx: BotContext | None = None,
) -> bool:
    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True,
        )
        if ctx:
            await ctx.db.set_group_ban(chat_id, user_id, False)
        logger.info("Unbanned user %s in chat %s", user_id, chat_id)
        return True
    except Forbidden:
        logger.warning("Missing permissions to unban user %s in %s", user_id, chat_id)
        return False
    except RetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        try:
            await context.bot.unban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                only_if_banned=True,
            )
            if ctx:
                await ctx.db.set_group_ban(chat_id, user_id, False)
            return True
        except Exception as inner:
            logger.error("Unban retry failed: %s", inner)
            return False
    except Exception as exc:
        logger.error("Unban failed for user %s in %s: %s", user_id, chat_id, exc)
        return False


async def restore_message_from_audit(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_text: str,
    user_label: str,
) -> bool:
    """Re-post deleted message content to the group."""
    if not message_text.strip():
        return False
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"↩️ پیام بازگردانده‌شده از {user_label}:\n\n{message_text[:3500]}",
        )
        return True
    except (BadRequest, Forbidden) as exc:
        logger.warning("Could not restore message in %s: %s", chat_id, exc)
        return False
