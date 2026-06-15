"""Inline keyboard builders for admin panels (Persian UI)."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import i18n

PREFIX = "gdoc"


def _cb(action: str, chat_id: int = 0, extra: str = "") -> str:
    if extra:
        return f"{PREFIX}:{action}:{chat_id}:{extra}"
    return f"{PREFIX}:{action}:{chat_id}"


def group_admin_panel(chat_id: int, group: dict, *, from_sa: bool = False) -> InlineKeyboardMarkup:
    enabled = i18n.moderation_status(bool(group.get("moderation_enabled")))
    ai_status = i18n.moderation_status(bool(group.get("ai_enabled", True)))
    strictness = i18n.strictness_label(group.get("strictness", "medium"))
    action = group.get("action_mode", "keep_alert")
    action_label = i18n.action_mode_label(action)
    action_btn = action_label if len(action_label) <= 28 else action_label[:25] + "…"
    threshold = group.get("warning_threshold", 3)

    rows = [
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
        [
            InlineKeyboardButton(
                f"{i18n.BTN_AI} {ai_status}",
                callback_data=_cb("toggle_ai", chat_id),
            ),
        ],
        [InlineKeyboardButton(i18n.BTN_BLACKLIST, callback_data=_cb("blacklist", chat_id))],
        [InlineKeyboardButton(i18n.BTN_LINKS, callback_data=_cb("links", chat_id))],
        [InlineKeyboardButton(i18n.BTN_BANNED, callback_data=_cb("banned", chat_id))],
        [InlineKeyboardButton(i18n.BTN_AUDIT, callback_data=_cb("audit", chat_id))],
        [InlineKeyboardButton(i18n.BTN_STATS, callback_data=_cb("stats", chat_id))],
        [InlineKeyboardButton(i18n.BTN_REFRESH, callback_data=_cb("panel", chat_id))],
    ]
    if from_sa:
        rows.append(
            [InlineKeyboardButton(i18n.BTN_SA_GROUPS_BACK, callback_data=_cb("sa_grps", 0, "0"))],
        )
    return InlineKeyboardMarkup(rows)


def rules_menu_keyboard(chat_id: int, *, from_sa: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(i18n.BTN_RULES_TEMPLATES, callback_data=_cb("templates", chat_id))],
        [InlineKeyboardButton(i18n.BTN_RULES_BAN, callback_data=_cb("rules_ban", chat_id))],
        [InlineKeyboardButton(i18n.BTN_RULES_SUSPECT, callback_data=_cb("rules_suspect", chat_id))],
        [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))],
    ]
    if from_sa:
        rows.append(
            [InlineKeyboardButton(i18n.BTN_SA_GROUPS_BACK, callback_data=_cb("sa_grps", 0, "0"))],
        )
    return InlineKeyboardMarkup(rows)


def templates_menu_keyboard(chat_id: int, *, from_sa: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(i18n.BTN_TEMPLATES_BAN, callback_data=_cb("tmpl_ban", chat_id))],
        [InlineKeyboardButton(i18n.BTN_TEMPLATES_SUSPECT, callback_data=_cb("tmpl_suspect", chat_id))],
        [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("rules", chat_id))],
    ]
    if from_sa:
        rows.append(
            [InlineKeyboardButton(i18n.BTN_SA_GROUPS_BACK, callback_data=_cb("sa_grps", 0, "0"))],
        )
    return InlineKeyboardMarkup(rows)


def template_list_keyboard(
    chat_id: int,
    templates: list,
    enabled: dict[str, bool],
    *,
    from_sa: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    for tmpl in templates:
        is_on = enabled.get(tmpl.id, False)
        mark = "✅" if is_on else "⬜"
        label = f"{mark} {tmpl.label}"
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=_cb("tmpl_toggle", chat_id, tmpl.id),
                ),
            ],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("templates", chat_id))])
    if from_sa:
        rows.append(
            [InlineKeyboardButton(i18n.BTN_SA_GROUPS_BACK, callback_data=_cb("sa_grps", 0, "0"))],
        )
    return InlineKeyboardMarkup(rows)


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


def links_policy_keyboard(chat_id: int, current: str) -> InlineKeyboardMarkup:
    from link_filter import LINK_POLICIES

    rows = []
    for policy in LINK_POLICIES:
        mark = "✓ " if policy == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{mark}{i18n.link_policy_label(policy)}",
                    callback_data=_cb("set_link_policy", chat_id, policy),
                ),
            ],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))])
    return InlineKeyboardMarkup(rows)


def links_manage_keyboard(chat_id: int, policy: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(i18n.BTN_LINK_POLICY, callback_data=_cb("links_policy", chat_id))],
    ]
    if policy in ("blocklist", "allowlist"):
        rows.extend(
            [
                [InlineKeyboardButton(i18n.BTN_LINK_ADD, callback_data=_cb("links_add", chat_id))],
                [InlineKeyboardButton(i18n.BTN_LINK_REMOVE, callback_data=_cb("links_remove", chat_id))],
            ],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))])
    return InlineKeyboardMarkup(rows)


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
            [InlineKeyboardButton(i18n.BTN_SA_BANNED, callback_data=_cb("sa_banned"))],
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


def back_to_group_panel(chat_id: int, *, from_sa: bool = False) -> InlineKeyboardMarkup:
    if from_sa:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_grp", chat_id))],
                [InlineKeyboardButton(i18n.BTN_SA_GROUPS_BACK, callback_data=_cb("sa_grps", 0, "0"))],
            ],
        )
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("panel", chat_id))]],
    )


def warning_action_keyboard(chat_id: int, user_id: int, audit_id: int = 0) -> InlineKeyboardMarkup:
    extra = str(user_id) if not audit_id else f"{user_id}:{audit_id}"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    i18n.BTN_MOD_FORGIVE,
                    callback_data=_cb("mod_forgive", chat_id, extra),
                ),
                InlineKeyboardButton(
                    i18n.BTN_MOD_BAN,
                    callback_data=_cb("mod_ban", chat_id, str(user_id)),
                ),
            ],
            [
                InlineKeyboardButton(
                    i18n.BTN_MOD_RESTORE,
                    callback_data=_cb("mod_restore", chat_id, extra),
                ),
            ],
        ],
    )


def ban_notice_keyboard(chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    i18n.BTN_MOD_UNBAN,
                    callback_data=_cb("mod_unban", chat_id, str(user_id)),
                ),
                InlineKeyboardButton(
                    i18n.BTN_MOD_FORGIVE,
                    callback_data=_cb("mod_forgive", chat_id, str(user_id)),
                ),
            ],
        ],
    )


def delete_notice_keyboard(chat_id: int, user_id: int, audit_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    i18n.BTN_MOD_RESTORE,
                    callback_data=_cb("mod_restore", chat_id, f"{user_id}:{audit_id}"),
                ),
                InlineKeyboardButton(
                    i18n.BTN_MOD_FORGIVE,
                    callback_data=_cb("mod_forgive", chat_id, str(user_id)),
                ),
            ],
        ],
    )


def admin_review_keyboard(chat_id: int, audit_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    i18n.BTN_REVIEW_HARM,
                    callback_data=_cb("review_harm", chat_id, str(audit_id)),
                ),
            ],
            [
                InlineKeyboardButton(
                    i18n.BTN_REVIEW_SAFE,
                    callback_data=_cb("review_safe", chat_id, str(audit_id)),
                ),
            ],
            [
                InlineKeyboardButton(
                    i18n.BTN_REVIEW_DELETE,
                    callback_data=_cb("review_del", chat_id, str(audit_id)),
                ),
            ],
        ],
    )


def banned_users_keyboard(
    chat_id: int,
    banned: list[dict],
    *,
    page: int = 0,
    page_size: int = 8,
    total: int = 0,
    from_sa: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    for row in banned:
        uid = row["user_id"]
        name = row.get("first_name") or row.get("username") or str(uid)
        label = name if len(name) <= 28 else name[:25] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🔓 {label}",
                    callback_data=_cb("panel_unban", chat_id, str(uid)),
                ),
            ],
        )
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("◀️", callback_data=_cb("banned_page", chat_id, str(page - 1))),
        )
    if (page + 1) * page_size < total:
        nav.append(
            InlineKeyboardButton("▶️", callback_data=_cb("banned_page", chat_id, str(page + 1))),
        )
    if nav:
        rows.append(nav)
    back_action = _cb("sa_grp", chat_id) if from_sa else _cb("panel", chat_id)
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=back_action)])
    return InlineKeyboardMarkup(rows)


def global_banned_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for u in users[:20]:
        uid = u["telegram_id"]
        name = u.get("first_name") or u.get("username") or str(uid)
        label = name if len(name) <= 28 else name[:25] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    f"🔓 {label}",
                    callback_data=_cb("sa_unban_user", 0, str(uid)),
                ),
            ],
        )
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_panel"))])
    return InlineKeyboardMarkup(rows)


def sa_groups_picker(groups: list[dict], page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    start = page * page_size
    end = start + page_size
    page_groups = groups[start:end]
    rows = []
    for g in page_groups:
        title = g.get("title") or str(g["chat_id"])
        label = title if len(title) <= 35 else title[:32] + "…"
        auth = "✅" if g.get("is_authorized") else "🚫"
        rows.append(
            [
                InlineKeyboardButton(
                    f"{auth} {label}",
                    callback_data=_cb("sa_grp", g["chat_id"]),
                ),
            ],
        )
    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton("◀️", callback_data=_cb("sa_grps", 0, str(page - 1))),
        )
    if end < len(groups):
        nav.append(
            InlineKeyboardButton("▶️", callback_data=_cb("sa_grps", 0, str(page + 1))),
        )
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(i18n.BTN_BACK, callback_data=_cb("sa_panel"))])
    return InlineKeyboardMarkup(rows)


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
