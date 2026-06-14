"""Inline keyboard builders for admin panels (Persian UI)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import i18n

PREFIX = "gdoc"


def _cb(action: str, chat_id: int = 0, extra: str = "") -> str:
    if extra:
        return f"{PREFIX}:{action}:{chat_id}:{extra}"
    return f"{PREFIX}:{action}:{chat_id}"


def group_admin_panel(chat_id: int, group: dict) -> InlineKeyboardMarkup:
    enabled = i18n.moderation_status(bool(group.get("moderation_enabled")))
    strictness = i18n.strictness_label(group.get("strictness", "medium"))
    action = group.get("action_mode", "delete_flag")
    action_label = i18n.action_mode_label(action)
    action_btn = action_label if len(action_label) <= 28 else action_label[:25] + "…"
    threshold = group.get("warning_threshold", 3)

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(i18n.BTN_RULES, callback_data=_cb("rules", chat_id))],
            [
                InlineKeyboardButton(
                    f"{i18n.BTN_STRICTNESS}: {strictness}",
                    callback_data=_cb("strictness", chat_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{i18n.BTN_ACTION}: {action_btn}",
                    callback_data=_cb("action", chat_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{i18n.BTN_THRESHOLD}: {threshold}",
                    callback_data=_cb("threshold", chat_id),
                ),
            ],
            [
                InlineKeyboardButton(
                    f"{i18n.BTN_MODERATION} {enabled}",
                    callback_data=_cb("toggle", chat_id),
                ),
            ],
            [InlineKeyboardButton(i18n.BTN_BLACKLIST, callback_data=_cb("blacklist", chat_id))],
            [InlineKeyboardButton(i18n.BTN_AUDIT, callback_data=_cb("audit", chat_id))],
            [InlineKeyboardButton(i18n.BTN_STATS, callback_data=_cb("stats", chat_id))],
            [InlineKeyboardButton(i18n.BTN_REFRESH, callback_data=_cb("panel", chat_id))],
        ],
    )


def strictness_keyboard(chat_id: int, current: str) -> InlineKeyboardMarkup:
    rows = []
    for level in ("low", "medium", "high"):
        mark = "✓ " if level == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark}{i18n.strictness_label(level)}",
                    callback_data=_cb("set_strictness", chat_id, level),
                ),
            ],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))])
    return InlineKeyboardMarkup(rows)


def action_mode_keyboard(chat_id: int, current: str) -> InlineKeyboardMarkup:
    rows = []
    for mode in ("delete_flag", "keep_alert"):
        mark = "✓ " if mode == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark}{i18n.action_mode_label(mode)}",
                    callback_data=_cb("set_action", chat_id, mode),
                ),
            ],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))])
    return InlineKeyboardMarkup(rows)


def threshold_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(str(n), callback_data=_cb("set_threshold", chat_id, str(n)))]
        for n in (1, 2, 3, 5, 10)
    ]
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))])
    return InlineKeyboardMarkup(rows)


def blacklist_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(i18n.BTN_BL_ADD_KW, callback_data=_cb("bl_add_kw", chat_id))],
            [InlineKeyboardButton(i18n.BTN_BL_ADD_RX, callback_data=_cb("bl_add_rx", chat_id))],
            [InlineKeyboardButton(i18n.BTN_BL_REMOVE, callback_data=_cb("bl_remove", chat_id))],
            [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))],
        ],
    )


def super_admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(i18n.BTN_SA_AI, callback_data=_cb("sa_ai"))],
            [InlineKeyboardButton(i18n.BTN_SA_WEBHOOK, callback_data=_cb("sa_webhook"))],
            [InlineKeyboardButton(i18n.BTN_SA_STATS, callback_data=_cb("sa_stats"))],
            [InlineKeyboardButton(i18n.BTN_SA_GROUPS, callback_data=_cb("sa_groups"))],
            [InlineKeyboardButton(i18n.BTN_SA_ADMINS, callback_data=_cb("sa_admins"))],
            [InlineKeyboardButton(i18n.BTN_SA_AUTH, callback_data=_cb("sa_auth"))],
            [InlineKeyboardButton(i18n.BTN_SA_BAN_GROUP, callback_data=_cb("sa_ban_group"))],
            [InlineKeyboardButton(i18n.BTN_SA_BAN_USER, callback_data=_cb("sa_ban_user"))],
            [InlineKeyboardButton(i18n.BTN_SA_AUDIT, callback_data=_cb("sa_audit"))],
        ],
    )


def ai_settings_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(i18n.BTN_SA_PROVIDER, callback_data=_cb("sa_provider"))],
            [InlineKeyboardButton(i18n.BTN_SA_BASEURL, callback_data=_cb("sa_baseurl"))],
            [InlineKeyboardButton(i18n.BTN_SA_APIKEY, callback_data=_cb("sa_apikey"))],
            [InlineKeyboardButton(i18n.BTN_SA_MODEL, callback_data=_cb("sa_model"))],
            [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_panel"))],
        ],
    )


def provider_keyboard(current: str) -> InlineKeyboardMarkup:
    providers = [
        ("openai", i18n.PROVIDER_OPENAI),
        ("gemini", i18n.PROVIDER_GEMINI),
        ("openai_compat", i18n.PROVIDER_COMPAT),
    ]
    rows = []
    for key, label in providers:
        mark = "✓ " if key == current else ""
        rows.append(
            [InlineKeyboardButton(f"{mark}{label}", callback_data=_cb("sa_set_provider", 0, key))],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_ai"))])
    return InlineKeyboardMarkup(rows)


def model_keyboard(models: list[str], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    start = page * page_size
    end = start + page_size
    page_models = models[start:end]
    rows = []
    for idx, model in enumerate(page_models):
        global_idx = start + idx
        label = model if len(model) <= 40 else model[:37] + "…"
        rows.append(
            [InlineKeyboardButton(label, callback_data=_cb("sa_set_model", 0, str(global_idx)))],
        )
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=_cb("sa_model_page", 0, str(page - 1))))
    if end < len(models):
        nav.append(InlineKeyboardButton("▶️", callback_data=_cb("sa_model_page", 0, str(page + 1))))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_ai"))])
    return InlineKeyboardMarkup(rows)


def webhook_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(i18n.BTN_WH_POLLING, callback_data=_cb("sa_wh_polling"))],
            [InlineKeyboardButton(i18n.BTN_WH_MANUAL, callback_data=_cb("sa_wh_manual"))],
            [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_panel"))],
        ],
    )


def admin_management_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(i18n.BTN_SA_RENEW, callback_data=_cb("sa_renew"))],
            [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_panel"))],
        ],
    )


def back_to_ai_settings() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_ai"))]],
    )


def back_to_super_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_panel"))]],
    )


def back_to_group_panel(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))]],
    )


def parse_callback(data: str) -> tuple[str, int, str]:
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != PREFIX:
        return "", 0, ""
    action = parts[1]
    chat_id = int(parts[2]) if len(parts) > 2 and parts[2].lstrip("-").isdigit() else 0
    extra = parts[3] if len(parts) > 3 else ""
    if len(parts) > 3 and not parts[2].lstrip("-").isdigit():
        extra = ":".join(parts[2:])
        chat_id = 0
    return action, chat_id, extra
