"""Persian (Farsi) UI strings for gdoc bot."""

from __future__ import annotations

STRICTNESS_FA = {
    "low": "کم",
    "medium": "متوسط",
    "high": "زیاد",
}

ACTION_MODE_FA = {
    "delete_flag": "حذف پیام + ثبت در پنل",
    "keep_alert": "نگه‌داشتن پیام + هشدار به ادمین",
}

CLASSIFICATION_FA = {
    "SAFE": "ایمن",
    "SUSPECT": "مشکوک",
    "VIOLATION": "تخلف",
}

LAYER_FA = {
    "regex": "فیلتر محلی",
    "ai": "هوش مصنوعی",
    "none": "—",
}


def strictness_label(level: str) -> str:
    return STRICTNESS_FA.get(level, level)


def action_mode_label(mode: str) -> str:
    return ACTION_MODE_FA.get(mode, mode)


def classification_label(value: str) -> str:
    return CLASSIFICATION_FA.get(value.upper(), value)


def layer_label(value: str) -> str:
    return LAYER_FA.get(value, value)


def moderation_status(enabled: bool) -> str:
    return "✅ فعال" if enabled else "❌ غیرفعال"


def authorized_status(authorized: bool) -> str:
    return "✅ مجاز" if authorized else "🚫 غیرمجاز"


# --- Commands / welcome ---

MSG_START_SUPER = (
    "👋 به **gdoc** (دکتر گروه) خوش آمدید.\n"
    "شما مالک سیستم هستید.\n"
    "برای پنل کنترل سراسری از /superadmin استفاده کنید."
)

MSG_START_USER = (
    "👋 به **gdoc** (دکتر گروه) خوش آمدید.\n\n"
    "مرا به گروه اضافه کنید، به **ادمین** ارتقا دهید، "
    "سپس در گروه دستور /panel را بزنید."
)

MSG_PANEL_PRIVATE = "دستور /panel را داخل گروهی که ربات ادمین است ارسال کنید."
MSG_ACCESS_DENIED = "⛔ دسترسی مجاز نیست."
MSG_NOT_GROUP_ADMIN = "فقط ادمین‌های گروه به این پنل دسترسی دارند."
MSG_PROMOTE_BOT = "⚠️ لطفاً ربات را به **ادمین** ارتقا دهید تا moderation فعال شود."
MSG_GROUP_NOT_FOUND = "گروه یافت نشد. دوباره تلاش کنید."

MSG_HELP = (
    "**دستورات gdoc**\n"
    "/start — پیام خوش‌آمد\n"
    "/panel — پنل تنظیمات گروه (داخل گروه)\n"
    "/superadmin — پنل مالک سیستم\n"
    "/help — راهنما"
)

MSG_SUPER_PANEL = "🛡 **پنل کنترل مالک — gdoc**"


def format_group_panel_header(group: dict) -> str:
    title = group.get("title") or "گروه"
    enabled = "✅ فعال" if group.get("moderation_enabled") else "⏸ متوقف"
    authorized = authorized_status(bool(group.get("is_authorized")))
    strictness = strictness_label(group.get("strictness", "medium"))
    threshold = group.get("warning_threshold", 3)
    return (
        f"⚙️ **پنل مدیریت گروه**\n"
        f"📌 {title}\n"
        f"وضعیت moderation: {enabled}\n"
        f"وضعیت ربات: {authorized}\n"
        f"سطح سختی: **{strictness}**\n"
        f"اخطار تا بن: **{threshold}**"
    )


# --- Inline keyboard buttons ---

BTN_RULES = "📝 قوانین سفارشی"
BTN_STRICTNESS = "🎚 سطح سختی"
BTN_ACTION = "⚡ عملکرد پیام مشکوک"
BTN_THRESHOLD = "⚠️ آستانه اخطار"
BTN_MODERATION = "🤖 moderation"
BTN_BLACKLIST = "🚫 لیست سیاه"
BTN_AUDIT = "📋 گزارش تخلفات"
BTN_REFRESH = "🔄 بروزرسانی"
BTN_BACK = "⬅️ بازگشت"

BTN_BL_ADD_KW = "➕ افزودن کلمه"
BTN_BL_ADD_RX = "➕ افزودن Regex"
BTN_BL_REMOVE = "➖ حذف الگو"

BTN_SA_STATS = "📊 آمار سراسری"
BTN_SA_GROUPS = "👥 همه گروه‌ها"
BTN_SA_APIKEY = "🔑 تغییر کلید AI"
BTN_SA_AUTH = "✅ مجاز کردن گروه"
BTN_SA_BAN_GROUP = "🚫 مسدود کردن گروه"
BTN_SA_BAN_USER = "🔨 بن کاربر/ادمین"
BTN_SA_AUDIT = "📋 گزارش سراسری"

# --- Callback prompts ---

PROMPT_STRICTNESS = "سطح سختی moderation را انتخاب کنید:"
PROMPT_ACTION = "برخورد با پیام‌های مشکوک:"
PROMPT_THRESHOLD = "حداکثر تعداد اخطار قبل از بن خودکار:"
PROMPT_RULES = (
    "قوانین سفارشی گروه را به‌صورت یک پیام متنی ارسال کنید.\n\n"
    "قوانین فعلی:\n{preview}"
)
PROMPT_RULES_NONE = "(تعریف نشده)"
PROMPT_BL_KEYWORD = "کلمه یا عبارت را برای لیست سیاه ارسال کنید (بدون حساسیت به حروف)."
PROMPT_BL_REGEX = "الگوی Regex را برای لیست سیاه ارسال کنید."
PROMPT_BL_REMOVE = "متن دقیق الگویی که می‌خواهید حذف شود را ارسال کنید."

