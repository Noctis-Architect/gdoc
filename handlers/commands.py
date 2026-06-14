"""Telegram command handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

import i18n
import keyboards
from context import BotContext
from database import Database

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    ctx: BotContext = context.bot_data["ctx"]
    user = update.effective_user
    await ctx.db.upsert_user(user.id, user.username, user.first_name)

    if await ctx.db.is_super_admin(user.id):
        await update.message.reply_text(i18n.MSG_START_SUPER, parse_mode="Markdown")
        return

    await update.message.reply_text(i18n.MSG_START_USER, parse_mode="Markdown")


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    user = update.effective_user
    ctx: BotContext = context.bot_data["ctx"]

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text(i18n.MSG_PANEL_PRIVATE)
        return

    if not await _user_can_manage_group(update, context, ctx.db):
        await update.message.reply_text(i18n.MSG_NOT_GROUP_ADMIN)
        return

    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    is_admin = bot_member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    await ctx.db.upsert_group(chat.id, chat.title or "", bot_is_admin=is_admin)
    await ctx.db.register_group_admin(chat.id, user.id)

    if not is_admin:
        await update.message.reply_text(i18n.MSG_PROMOTE_BOT, parse_mode="Markdown")
        return

    group = await ctx.db.group_to_dict(chat.id)
    if not group:
        await update.message.reply_text(i18n.MSG_GROUP_NOT_FOUND)
        return

    await update.message.reply_text(
        i18n.format_group_panel_header(group),
        reply_markup=keyboards.group_admin_panel(chat.id, group),
        parse_mode="Markdown",
    )


async def superadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return

    ctx: BotContext = context.bot_data["ctx"]
    if not await ctx.db.is_super_admin(update.effective_user.id):
        await update.message.reply_text(i18n.MSG_ACCESS_DENIED)
        return

    await update.message.reply_text(
        i18n.MSG_SUPER_PANEL,
        reply_markup=keyboards.super_admin_panel(),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(i18n.MSG_HELP, parse_mode="Markdown")


async def _user_can_manage_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    db: Database,
) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if await db.is_super_admin(user.id):
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.CREATOR,
        )
    except Exception:
        return False
