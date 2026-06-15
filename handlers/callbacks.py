"""Inline callback query handlers for admin panels."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import i18n
import keyboards
from config import Config
from context import BotContext
from rule_templates import (
    BAN_TEMPLATES,
    SUSPECT_TEMPLATES,
    get_template,
    parse_enabled_templates,
    serialize_enabled_templates,
)
from handlers.admin_utils import can_manage_group_fast, has_admin_access, is_telegram_group_admin
from handlers.moderation_actions import (
    ban_user_in_chat,
    increment_warning_cached,
    reset_warnings_cached,
    restore_message_from_audit,
    safe_delete_message,
    unban_user_in_chat,
)
from handlers.group_notifications import notify_group_ban, notify_group_warning
from webhook_manager import (
    normalize_webhook_url,
    update_env_file,
    validate_webhook_url,
)

logger = logging.getLogger(__name__)


async def _safe_edit(query, text: str, **kwargs) -> None:
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("Could not edit callback message: %s", exc)


async def _is_sa_remote(query, ctx: BotContext, user_id: int) -> bool:
    """Super-admin managing a group from private chat."""
    if not query.message or not query.message.chat:
        return False
    from telegram.constants import ChatType

    return (
        query.message.chat.type == ChatType.PRIVATE
        and await ctx.db.is_super_admin(user_id)
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return

    await query.answer()
    action, chat_id, extra = keyboards.parse_callback(query.data)
    ctx: BotContext = context.bot_data["ctx"]
    user_id = update.effective_user.id

    if action in ("mod_forgive", "mod_ban", "mod_unban", "mod_restore"):
        await _handle_mod_action(action, query, ctx, chat_id, extra, context)
        return

    if action in ("review_harm", "review_safe", "review_del"):
        await _handle_review_action(action, query, ctx, chat_id, extra, context)
        return

    if action.startswith("sa_"):
        if not await ctx.db.is_super_admin(user_id):
            await query.edit_message_text(i18n.MSG_ACCESS_DENIED)
            return
        await _handle_super_admin(action, query, ctx, context, extra)
        return

    is_sa_remote = await _is_sa_remote(query, ctx, user_id)

    if chat_id and not is_sa_remote and not await can_manage_group_fast(
        context.bot, chat_id, user_id, ctx.db,
    ):
        await query.edit_message_text(i18n.MSG_NOT_GROUP_ADMIN)
        return

    if chat_id and not is_sa_remote and not await has_admin_access(ctx.db, user_id):
        await query.edit_message_text(i18n.MSG_SUBSCRIPTION_EXPIRED, parse_mode="Markdown")
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
        "rules": _show_rules_menu,
        "rules_ban": _prompt_ban_rules,
        "rules_suspect": _prompt_suspect_rules,
        "templates": _show_templates_menu,
        "tmpl_ban": _show_ban_templates,
        "tmpl_suspect": _show_suspect_templates,
        "tmpl_toggle": _toggle_template,
        "blacklist": _show_blacklist,
        "bl_add_kw": _prompt_blacklist_keyword,
        "bl_add_rx": _prompt_blacklist_regex,
        "bl_remove": _prompt_blacklist_remove,
        "links": _show_links,
        "links_policy": _show_links_policy,
        "set_link_policy": _set_link_policy,
        "links_add": _prompt_link_add,
        "links_remove": _prompt_link_remove,
        "audit": _show_audit,
        "stats": _show_group_stats,
        "banned": _show_banned_users,
        "banned_page": _show_banned_users,
        "panel_unban": _panel_unban_user,
    }

    handler = handlers.get(action)
    if handler:
        await handler(query, ctx, chat_id, extra, context)


async def _back_kb(chat_id: int, query, ctx: BotContext):
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    return keyboards.back_to_group_panel(chat_id, from_sa=from_sa)


def _parse_user_extra(extra: str) -> tuple[int, int]:
    """Parse extra as user_id or user_id:audit_id."""
    if ":" in extra:
        parts = extra.split(":", 1)
        return int(parts[0]), int(parts[1])
    return int(extra), 0


async def _handle_mod_action(
    action: str,
    query,
    ctx: BotContext,
    chat_id: int,
    extra: str,
    context,
) -> None:
    if not chat_id or not extra:
        return

    try:
        target_user_id, audit_id = _parse_user_extra(extra)
    except ValueError:
        return

    admin_id = query.from_user.id
    if not await is_telegram_group_admin(context.bot, chat_id, admin_id, ctx.db):
        try:
            await query.message.reply_text(i18n.MSG_MOD_NOT_GROUP_ADMIN)
        except BadRequest:
            pass
        return

    if action == "mod_forgive":
        # Forgiving must also lift any active Telegram ban so the user can rejoin,
        # not only clear the warning/ban flags in the database.
        await unban_user_in_chat(context, chat_id, target_user_id, ctx=ctx)
        await reset_warnings_cached(ctx, chat_id, target_user_id)
        result = i18n.MSG_MOD_FORGIVEN.format(user=f"کاربر {target_user_id}")
    elif action == "mod_ban":
        await ban_user_in_chat(
            context, chat_id, target_user_id, "Banned by group admin", ctx=ctx,
        )
        result = i18n.MSG_MOD_BANNED.format(user=f"کاربر {target_user_id}")
    elif action == "mod_unban":
        ok = await unban_user_in_chat(context, chat_id, target_user_id, ctx=ctx)
        if ok:
            await reset_warnings_cached(ctx, chat_id, target_user_id)
            result = i18n.MSG_MOD_UNBANNED.format(user=f"کاربر {target_user_id}")
        else:
            result = i18n.MSG_MOD_ALREADY_DONE
    elif action == "mod_restore":
        audit = await ctx.db.get_audit_log(audit_id) if audit_id else None
        if not audit:
            result = i18n.MSG_MOD_ALREADY_DONE
        else:
            user_label = audit.get("username") or str(target_user_id)
            restored = await restore_message_from_audit(
                context, chat_id, audit.get("message_text", ""), user_label,
            )
            result = (
                i18n.MSG_MOD_RESTORED.format(user=user_label)
                if restored
                else i18n.MSG_MOD_ALREADY_DONE
            )
    else:
        return

    try:
        await query.edit_message_text(
            f"{query.message.text}\n\n{result}",
            reply_markup=None,
        )
    except BadRequest:
        await query.message.reply_text(result)


async def _handle_review_action(
    action: str,
    query,
    ctx: BotContext,
    chat_id: int,
    extra: str,
    context,
) -> None:
    if not chat_id or not extra:
        return

    try:
        audit_id = int(extra)
    except ValueError:
        return

    admin_id = query.from_user.id
    if not await is_telegram_group_admin(context.bot, chat_id, admin_id, ctx.db):
        try:
            await query.message.reply_text(i18n.MSG_MOD_NOT_GROUP_ADMIN)
        except BadRequest:
            pass
        return

    audit = await ctx.db.get_audit_log(audit_id)
    if not audit:
        await query.edit_message_text(i18n.MSG_MOD_ALREADY_DONE, reply_markup=None)
        return

    if audit.get("review_status") in ("approved", "dismissed", "deleted"):
        await query.edit_message_text(
            f"{query.message.text}\n\n{i18n.MSG_MOD_REVIEW_DONE}",
            reply_markup=None,
        )
        return

    target_user_id = audit["user_id"]
    reason = audit.get("reason") or "تخلف"
    group = await ctx.db.group_to_dict(chat_id)
    threshold = (group or {}).get("warning_threshold", 3)

    if action == "review_safe":
        await ctx.db.update_audit_review_status(audit_id, "dismissed")
        result = i18n.MSG_MOD_REVIEW_SAFE
    elif action == "review_del":
        msg_id = audit.get("message_id")
        if msg_id:
            await safe_delete_message(context, chat_id, msg_id)
        await ctx.db.update_audit_review_status(audit_id, "deleted")
        result = "🗑 پیام در گروه حذف شد."
    elif action == "review_harm":
        count, auto_banned = await increment_warning_cached(ctx, chat_id, target_user_id)
        await ctx.db.update_audit_review_status(audit_id, "approved")
        msg_id = audit.get("message_id")
        if msg_id:
            await safe_delete_message(context, chat_id, msg_id)
        user_stub = type("U", (), {
            "id": target_user_id,
            "full_name": audit.get("username") or str(target_user_id),
            "username": audit.get("username"),
        })()
        if auto_banned:
            await ban_user_in_chat(
                context, chat_id, target_user_id, reason, ctx=ctx,
            )
            reasons = await ctx.db.get_user_violation_reasons(chat_id, target_user_id)
            await notify_group_ban(context, chat_id, user_stub, count, reasons)
            result = i18n.MSG_MODCMD_WARN_BAN.format(
                user=user_stub.full_name, count=count,
            )
        else:
            await notify_group_warning(
                context,
                chat_id,
                user_stub,
                reason,
                count,
                threshold,
                deleted=bool(msg_id),
                audit_id=audit_id,
            )
            result = i18n.MSG_MOD_REVIEW_HARM
    else:
        return

    try:
        await query.edit_message_text(
            f"{query.message.text}\n\n{result}",
            reply_markup=None,
        )
    except BadRequest:
        await query.message.reply_text(result)


async def _show_banned_users(query, ctx: BotContext, chat_id: int, extra: str, _context) -> None:
    page_size = 8
    try:
        page = int(extra) if extra else 0
    except ValueError:
        page = 0
    total = await ctx.db.count_group_banned_users(chat_id)
    banned = await ctx.db.list_group_banned_users(chat_id, limit=page_size, offset=page * page_size)
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    await _safe_edit(
        query,
        i18n.format_banned_users_list(banned, total=total, page=page, page_size=page_size),
        reply_markup=keyboards.banned_users_keyboard(
            chat_id, banned, page=page, page_size=page_size, total=total, from_sa=from_sa,
        ),
        parse_mode="Markdown",
    )


async def _panel_unban_user(query, ctx: BotContext, chat_id: int, extra: str, context) -> None:
    if not extra:
        return
    try:
        target_user_id = int(extra)
    except ValueError:
        return

    admin_id = query.from_user.id
    is_sa_remote = await _is_sa_remote(query, ctx, admin_id)
    if not is_sa_remote and not await can_manage_group_fast(
        context.bot, chat_id, admin_id, ctx.db,
    ):
        await query.edit_message_text(i18n.MSG_NOT_GROUP_ADMIN)
        return

    ok = await unban_user_in_chat(context, chat_id, target_user_id, ctx=ctx)
    if ok:
        await reset_warnings_cached(ctx, chat_id, target_user_id)
        result = i18n.MSG_MOD_UNBANNED.format(user=f"کاربر {target_user_id}")
    else:
        result = i18n.MSG_MOD_ALREADY_DONE

    page = 0
    page_size = 8
    total = await ctx.db.count_group_banned_users(chat_id)
    banned = await ctx.db.list_group_banned_users(chat_id, limit=page_size, offset=0)
    from_sa = await _is_sa_remote(query, ctx, admin_id)
    await _safe_edit(
        query,
        f"{i18n.format_banned_users_list(banned, total=total, page=page, page_size=page_size)}\n\n{result}",
        reply_markup=keyboards.banned_users_keyboard(
            chat_id, banned, page=page, page_size=page_size, total=total, from_sa=from_sa,
        ),
        parse_mode="Markdown",
    )


async def _show_group_panel(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    if not group:
        await query.edit_message_text(i18n.MSG_GROUP_NOT_FOUND)
        return
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    await _safe_edit(
        query,
        i18n.format_group_panel_header(group),
        reply_markup=keyboards.group_admin_panel(chat_id, group, from_sa=from_sa),
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
    current = group.get("action_mode", "keep_alert") if group else "keep_alert"
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


async def _show_rules_menu(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    await query.edit_message_text(
        i18n.PROMPT_RULES,
        reply_markup=await _rules_menu_kb(chat_id, query, ctx),
        parse_mode="Markdown",
    )


async def _rules_menu_kb(chat_id: int, query, ctx: BotContext):
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    return keyboards.rules_menu_keyboard(chat_id, from_sa=from_sa)


async def _prompt_ban_rules(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "rules_ban", "chat_id": chat_id}
    group = await ctx.db.group_to_dict(chat_id)
    current = (group or {}).get("custom_rules", "")
    preview = current[:500] + ("..." if len(current) > 500 else "")
    await query.edit_message_text(
        i18n.PROMPT_RULES_BAN.format(preview=preview or i18n.PROMPT_RULES_NONE),
        reply_markup=await _back_kb(chat_id, query, ctx),
    )


async def _prompt_suspect_rules(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "rules_suspect", "chat_id": chat_id}
    group = await ctx.db.group_to_dict(chat_id)
    current = (group or {}).get("suspect_rules", "")
    preview = current[:500] + ("..." if len(current) > 500 else "")
    await query.edit_message_text(
        i18n.PROMPT_RULES_SUSPECT.format(preview=preview or i18n.PROMPT_RULES_NONE),
        reply_markup=await _back_kb(chat_id, query, ctx),
    )


async def _show_templates_menu(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    await query.edit_message_text(
        i18n.PROMPT_TEMPLATES,
        reply_markup=keyboards.templates_menu_keyboard(chat_id, from_sa=from_sa),
        parse_mode="Markdown",
    )


async def _show_ban_templates(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    enabled = parse_enabled_templates((group or {}).get("enabled_templates"))
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    await query.edit_message_text(
        i18n.PROMPT_TEMPLATES_BAN,
        reply_markup=keyboards.template_list_keyboard(
            chat_id, BAN_TEMPLATES, enabled, from_sa=from_sa,
        ),
        parse_mode="Markdown",
    )


async def _show_suspect_templates(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    enabled = parse_enabled_templates((group or {}).get("enabled_templates"))
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    await query.edit_message_text(
        i18n.PROMPT_TEMPLATES_SUSPECT,
        reply_markup=keyboards.template_list_keyboard(
            chat_id, SUSPECT_TEMPLATES, enabled, from_sa=from_sa,
        ),
        parse_mode="Markdown",
    )


async def _toggle_template(query, ctx: BotContext, chat_id: int, extra: str, _context) -> None:
    if not extra:
        return
    tmpl = get_template(extra)
    if not tmpl:
        return

    group = await ctx.db.group_to_dict(chat_id)
    enabled = parse_enabled_templates((group or {}).get("enabled_templates"))
    enabled[extra] = not enabled.get(extra, False)
    await ctx.db.update_group_field(chat_id, "enabled_templates", serialize_enabled_templates(enabled))
    await ctx.moderation.invalidate_group_cache(chat_id)

    status = "فعال" if enabled[extra] else "غیرفعال"
    templates = BAN_TEMPLATES if tmpl.kind == "ban" else SUSPECT_TEMPLATES
    from_sa = await _is_sa_remote(query, ctx, query.from_user.id)
    header = i18n.PROMPT_TEMPLATES_BAN if tmpl.kind == "ban" else i18n.PROMPT_TEMPLATES_SUSPECT
    await _safe_edit(
        query,
        f"{header}\n\n{i18n.MSG_TEMPLATE_TOGGLED.format(label=tmpl.label, status=status)}",
        reply_markup=keyboards.template_list_keyboard(
            chat_id, templates, enabled, from_sa=from_sa,
        ),
        parse_mode="Markdown",
    )


async def _prompt_rules(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    await _show_rules_menu(query, ctx, chat_id, _extra, _context)


async def _prompt_blacklist_keyword(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "bl_keyword", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_BL_KEYWORD,
        reply_markup=await _back_kb(chat_id, query, ctx),
    )


async def _prompt_blacklist_regex(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "bl_regex", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_BL_REGEX,
        reply_markup=await _back_kb(chat_id, query, ctx),
    )


async def _prompt_blacklist_remove(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "bl_remove", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_BL_REMOVE,
        reply_markup=await _back_kb(chat_id, query, ctx),
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


async def _show_links(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    policy = (group or {}).get("link_policy", "allow_all")
    domains = await ctx.db.get_link_domains(chat_id)
    await query.edit_message_text(
        i18n.format_links_header(policy, domains),
        reply_markup=keyboards.links_manage_keyboard(chat_id, policy),
        parse_mode="Markdown",
    )


async def _show_links_policy(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    current = (group or {}).get("link_policy", "allow_all")
    await query.edit_message_text(
        i18n.PROMPT_LINKS,
        reply_markup=keyboards.links_policy_keyboard(chat_id, current),
    )


async def _set_link_policy(query, ctx: BotContext, chat_id: int, extra: str, _context) -> None:
    from link_filter import LINK_POLICIES

    if extra not in LINK_POLICIES:
        return
    await ctx.db.update_group_field(chat_id, "link_policy", extra)
    await ctx.moderation.invalidate_group_cache(chat_id)
    await _show_links(query, ctx, chat_id, "", _context)


async def _prompt_link_add(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "links_add", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_LINK_ADD,
        reply_markup=await _back_kb(chat_id, query, ctx),
        parse_mode="Markdown",
    )


async def _prompt_link_remove(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    ctx.pending_inputs[query.from_user.id] = {"type": "links_remove", "chat_id": chat_id}
    await query.edit_message_text(
        i18n.PROMPT_LINK_REMOVE,
        reply_markup=await _back_kb(chat_id, query, ctx),
    )


async def _show_audit(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    logs = await ctx.db.get_audit_logs(chat_id, limit=10)
    back = await _back_kb(chat_id, query, ctx)
    if not logs:
        await _safe_edit(
            query,
            i18n.MSG_AUDIT_EMPTY,
            reply_markup=back,
        )
        return

    await _safe_edit(
        query,
        i18n.format_audit_log(logs)[:4000],
        reply_markup=back,
        parse_mode="Markdown",
    )


async def _show_group_stats(query, ctx: BotContext, chat_id: int, _extra: str, _context) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    if not group:
        await query.edit_message_text(i18n.MSG_GROUP_NOT_FOUND)
        return
    stats = await ctx.db.get_group_message_stats(chat_id)
    await _safe_edit(
        query,
        i18n.format_group_message_stats(group, stats),
        reply_markup=await _back_kb(chat_id, query, ctx),
        parse_mode="Markdown",
    )


async def _handle_super_admin(action, query, ctx: BotContext, context, extra: str) -> None:
    user_id = query.from_user.id

    if action == "sa_panel":
        await query.edit_message_text(
            i18n.MSG_SUPER_PANEL,
            reply_markup=keyboards.super_admin_panel(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_ai":
        settings = await ctx.db.get_ai_settings()
        configured = await ctx.db.is_ai_configured()
        await query.edit_message_text(
            i18n.format_ai_settings(settings, configured),
            reply_markup=keyboards.ai_settings_panel(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_provider":
        current = await ctx.db.get_ai_provider()
        await query.edit_message_text(
            "پرووایدر AI را انتخاب کنید:",
            reply_markup=keyboards.provider_keyboard(current),
        )
        return

    if action == "sa_set_provider":
        if extra not in ("openai", "gemini", "openai_compat"):
            return
        await ctx.db.set_ai_provider(extra)
        default_url = ctx.ai.get_default_base_url(extra)
        if extra != "openai_compat":
            await ctx.db.set_ai_base_url(default_url)
        await ctx.refresh_ai_config()
        await query.edit_message_text(
            i18n.MSG_PROVIDER_UPDATED.format(provider=i18n.provider_label(extra)),
            reply_markup=keyboards.back_to_ai_settings(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_baseurl":
        ctx.pending_inputs[user_id] = {"type": "sa_baseurl"}
        current = await ctx.db.get_ai_base_url()
        preview = current or ctx.ai.get_default_base_url(await ctx.db.get_ai_provider())
        await query.edit_message_text(
            i18n.PROMPT_SA_BASEURL + f"\n\nفعلی: `{preview}`",
            reply_markup=keyboards.back_to_ai_settings(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_model":
        await ctx.refresh_ai_config()
        models, error = await ctx.ai.list_models()
        if error:
            await query.edit_message_text(
                i18n.MSG_MODEL_LIST_ERROR.format(error=error),
                reply_markup=keyboards.back_to_ai_settings(),
            )
            return
        if not models:
            await query.edit_message_text(
                i18n.MSG_MODEL_LIST_EMPTY,
                reply_markup=keyboards.back_to_ai_settings(),
            )
            return
        ctx.model_cache[user_id] = models
        current = await ctx.db.get_ai_model()
        header = f"مدل AI را انتخاب کنید ({len(models)} مدل):\nفعلی: `{current}`"
        await query.edit_message_text(
            header,
            reply_markup=keyboards.model_keyboard(models, page=0),
            parse_mode="Markdown",
        )
        return

    if action == "sa_model_page":
        models = ctx.model_cache.get(user_id, [])
        if not models:
            await query.edit_message_text(
                i18n.MSG_MODEL_LIST_EMPTY,
                reply_markup=keyboards.back_to_ai_settings(),
            )
            return
        try:
            page = int(extra)
        except ValueError:
            page = 0
        current = await ctx.db.get_ai_model()
        await query.edit_message_text(
            f"مدل AI را انتخاب کنید ({len(models)} مدل):\nفعلی: `{current}`",
            reply_markup=keyboards.model_keyboard(models, page=page),
            parse_mode="Markdown",
        )
        return

    if action == "sa_set_model":
        models = ctx.model_cache.get(user_id, [])
        try:
            idx = int(extra)
            model = models[idx]
        except (ValueError, IndexError):
            return
        await ctx.db.set_ai_model(model)
        await ctx.refresh_ai_config()
        await query.edit_message_text(
            i18n.MSG_MODEL_UPDATED.format(model=model),
            reply_markup=keyboards.back_to_ai_settings(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_webhook":
        settings = await ctx.db.get_webhook_settings()
        await query.edit_message_text(
            i18n.format_webhook_settings(settings),
            reply_markup=keyboards.webhook_panel(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_wh_polling":
        await ctx.db.set_use_webhook(False)
        await ctx.db.set_webhook_url("")
        update_env_file(Config.ENV_FILE, {"USE_WEBHOOK": "false", "WEBHOOK_URL": ""})
        await query.edit_message_text(
            i18n.MSG_WEBHOOK_POLLING,
            reply_markup=keyboards.back_to_super_admin(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_wh_manual":
        ctx.pending_inputs[user_id] = {"type": "sa_webhook_url"}
        await query.edit_message_text(
            i18n.PROMPT_SA_WEBHOOK_URL,
            reply_markup=keyboards.back_to_super_admin(),
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

    if action == "sa_groups" or action == "sa_grps":
        await _show_sa_groups_picker(query, ctx, extra)
        return

    if action == "sa_grp":
        if not chat_id:
            return
        await _show_sa_group_panel(query, ctx, chat_id)
        return

    if action == "sa_apikey":
        ctx.pending_inputs[query.from_user.id] = {"type": "sa_apikey"}
        await query.edit_message_text(
            i18n.PROMPT_SA_APIKEY,
            reply_markup=keyboards.back_to_ai_settings(),
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

    if action == "sa_banned":
        users = await ctx.db.list_globally_banned_users()
        await _safe_edit(
            query,
            i18n.format_global_banned_users(users),
            reply_markup=keyboards.global_banned_keyboard(users),
            parse_mode="Markdown",
        )
        return

    if action == "sa_unban_user":
        if not extra:
            return
        try:
            target_id = int(extra)
        except ValueError:
            return
        await ctx.db.set_global_ban(target_id, False)
        users = await ctx.db.list_globally_banned_users()
        await _safe_edit(
            query,
            f"{i18n.MSG_USER_UNBANNED.format(user_id=target_id)}\n\n"
            f"{i18n.format_global_banned_users(users)}",
            reply_markup=keyboards.global_banned_keyboard(users),
            parse_mode="Markdown",
        )
        return

    if action == "sa_audit":
        logs = await ctx.db.get_global_audit_logs(limit=15)
        await _safe_edit(
            query,
            i18n.format_global_audit(logs)[:4000],
            reply_markup=keyboards.back_to_super_admin(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_admins":
        admins = await ctx.db.list_registered_admins()
        await query.edit_message_text(
            i18n.format_registered_admins(admins)[:4000],
            reply_markup=keyboards.admin_management_panel(),
            parse_mode="Markdown",
        )
        return

    if action == "sa_renew":
        ctx.pending_inputs[user_id] = {"type": "sa_renew"}
        await query.edit_message_text(
            i18n.PROMPT_SA_RENEW,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return

    await query.edit_message_text(
        i18n.MSG_SUPER_PANEL,
        reply_markup=keyboards.super_admin_panel(),
        parse_mode="Markdown",
    )


async def _show_sa_groups_picker(query, ctx: BotContext, extra: str) -> None:
    groups = await ctx.db.list_all_groups()
    if not groups:
        await query.edit_message_text(
            i18n.MSG_SA_NO_GROUPS,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return
    try:
        page = int(extra) if extra else 0
    except ValueError:
        page = 0
    await query.edit_message_text(
        i18n.MSG_SA_SELECT_GROUP,
        reply_markup=keyboards.sa_groups_picker(groups, page=page),
        parse_mode="Markdown",
    )


async def _show_sa_group_panel(query, ctx: BotContext, chat_id: int) -> None:
    group = await ctx.db.group_to_dict(chat_id)
    if not group:
        await query.edit_message_text(
            i18n.MSG_GROUP_NOT_FOUND,
            reply_markup=keyboards.back_to_super_admin(),
        )
        return
    await _safe_edit(
        query,
        i18n.format_group_panel_header(group),
        reply_markup=keyboards.group_admin_panel(chat_id, group, from_sa=True),
        parse_mode="Markdown",
    )