PROMPT_SA_APIKEY = "کلید API جدید OpenAI/Gemini را به‌صورت پیام متنی ارسال کنید."
PROMPT_SA_AUTH = "شناسه عددی گروه را برای مجاز کردن ارسال کنید (مثلاً -1001234567890)."
PROMPT_SA_BAN_GROUP = "شناسه عددی گروه را برای مسدود کردن ارسال کنید."
PROMPT_SA_BAN_USER = "شناسه عددی کاربر تلگرام را برای بن سراسری ارسال کنید."

# --- Blacklist / audit ---

def format_blacklist_header(lines: list[str]) -> str:
    body = "\n".join(lines) if lines else "_هنوز الگویی ثبت نشده._"
    return f"🚫 **الگوهای لیست سیاه**\n\n{body}"


def format_blacklist_item(pattern: str, is_regex: bool) -> str:
    kind = "regex" if is_regex else "کلمه"
    return f"• [{kind}] `{pattern}`"


MSG_AUDIT_EMPTY = "📋 هنوز پیام پرچم‌گذاری‌شده‌ای ثبت نشده."

def format_audit_log(entries: list[dict]) -> str:
    lines = ["📋 **گزارش اخیر تخلفات**\n"]
    for entry in entries:
        user_label = entry.get("username") or str(entry.get("user_id"))
        text_preview = (entry.get("message_text") or "")[:80]
        cls = classification_label(str(entry.get("classification", "")))
        layer = layer_label(str(entry.get("layer", "")))
        lines.append(
            f"• **{user_label}** — {cls}\n"
            f"  _{text_preview}_\n"
            f"  دلیل: {entry.get('reason')}\n"
            f"  لایه: {layer} | اقدام: {entry.get('action_taken')}\n",
        )
    return "\n".join(lines)


def format_global_stats(stats: dict) -> str:
    groups_list = "\n".join(
        f"• {g.get('title', g['chat_id'])} ({g.get('messages_processed', 0)} پیام)"
        for g in stats.get("groups", [])[:15]
    ) or "_گروه فعالی وجود ندارد_"
    return (
        "📊 **آمار سراسری**\n\n"
        f"گروه‌های فعال: **{stats['active_groups']}**\n"
        f"کل پیام‌های پردازش‌شده: **{stats['total_messages']}**\n"
        f"ادمین‌های ثبت‌شده: **{stats['active_admins']}**\n\n"
        f"**گروه‌ها:**\n{groups_list}"
    )


def format_all_groups(groups: list[dict]) -> str:
    lines = ["👥 **فهرست همه گروه‌ها**\n"]
    for g in groups[:25]:
        auth = "✅" if g.get("is_authorized") else "🚫"
        lines.append(
            f"{auth} `{g['chat_id']}` — {g.get('title', 'نامشخص')} "
            f"({g.get('messages_processed', 0)} پیام)",
        )
    return "\n".join(lines)


def format_global_audit(entries: list[dict]) -> str:
    if not entries:
        return "گزارشی ثبت نشده."
    lines = ["📋 **گزارش سراسری تخلفات**\n"]
    for entry in entries:
        cls = classification_label(str(entry.get("classification", "")))
        lines.append(
            f"• گروه `{entry.get('chat_id')}` — "
            f"کاربر {entry.get('user_id')} — {cls}\n"
            f"  {(entry.get('message_text') or '')[:60]}\n",
        )
    return "\n".join(lines)


# --- Pending input confirmations ---

MSG_RULES_UPDATED = "✅ قوانین سفارشی ذخیره شد."
MSG_KEYWORD_ADDED = "✅ کلمه اضافه شد: `{text}`"
MSG_REGEX_ADDED = "✅ Regex اضافه شد: `{text}`"
MSG_PATTERN_REMOVED = "✅ الگو حذف شد: `{text}`"
MSG_APIKEY_UPDATED = "✅ کلید API سراسری بروزرسانی شد."
MSG_GROUP_AUTHORIZED = "✅ گروه `{chat_id}` مجاز شد."
MSG_GROUP_BANNED = "🚫 گروه `{chat_id}` مسدود شد."
MSG_USER_BANNED = "🔨 کاربر `{user_id}` به‌صورت سراسری بن شد."
MSG_INVALID_CHAT_ID = "شناسه گروه نامعتبر است."
MSG_INVALID_USER_ID = "شناسه کاربر نامعتبر است."

# --- Moderation alerts ---

def format_moderation_alert(
    user_name: str,
    username: str | None,
    classification: str,
    reason: str,
    text: str,
) -> str:
    uname = f"@{username}" if username else "ندارد"
    cls = classification_label(classification)
    return (
        f"⚠️ **هشدار moderation**\n"
        f"کاربر: {user_name} ({uname})\n"
        f"طبقه‌بندی: {cls}\n"
        f"دلیل: {reason}\n"
        f"پیام: _{text[:200]}_"
    )


def format_cross_group_alert(
    user_label: str,
    source_title: str,
    reason: str,
) -> str:
    return (
        f"🚨 **هشدار بین‌گروهی**\n"
        f"توجه: کاربر {user_label} اخیراً در گروه دیگری "
        f"({source_title}) به‌دلیل [{reason}] بن شد.\n"
        f"این کاربر را زیر نظر بگیرید."
    )
