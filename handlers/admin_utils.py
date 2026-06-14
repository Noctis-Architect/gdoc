"""Shared admin checks and protected-member logic."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.constants import ChatMemberStatus

from database import Database

logger = logging.getLogger(__name__)

_ADMIN_STATUSES = (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def is_super_admin(db: Database, user_id: int) -> bool:
    return await db.is_super_admin(user_id)


async def has_admin_access(db: Database, user_id: int) -> bool:
    """Super-admin has unlimited access; regular admins need an active subscription."""
    if await is_super_admin(db, user_id):
        return True
    return await db.is_admin_subscription_active(user_id)


async def get_member_status(bot: Bot, chat_id: int, user_id: int) -> str | None:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status
    except Exception as exc:
        logger.warning("Could not fetch member %s in %s: %s", user_id, chat_id, exc)
        return None


async def is_group_admin(bot: Bot, chat_id: int, user_id: int, db: Database) -> bool:
    if await is_super_admin(db, user_id):
        return True
    if not await has_admin_access(db, user_id):
        return False
    admin_ids = await db.get_group_admins(chat_id)
    if user_id in admin_ids:
        return True
    status = await get_member_status(bot, chat_id, user_id)
    return status in _ADMIN_STATUSES


async def is_group_owner(bot: Bot, chat_id: int, user_id: int) -> bool:
    status = await get_member_status(bot, chat_id, user_id)
    return status == ChatMemberStatus.OWNER


async def is_protected_member(bot: Bot, chat_id: int, user_id: int, db: Database) -> bool:
    """Owner, group admins, and super-admin must not be auto-moderated or acted on."""
    if await is_super_admin(db, user_id):
        return True
    status = await get_member_status(bot, chat_id, user_id)
    return status in _ADMIN_STATUSES


async def can_manage_group_fast(
    bot: Bot,
    chat_id: int,
    user_id: int,
    db: Database,
) -> bool:
    """Fast path: DB super-admin / registered admins, then Telegram API fallback."""
    if await is_super_admin(db, user_id):
        return True
    admin_ids = await db.get_group_admins(chat_id)
    if user_id in admin_ids:
        return True
    status = await get_member_status(bot, chat_id, user_id)
    return status in _ADMIN_STATUSES


async def is_telegram_group_admin(bot: Bot, chat_id: int, user_id: int, db: Database) -> bool:
    """True only for Telegram group admins/owner (super-admin bypass for remote management)."""
    if await is_super_admin(db, user_id):
        return True
    status = await get_member_status(bot, chat_id, user_id)
    return status in _ADMIN_STATUSES
