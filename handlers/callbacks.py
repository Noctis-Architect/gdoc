"""Inline callback query handlers for admin panels."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

import i18n
import keyboards
from context import BotContext
from handlers.commands import _user_can_manage_group

logger = logging.getLogger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return

    await query.answer()
    action, chat_id, extra = keyboards.parse_callback(query.data)
    ctx: BotContext = context.bot_data["ctx"]
    user_id = update.effective_user.id

    if action.startswith("sa_"):
        if not await ctx.db.is_super_admin(user_id):
            await query.edit_message_text(i18n.MSG_ACCESS_DENIED)
            return
        await _handle_super_admin(action, query, ctx, context, extra)
        return

    if chat_id and not await _user_can_manage_group(update, context, ctx.db):
        await query.edit_message_text(i18n.MSG_NOT_GROUP_ADMIN)
        return

    handlers = {
        "panel": _show_group_panel,
        "strictness": _show_strictness,
        "set_strictness": _set_strictness,
        "action": _show_action,
        "set_action": _set_action,
        "threshold": _show_threshold,
        "set_threshold": _set_threshold,
        "toggle": _toggle_moderation,
        "rules": _prompt_rules,
        "blacklist": _show_blacklist,
        "bl_add_kw": _prompt_blacklist_keyword,
        "bl_add_rx": _prompt_blacklist_regex,
        "bl_remove": _prompt_blacklist_remove,
        "audit": _show_audit,
    }

    handler = handlers.get(action)
    if handler:
        await handler(query, ctx, chat_id, extra, context)


async def _show_group_panel(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    if not group:
        await query.edit_message_text(i18n.MSG_GROUP_NOT_FOUND)
        return
    await query.edit_message_text(
        i18n.format_group_panel_header(group),
        reply_markup=keyboards.group_admin_panel(chat_id, group),
        parse_mode="Markdown",
    )


async def _show_strictness(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    current = group.get("strictness", "medium") if group else "medium"
    await query.edit_message_text(
        i18n.PROMPT_STRICTNESS,
        reply_markup=keyboards.strictness_keyboard(chat_id, current),
    )


async def _set_strictness(query, ctx: BotContext, chat_id: int, extra: str, _context) -> None:
    if extra not in ("low", "medium", "high"):
        return
    await ctx.db.update_group_field(chat_id, "strictness", extra)
    await ctx.moderation.invalidate_group_cache(chat_id)
    await _show_group_panel(query, ctx, chat_id, "", _context)


async def _show_action(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    current = group.get("action_mode", "delete_flag") if group else "delete_flag"
    await query.edit_message_text(
        i18n.PROMPT_ACTION,
        reply_markup=keyboards.action_mode_keyboard(chat_id, current),
    )


async def _set_action(query, ctx: BotContext, chat_id: int, extra: str, _context) -> None:
    if extra not in ("delete_flag", "keep_alert"):
        return
    await ctx.db.update_group_field(chat_id, "action_mode", extra)
    await ctx.moderation.invalidate_group_cache(chat_id)
    await _show_group_panel(query, ctx, chat_id, "", _context)


async def _show_threshold(query, _ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    await query.edit_message_text(
        i18n.PROMPT_THRESHOLD,
        reply_markup=keyboards.threshold_keyboard(chat_id),
    )


async def _set_threshold(query, ctx: BotContext, chat_id: int, extra: str, _context) -> None:
    try:
        value = int(extra)
    except ValueError:
        return
    await ctx.db.update_group_field(chat_id, "warning_threshold", value)
    await ctx.moderation.invalidate_group_cache(chat_id)
    await _show_group_panel(query, ctx, chat_id, "", _context)


async def _toggle_moderation(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    if not group:
        return
    new_value = 0 if group.get("moderation_enabled") else 1
    await ctx.db.update_group_field(chat_id, "moderation_enabled", new_value)
    await ctx.moderation.invalidate_group_cache(chat_id)
    await _show_group_panel(query, ctx, chat_id, "", _context)


async def _prompt_rules(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "rules", "chat_id": chat_id}
    group = await ctx.db.group_to_dict(chat_id)
    current = (group or {}).get("custom_rules", "")
    preview = current[:500] + ("..." if len(current) > 500 else "")
    await query.edit_message_text(
        i18n.PROMPT_RULES.format(preview=preview or i18n.PROMPT_RULES_NONE),
        reply_markup=keyboards.back_to_group_panel(chat_id),
    )


async def _show_blacklist(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    patterns = await ctx.db.get_blacklist(chat_id)
    lines = [
        i18n.format_blacklist_item(p["pattern"], bool(p.get("is_regex")))
        for p in patterns
    ]
    await query.edit_message_text(
        i18n.format_blacklist_header(lines),
        reply_markup=keyboards.blacklist_keyboard(chat_id),
        parse_mode="Markdown",
    )


async def _prompt_blacklist_keyword(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "bl_keyword", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_BL_KEYWORD,
        reply_markup=keyboards.back_to_group_panel(chat_id),
    )


async def _prompt_blacklist_regex(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "bl_regex", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_BL_REGEX,
        reply_markup=keyboards.back_to_group_panel(chat_id),
    )


async def _prompt_blacklist_remove(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "bl_remove", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_BL_REMOVE,
        reply_markup=keyboards.back_to_group_panel(chat_id),
    )


async def _show_audit(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    logs = await ctx.db.get_audit_logs(chat_id, limit=10)
    if not logs:
        await query.edit_message_text(
            i18n.MSG_AUDIT_EMPTY,
            reply_markup=keyboards.back_to_group_panel(chat_id),
        )
        return

    await query.edit_message_text(
        i18n.format_audit_log(logs)[:4000],
        reply_markup=keyboards.back_to_group_panel(chat_id),
        parse_mode="Markdown",
    )


async def _handle_super_admin(action, query, ctx: BotContext, context, extra: str) -> None:
    if action == "sa_panel":
        await query.edit_message_text(
            i18n.MSG_SUPER_PANEL,
            reply_markup=keyboards.super_admin_panel(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_stats":
        stats = await ctx.db.get_global_stats()
        await query.edit_message_text(
            i18n.format_global_stats(stats),
            reply_markup=keyboards.back_to_super_admin(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_groups":
        groups = await ctx.db.list_all_groups()
        await query.edit_message_text(
            i18n.format_all_groups(groups)[:4000],
            reply_markup=keyboards.back_to_super_admin(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_apikey":
        ctx.pending_inputs[query.from_user.id] = {"type": "sa_apikey"}
        await query.edit_message_text(
            i18n.PROMPT_SA_APIKEY,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return

    if action == "sa_auth":
        ctx.pending_inputs[query.from_user.id] = {"type": "sa_auth"}
        await query.edit_message_text(
            i18n.PROMPT_SA_AUTH,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return

    if action == "sa_ban_group":
        ctx.pending_inputs[query.from_user.id] = {"type": "sa_ban_group"}
        await query.edit_message_text(
            i18n.PROMPT_SA_BAN_GROUP,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return

    if action == "sa_ban_user":
        ctx.pending_inputs[query.from_user.id] = {"type": "sa_ban_user"}
        await query.edit_message_text(
            i18n.PROMPT_SA_BAN_USER,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return

    if action == "sa_audit":
        logs = await ctx.db.get_global_audit_logs(limit=15)
        await query.edit_message_text(
            i18n.format_global_audit(logs)[:4000],
            reply_markup=keyboards.back_to_super_admin(),
            parse_mode="Markdown",
        )
        return

    await query.edit_message_text(
        i18n.MSG_SUPER_PANEL,
        reply_markup=keyboards.super_admin_panel(),
        parse_mode="Markdown",
    )
