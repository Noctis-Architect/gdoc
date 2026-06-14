"""Reply-based moderation commands for group admins."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions, Update
from telegram.error import BadRequest, Forbidden, RetryAfter
from telegram.ext import ContextTypes

import i18n
from context import BotContext
from handlers.admin_utils import is_group_admin, is_protected_member
from handlers.group_notifications import notify_group_ban, notify_group_warning
from handlers.moderation_actions import ban_user_in_chat, increment_warning_cached, safe_delete_message

logger = logging.getLogger(__name__)

_ADMIN_COMMANDS = frozenset({
    "ban",
    "kick",
    "mute",
    "unmute",
    "warn",
    "del",
    "delete",
    "purge",
})


def parse_admin_command(text: str) -> str | None:
    if not text:
        return None
    cmd = text.strip().lower()
    if cmd.startswith("/"):
        cmd = cmd[1:].split("@", 1)[0]
    return cmd if cmd in _ADMIN_COMMANDS else None


async def try_handle_admin_reply_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: BotContext,
) -> bool:
    """Handle admin reply commands. Returns True if the update was consumed."""
    message = update.message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or not message.reply_to_message:
        return False

    cmd = parse_admin_command(message.text or message.caption or "")
    if not cmd:
        return False

    if not await is_group_admin(context.bot, chat.id, user.id, ctx.db):
        return False

    target_msg = message.reply_to_message
    target_user = target_msg.from_user
    if not target_user or target_user.is_bot:
        await message.reply_text(i18n.MSG_MODCMD_NO_TARGET)
        return True

    if target_user.id == user.id:
        await message.reply_text(i18n.MSG_MODCMD_SELF)
        return True

    if await is_protected_member(context.bot, chat.id, target_user.id, ctx.db):
        await message.reply_text(i18n.MSG_MODCMD_PROTECTED)
        return True

    target_label = target_user.full_name
    if target_user.username:
        target_label += f" (@{target_user.username})"

    try:
        if cmd == "ban":
            await _cmd_ban(context, chat.id, target_user.id, target_msg.message_id)
            reasons = ["بن دستی توسط ادمین"]
            await notify_group_ban(context, chat.id, target_user, 0, reasons)
            result = i18n.MSG_MODCMD_BAN.format(user=target_label)
        elif cmd == "kick":
            await _cmd_kick(context, chat.id, target_user.id, target_msg.message_id)
            result = i18n.MSG_MODCMD_KICK.format(user=target_label)
        elif cmd == "mute":
            await _cmd_mute(context, chat.id, target_user.id)
            result = i18n.MSG_MODCMD_MUTE.format(user=target_label)
        elif cmd == "unmute":
            await _cmd_unmute(context, chat.id, target_user.id)
            result = i18n.MSG_MODCMD_UNMUTE.format(user=target_label)
        elif cmd == "warn":
            count, auto_banned = await increment_warning_cached(ctx, chat.id, target_user.id)
            group = await ctx.db.group_to_dict(chat.id)
            threshold = (group or {}).get("warning_threshold", 3)
            msg_text = target_msg.text or target_msg.caption or ""
            if auto_banned:
                await ban_user_in_chat(context, chat.id, target_user.id, "Warning threshold exceeded")
                reasons = await ctx.db.get_user_violation_reasons(chat.id, target_user.id)
                if not reasons:
                    reasons = ["اخطار دستی توسط ادمین"]
                await notify_group_ban(context, chat.id, target_user, count, reasons)
                result = i18n.MSG_MODCMD_WARN_BAN.format(user=target_label, count=count)
            else:
                await notify_group_warning(
                    context,
                    chat.id,
                    target_user,
                    "اخطار دستی توسط ادمین",
                    count,
                    threshold,
                    deleted=False,
                )
                result = i18n.MSG_MODCMD_WARN.format(user=target_label, count=count)
        elif cmd in ("del", "delete"):
            await safe_delete_message(context, chat.id, target_msg.message_id)
            result = i18n.MSG_MODCMD_DEL
        elif cmd == "purge":
            await _cmd_purge(context, chat.id, target_user.id, target_msg.message_id)
            result = i18n.MSG_MODCMD_PURGE.format(user=target_label)
        else:
            return False
    except Forbidden:
        await message.reply_text(i18n.MSG_MODCMD_NO_PERMISSION)
        return True
    except RetryAfter as exc:
        await message.reply_text(i18n.MSG_MODCMD_RATE_LIMIT.format(seconds=exc.retry_after))
        return True
    except BadRequest as exc:
        logger.warning("Moderation command %s failed: %s", cmd, exc)
        await message.reply_text(i18n.MSG_MODCMD_FAILED.format(error=str(exc)))
        return True

    await ctx.db.add_audit_log(
        chat_id=chat.id,
        user_id=target_user.id,
        username=target_user.username,
        message_text=(target_msg.text or target_msg.caption or "")[:500],
        classification="MANUAL",
        reason=f"admin_cmd:{cmd}",
        layer="admin",
        action_taken=cmd,
    )

    await message.reply_text(result)
    try:
        await message.delete()
    except (BadRequest, Forbidden):
        pass
    return True


async def _cmd_ban(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, message_id: int) -> None:
    await safe_delete_message(context, chat_id, message_id)
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, revoke_messages=True)


async def _cmd_kick(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, message_id: int) -> None:
    await safe_delete_message(context, chat_id, message_id)
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, revoke_messages=False)
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)


async def _cmd_mute(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    until = datetime.now(timezone.utc) + timedelta(days=365)
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=perms,
        until_date=until,
    )


async def _cmd_unmute(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
    )
    await context.bot.restrict_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        permissions=perms,
    )


async def _cmd_purge(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    message_id: int,
) -> None:
    await safe_delete_message(context, chat_id, message_id)
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id, revoke_messages=True)
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
