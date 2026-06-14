"""Message handlers: moderation pipeline and admin text inputs."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from config import Config
from context import BotContext
import i18n
from webhook_manager import (
    normalize_webhook_url,
    update_env_file,
    validate_webhook_url,
)

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.effective_chat or not update.message:
        return

    ctx: BotContext = context.bot_data["ctx"]
    user = update.effective_user
    chat = update.effective_chat

    if user.id in ctx.pending_inputs and chat.type == ChatType.PRIVATE:
        await _handle_pending_input(update, context, ctx)
        return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if update.message.new_chat_members or update.message.left_chat_member:
        return

    if await ctx.db.is_globally_banned(user.id):
        await _safe_delete_message(context, chat.id, update.message.message_id)
        return

    await ctx.db.upsert_user(user.id, user.username, user.first_name)
    await ctx.db.upsert_group(chat.id, chat.title or "")

    group_row = await ctx.db.group_to_dict(chat.id)
    if not group_row or not group_row.get("is_authorized"):
        return

    text = update.message.text or update.message.caption or ""
    await ctx.db.increment_messages_processed(chat.id)

    group, decision = await ctx.moderation.evaluate(chat.id, text)
    if not decision.flagged:
        return

    action_taken = await _apply_moderation_action(update, context, ctx, group, decision, text)
    await ctx.db.add_audit_log(
        chat_id=chat.id,
        user_id=user.id,
        username=user.username,
        message_text=text,
        classification=decision.classification,
        reason=decision.reason,
        layer=decision.layer,
        action_taken=action_taken,
    )

    if decision.should_warn:
        warn_count, auto_banned = await _increment_warning_cached(ctx, chat.id, user.id)
        if auto_banned:
            await _ban_user_in_chat(context, chat.id, user.id, "Warning threshold exceeded")
            await _notify_cross_group(
                ctx,
                context.bot,
                source_chat_id=chat.id,
                user_id=user.id,
                username=user.username,
                reason=f"بن پس از {warn_count} اخطار",
            )

    if decision.should_ban and not decision.should_warn:
        await _ban_user_in_chat(context, chat.id, user.id, decision.reason)
        await _notify_cross_group(
            ctx,
            context.bot,
            source_chat_id=chat.id,
            user_id=user.id,
            username=user.username,
            reason=decision.reason,
        )


async def _handle_pending_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: BotContext,
) -> None:
    user_id = update.effective_user.id
    pending = ctx.pending_inputs.pop(user_id, None)
    if not pending or not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    input_type = pending["type"]

    try:
        await update.message.delete()
    except (BadRequest, Forbidden):
        pass

    if input_type == "rules":
        chat_id = pending["chat_id"]
        await ctx.db.update_group_field(chat_id, "custom_rules", text)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await update.message.reply_text(i18n.MSG_RULES_UPDATED)

    elif input_type == "bl_keyword":
        chat_id = pending["chat_id"]
        await ctx.db.add_blacklist_pattern(chat_id, text, is_regex=False)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await update.message.reply_text(i18n.MSG_KEYWORD_ADDED.format(text=text), parse_mode="Markdown")

    elif input_type == "bl_regex":
        chat_id = pending["chat_id"]
        await ctx.db.add_blacklist_pattern(chat_id, text, is_regex=True)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await update.message.reply_text(i18n.MSG_REGEX_ADDED.format(text=text), parse_mode="Markdown")

    elif input_type == "bl_remove":
        chat_id = pending["chat_id"]
        await ctx.db.remove_blacklist_pattern(chat_id, text)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await update.message.reply_text(i18n.MSG_PATTERN_REMOVED.format(text=text), parse_mode="Markdown")

    elif input_type == "sa_apikey":
        if not await ctx.db.is_super_admin(user_id):
            return
        await ctx.db.set_ai_api_key(text)
        await ctx.refresh_ai_config()
        await update.message.reply_text(i18n.MSG_APIKEY_UPDATED)

    elif input_type == "sa_baseurl":
        if not await ctx.db.is_super_admin(user_id):
            return
        url = text.rstrip("/")
        await ctx.db.set_ai_base_url(url)
        await ctx.refresh_ai_config()
        await update.message.reply_text(
            i18n.MSG_BASEURL_UPDATED.format(url=url),
            parse_mode="Markdown",
        )

    elif input_type == "sa_webhook_url":
        if not await ctx.db.is_super_admin(user_id):
            return
        url = normalize_webhook_url(text)
        if not validate_webhook_url(url):
            await update.message.reply_text(i18n.MSG_WEBHOOK_INVALID_URL)
            return
        await ctx.db.set_use_webhook(True)
        await ctx.db.set_webhook_url(url)
        update_env_file(Config.ENV_FILE, {"USE_WEBHOOK": "true", "WEBHOOK_URL": url})
        await update.message.reply_text(i18n.MSG_WEBHOOK_URL_SAVED, parse_mode="Markdown")

    elif input_type == "sa_auth":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            chat_id = int(text)
        except ValueError:
            await update.message.reply_text(i18n.MSG_INVALID_CHAT_ID)
            return
        await ctx.db.set_group_authorized(chat_id, True)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await update.message.reply_text(i18n.MSG_GROUP_AUTHORIZED.format(chat_id=chat_id), parse_mode="Markdown")

    elif input_type == "sa_ban_group":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            chat_id = int(text)
        except ValueError:
            await update.message.reply_text(i18n.MSG_INVALID_CHAT_ID)
            return
        await ctx.db.set_group_authorized(chat_id, False)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await update.message.reply_text(i18n.MSG_GROUP_BANNED.format(chat_id=chat_id), parse_mode="Markdown")

    elif input_type == "sa_ban_user":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text(i18n.MSG_INVALID_USER_ID)
            return
        await ctx.db.set_global_ban(target_id, True)
        await update.message.reply_text(i18n.MSG_USER_BANNED.format(user_id=target_id), parse_mode="Markdown")


async def _apply_moderation_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ctx: BotContext,
    group,
    decision,
    text: str,
) -> str:
    actions = []

    if decision.should_delete:
        deleted = await _safe_delete_message(
            context,
            update.effective_chat.id,
            update.message.message_id,
        )
        actions.append("deleted" if deleted else "delete_failed")
    else:
        actions.append("kept")

    if group and group.action_mode == "keep_alert" and decision.flagged:
        await _alert_group_admins(
            ctx,
            update.effective_chat.id,
            update.effective_user,
            decision,
            text,
            context,
        )
        actions.append("admins_alerted")

    if decision.should_warn:
        actions.append("warned")

    if decision.should_ban:
        actions.append("ban_requested")

    return ",".join(actions)


async def _increment_warning_cached(ctx: BotContext, chat_id: int, user_id: int) -> tuple[int, bool]:
    count, auto_banned = await ctx.db.increment_warning(chat_id, user_id)
    await ctx.cache.set_warning_count(chat_id, user_id, count)
    return count, auto_banned


async def _safe_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> bool:
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


async def _ban_user_in_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    reason: str,
) -> None:
    try:
        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        logger.info("Banned user %s in chat %s: %s", user_id, chat_id, reason)
    except Forbidden:
        logger.warning("Missing permissions to ban user %s in %s", user_id, chat_id)
    except RetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        except Exception as inner:
            logger.error("Ban retry failed: %s", inner)
    except Exception as exc:
        logger.error("Ban failed for user %s in %s: %s", user_id, chat_id, exc)


async def _resolve_admin_ids(ctx: BotContext, chat_id: int, bot) -> list[int]:
    admin_ids = await ctx.db.get_group_admins(chat_id)
    if admin_ids:
        return admin_ids
    try:
        admins = await bot.get_chat_administrators(chat_id)
        return [a.user.id for a in admins if not a.user.is_bot]
    except Exception as exc:
        logger.warning("Could not fetch admins for %s: %s", chat_id, exc)
        return []


async def _alert_group_admins(
    ctx: BotContext,
    chat_id: int,
    user,
    decision,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    admin_ids = await _resolve_admin_ids(ctx, chat_id, context.bot)
    if not admin_ids:
        return

    alert = i18n.format_moderation_alert(
        user.full_name,
        user.username,
        decision.classification,
        decision.reason,
        text,
    )

    for admin_id in admin_ids:
        await ctx.notify_queue.enqueue(
            admin_id,
            alert,
            priority=3,
            dedupe_key=f"alert:{chat_id}:{user.id}:{decision.classification}:{hash(text[:100])}",
        )


async def _notify_cross_group(
    ctx: BotContext,
    bot,
    source_chat_id: int,
    user_id: int,
    username: Optional[str],
    reason: str,
) -> None:
    other_groups = await ctx.db.get_other_groups_for_user(user_id, source_chat_id)
    other_groups = other_groups[: Config.NOTIFY_CROSS_GROUP_MAX_TARGETS]

    if not other_groups:
        return

    user_label = f"@{username}" if username else f"کاربر {user_id}"
    source_group = await ctx.db.group_to_dict(source_chat_id)
    source_title = (source_group or {}).get("title") or str(source_chat_id)

    notification = i18n.format_cross_group_alert(user_label, source_title, reason)
    seen_admins: set[int] = set()
    enqueued = 0

    for target_chat_id in other_groups:
        if target_chat_id == source_chat_id:
            continue

        await ctx.db.add_cross_group_event(
            source_chat_id=source_chat_id,
            user_id=user_id,
            event_type="ban",
            reason=reason,
            target_chat_id=target_chat_id,
        )

        admin_ids = await _resolve_admin_ids(ctx, target_chat_id, bot)
        for admin_id in admin_ids:
            if admin_id in seen_admins:
                continue
            seen_admins.add(admin_id)
            added = await ctx.notify_queue.enqueue(
                admin_id,
                notification,
                priority=7,
                dedupe_key=f"cross:{user_id}:{source_chat_id}:{admin_id}",
            )
            if added:
                enqueued += 1

    logger.info(
        "Cross-group alert queued for user %s: %s groups, %s admin messages",
        user_id,
        len(other_groups),
        enqueued,
    )


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.my_chat_member or not update.effective_chat:
        return

    ctx: BotContext = context.bot_data["ctx"]
    chat = update.effective_chat
    new_status = update.my_chat_member.new_chat_member.status
    is_admin = new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        await ctx.db.upsert_group(chat.id, chat.title or "", bot_is_admin=is_admin)
        await ctx.moderation.invalidate_group_cache(chat.id)

        if is_admin and update.effective_user:
            await ctx.db.register_group_admin(chat.id, update.effective_user.id)

        if is_admin:
            logger.info("Bot promoted to admin in group %s (%s)", chat.id, chat.title)
        else:
            logger.info("Bot is no longer admin in group %s", chat.id)
