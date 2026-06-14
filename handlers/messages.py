"""Message handlers: moderation pipeline and admin text inputs."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from config import Config
from context import BotContext
import i18n
from handlers.admin_utils import can_manage_group_fast, has_admin_access, is_protected_member
from handlers.group_notifications import (
    notify_group_ban,
    notify_group_delete,
    notify_group_warning,
    notify_user_reason_pm,
)
from handlers.moderation_actions import (
    ban_user_in_chat,
    increment_warning_cached,
    restore_message_from_audit,
    safe_delete_message,
)
from handlers.moderation_cmds import try_handle_admin_reply_command
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

    if user.id in ctx.pending_inputs:
        pending = ctx.pending_inputs.get(user.id)
        chat_id = pending.get("chat_id") if pending else None
        can_submit = chat.type == ChatType.PRIVATE
        if not can_submit and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            can_submit = chat_id == chat.id and await can_manage_group_fast(
                context.bot, chat.id, user.id, ctx.db,
            )
        if can_submit:
            await _handle_pending_input(update, context, ctx)
            return

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    if update.message.new_chat_members or update.message.left_chat_member:
        return

    if await try_handle_admin_reply_command(update, context, ctx):
        return

    if await ctx.db.is_globally_banned(user.id):
        await safe_delete_message(context, chat.id, update.message.message_id)
        await notify_user_reason_pm(
            context,
            user.id,
            "🚫 **پیام شما حذف شد.**\nدلیل: بن سراسری توسط مدیریت سیستم.",
        )
        return

    if await is_protected_member(context.bot, chat.id, user.id, ctx.db):
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

    msg_id = update.message.message_id

    if decision.instant_action:
        deleted = await safe_delete_message(context, chat.id, msg_id)
        await ban_user_in_chat(
            context, chat.id, user.id, decision.reason, ctx=ctx, revoke_messages=True,
        )
        reasons = [decision.reason] if decision.reason else []
        await notify_group_ban(context, chat.id, user, 0, reasons)
        await ctx.db.add_audit_log(
            chat_id=chat.id,
            user_id=user.id,
            username=user.username,
            message_text=text,
            classification=decision.classification,
            reason=decision.reason,
            layer=decision.layer,
            action_taken="deleted,ban_requested" if deleted else "delete_failed,ban_requested",
            message_id=msg_id,
        )
        await _notify_cross_group(
            ctx,
            context.bot,
            source_chat_id=chat.id,
            user_id=user.id,
            username=user.username,
            reason=decision.reason,
        )
        return

    review_mode = group and group.action_mode == "keep_alert"

    if review_mode and decision.classification == "SUSPECT":
        audit_id = await ctx.db.add_audit_log(
            chat_id=chat.id,
            user_id=user.id,
            username=user.username,
            message_text=text,
            classification=decision.classification,
            reason=decision.reason,
            layer=decision.layer,
            action_taken="pending_review",
            message_id=msg_id,
            review_status="pending",
        )
        await _alert_admins_for_review(
            ctx, context, chat.id, user, decision, text, audit_id,
        )
        return

    action_taken = await _apply_moderation_action(update, context, ctx, group, decision, text)
    audit_id = await ctx.db.add_audit_log(
        chat_id=chat.id,
        user_id=user.id,
        username=user.username,
        message_text=text,
        classification=decision.classification,
        reason=decision.reason,
        layer=decision.layer,
        action_taken=action_taken,
        message_id=msg_id,
    )

    if decision.should_warn:
        warn_count, auto_banned = await increment_warning_cached(ctx, chat.id, user.id)
        deleted = decision.should_delete
        threshold = group.warning_threshold if group else 3
        if auto_banned:
            await ban_user_in_chat(
                context, chat.id, user.id, decision.reason, ctx=ctx,
            )
            reasons = await ctx.db.get_user_violation_reasons(chat.id, user.id)
            await notify_group_ban(context, chat.id, user, warn_count, reasons)
            await _notify_cross_group(
                ctx,
                context.bot,
                source_chat_id=chat.id,
                user_id=user.id,
                username=user.username,
                reason=f"بن پس از {warn_count} اخطار",
            )
        else:
            await notify_group_warning(
                context,
                chat.id,
                user,
                decision.reason,
                warn_count,
                threshold,
                deleted,
                audit_id=audit_id,
            )

    if decision.should_ban and not decision.should_warn:
        await ban_user_in_chat(
            context, chat.id, user.id, decision.reason, ctx=ctx, revoke_messages=True,
        )
        reasons = [decision.reason] if decision.reason else []
        await notify_group_ban(context, chat.id, user, 0, reasons)
        await _notify_cross_group(
            ctx,
            context.bot,
            source_chat_id=chat.id,
            user_id=user.id,
            username=user.username,
            reason=decision.reason,
        )

    if decision.should_delete and not decision.should_warn and not decision.should_ban:
        await notify_group_delete(
            context, chat.id, user, decision.reason, text, audit_id,
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
    chat = update.effective_chat

    if input_type in ("rules_ban", "rules_suspect", "bl_keyword", "bl_regex", "bl_remove"):
        target_chat_id = pending.get("chat_id")
        if target_chat_id and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            if chat.id != target_chat_id:
                await _reply_input_result(
                    context, user_id, chat.id, i18n.MSG_PENDING_WRONG_GROUP,
                )
                return
            if not await can_manage_group_fast(context.bot, chat.id, user_id, ctx.db):
                await _reply_input_result(context, user_id, chat.id, i18n.MSG_NOT_GROUP_ADMIN)
                return
            if not await has_admin_access(ctx.db, user_id):
                await _reply_input_result(
                    context, user_id, chat.id, i18n.MSG_SUBSCRIPTION_EXPIRED,
                )
                return

    try:
        await update.message.delete()
    except (BadRequest, Forbidden):
        pass

    reply_chat_id = chat.id if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) else user_id

    if input_type == "rules_ban":
        chat_id = pending["chat_id"]
        await ctx.db.update_group_field(chat_id, "custom_rules", text)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_RULES_UPDATED)

    elif input_type == "rules_suspect":
        chat_id = pending["chat_id"]
        await ctx.db.update_group_field(chat_id, "suspect_rules", text)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_RULES_SUSPECT_UPDATED)

    elif input_type == "bl_keyword":
        chat_id = pending["chat_id"]
        await ctx.db.add_blacklist_pattern(chat_id, text, is_regex=False)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_KEYWORD_ADDED.format(text=text),
        )

    elif input_type == "bl_regex":
        chat_id = pending["chat_id"]
        await ctx.db.add_blacklist_pattern(chat_id, text, is_regex=True)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_REGEX_ADDED.format(text=text),
        )

    elif input_type == "bl_remove":
        chat_id = pending["chat_id"]
        await ctx.db.remove_blacklist_pattern(chat_id, text)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_PATTERN_REMOVED.format(text=text),
        )

    elif input_type == "sa_apikey":
        if not await ctx.db.is_super_admin(user_id):
            return
        await ctx.db.set_ai_api_key(text)
        await ctx.refresh_ai_config()
        await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_APIKEY_UPDATED)

    elif input_type == "sa_baseurl":
        if not await ctx.db.is_super_admin(user_id):
            return
        url = text.rstrip("/")
        await ctx.db.set_ai_base_url(url)
        await ctx.refresh_ai_config()
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_BASEURL_UPDATED.format(url=url),
        )

    elif input_type == "sa_webhook_url":
        if not await ctx.db.is_super_admin(user_id):
            return
        url = normalize_webhook_url(text)
        if not validate_webhook_url(url):
            await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_WEBHOOK_INVALID_URL)
            return
        await ctx.db.set_use_webhook(True)
        await ctx.db.set_webhook_url(url)
        update_env_file(Config.ENV_FILE, {"USE_WEBHOOK": "true", "WEBHOOK_URL": url})
        await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_WEBHOOK_URL_SAVED)

    elif input_type == "sa_auth":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            chat_id = int(text)
        except ValueError:
            await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_INVALID_CHAT_ID)
            return
        await ctx.db.set_group_authorized(chat_id, True)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_GROUP_AUTHORIZED.format(chat_id=chat_id),
        )

    elif input_type == "sa_ban_group":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            chat_id = int(text)
        except ValueError:
            await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_INVALID_CHAT_ID)
            return
        await ctx.db.set_group_authorized(chat_id, False)
        await ctx.moderation.invalidate_group_cache(chat_id)
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_GROUP_BANNED.format(chat_id=chat_id),
        )

    elif input_type == "sa_ban_user":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            target_id = int(text)
        except ValueError:
            await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_INVALID_USER_ID)
            return
        await ctx.db.set_global_ban(target_id, True)
        await _reply_input_result(
            context, user_id, reply_chat_id, i18n.MSG_USER_BANNED.format(user_id=target_id),
        )

    elif input_type == "sa_renew":
        if not await ctx.db.is_super_admin(user_id):
            return
        try:
            target_id = int(text)
        except ValueError:
            await _reply_input_result(context, user_id, reply_chat_id, i18n.MSG_INVALID_USER_ID)
            return
        new_expires = await ctx.db.extend_admin_subscription(target_id)
        await _reply_input_result(
            context,
            user_id,
            reply_chat_id,
            i18n.MSG_ADMIN_RENEWED.format(
                user_id=target_id,
                expires=new_expires.strftime("%Y-%m-%d"),
                days=Config.ADMIN_TRIAL_DAYS,
            ),
        )


async def _reply_input_result(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    msg: str,
) -> None:
    try:
        await context.bot.send_message(chat_id=chat_id, text=msg)
    except Forbidden:
        if chat_id != user_id:
            try:
                await context.bot.send_message(chat_id=user_id, text=msg)
            except Forbidden:
                logger.warning("Could not confirm pending input to user %s", user_id)
        else:
            logger.warning("User %s has not started the bot in private chat", user_id)
    except BadRequest as exc:
        logger.warning("Could not send pending input confirmation: %s", exc)


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
        deleted = await safe_delete_message(
            context,
            update.effective_chat.id,
            update.message.message_id,
        )
        actions.append("deleted" if deleted else "delete_failed")
    else:
        actions.append("kept")

    if decision.should_warn:
        actions.append("warned")

    if decision.should_ban:
        actions.append("ban_requested")

    return ",".join(actions)


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


async def _alert_admins_for_review(
    ctx: BotContext,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user,
    decision,
    text: str,
    audit_id: int,
) -> None:
    import keyboards

    admin_ids = await _resolve_admin_ids(ctx, chat_id, context.bot)
    if not admin_ids:
        return

    group_row = await ctx.db.group_to_dict(chat_id)
    group_title = (group_row or {}).get("title") or str(chat_id)
    alert = i18n.format_admin_review_alert(
        group_title,
        user.full_name,
        user.username,
        decision.classification,
        decision.reason,
        text,
    )
    markup = keyboards.admin_review_keyboard(chat_id, audit_id)

    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=alert,
                reply_markup=markup,
                parse_mode="Markdown",
            )
        except Forbidden:
            await ctx.notify_queue.enqueue(
                admin_id,
                alert,
                priority=3,
                dedupe_key=f"review:{audit_id}:{admin_id}",
            )
        except BadRequest as exc:
            logger.warning("Could not send review alert to %s: %s", admin_id, exc)


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

    from telegram.constants import ChatMemberStatus

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
