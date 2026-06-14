"""In-group moderation notification messages with admin action buttons."""

from __future__ import annotations

import logging

from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import i18n
import keyboards

logger = logging.getLogger(__name__)


async def notify_group_warning(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user,
    reason: str,
    warn_count: int,
    threshold: int,
    deleted: bool,
) -> None:
    text = i18n.format_group_warning_notice(
        user.full_name,
        user.username,
        reason,
        warn_count,
        threshold,
        deleted,
    )
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboards.warning_action_keyboard(chat_id, user.id),
            parse_mode="Markdown",
        )
    except (BadRequest, Forbidden) as exc:
        logger.warning("Could not send warning notice in %s: %s", chat_id, exc)


async def notify_group_ban(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user,
    warn_count: int,
    reasons: list[str],
) -> None:
    text = i18n.format_group_ban_notice(
        user.full_name,
        user.username,
        warn_count,
        reasons,
    )
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboards.ban_notice_keyboard(chat_id, user.id),
            parse_mode="Markdown",
        )
    except (BadRequest, Forbidden) as exc:
        logger.warning("Could not send ban notice in %s: %s", chat_id, exc)
