"""Persian (Farsi) UI strings for gdoc bot."""

from __future__ import annotations

from datetime import datetime, timezone

from ai import AIClassifier
from config import Config

STRICTNESS_FA = {
    "low": "کم",
    "medium": "متوسط",
    "high": "زیاد",
}

ACTION_MODE_FA = {
    "delete_flag": "حذف خودکار + اخطار",
    "keep_alert": "بررسی ادمین در پیوی (پیش‌فرض)",
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


def escape_md(text: str) -> str:
    """Escape Telegram legacy Markdown special characters in user content."""
    if not text:
        return ""
    for ch in ("\\", "_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def moderation_status(enabled: bool) -> str:
    return "✅ فعال" if enabled else "❌ غیرفعال"


def authorized_status(authorized: bool) -> str:
    return "✅ مجاز" if authorized else "🚫 غیرمجاز"


# --- Commands / welcome ---

MSG_START_SUPER = (
    "👋 به **gdoc** (دکتر گروه) خوش آمدید.\n"
    "شما مالک سیستم هستید.\n"
    "برای پنل کنترل سراسری از /superadmin استفاده کنید.\n"
    "از بخش **همه گروه‌ها** می‌توانید گروه را انتخاب و تنظیماتش را مدیریت کنید.\n\n"
    "⚙️ ابتدا از پنل، **تنظیمات AI** (پرووایدر، کلید API و مدل) را پیکربندی کنید."
)

MSG_START_USER = (
    "👋 به **gdoc** (دکتر گروه) خوش آمدید.\n\n"
    "مرا به گروه اضافه کنید، به **ادمین** ارتقا دهید، "
    "سپس در گروه دستور /panel را بزنید.\n\n"
    f"🎁 **{Config.ADMIN_TRIAL_DAYS} روز** استفاده رایگان برای ادمین‌های گروه.\n"
    f"ربات رسمی: [@{Config.OFFICIAL_BOT_USERNAME}](https://t.me/{Config.OFFICIAL_BOT_USERNAME})"
)

MSG_SUBSCRIPTION_EXPIRED = (
    "⏳ **دوره استفاده شما به پایان رسیده است.**\n\n"
    f"برای تمدید حساب با [@{Config.OWNER_USERNAME}](https://t.me/{Config.OWNER_USERNAME}) "
    "در تلگرام تماس بگیرید."
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
    "/superadmin — پنل مالک (چت خصوصی؛ انتخاب و مدیریت گروه‌ها)\n"
    "/help — راهنما\n\n"
    "**دستورات مدیریتی (ریپلای به پیام کاربر):**\n"
    "`ban` — بن + حذف پیام‌های ۴۸ ساعت اخیر\n"
    "`kick` — اخراج از گروه\n"
    "`mute` — سکوت کاربر\n"
    "`unmute` — لغو سکوت\n"
    "`warn` — ثبت اخطار\n"
    "`del` — حذف پیام\n"
    "`purge` — حذف پیام‌ها + اخراج موقت"
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

BTN_RULES = "📝 قوانین گروه"
BTN_RULES_BAN = "🔨 قوانین بن مستقیم"
BTN_RULES_SUSPECT = "🔍 قوانین مشکوک"
BTN_STRICTNESS = "🎚 سطح سختی"
BTN_ACTION = "⚡ عملکرد پیام مشکوک"
BTN_THRESHOLD = "⚠️ آستانه اخطار"
BTN_MODERATION = "🤖 moderation"
BTN_BLACKLIST = "🚫 لیست سیاه"
BTN_AUDIT = "📋 گزارش تخلفات"
BTN_BANNED = "🔨 کاربران بن‌شده"
BTN_STATS = "📊 آمار پیام‌ها"
BTN_REFRESH = "🔄 بروزرسانی"
BTN_BACK = "⬅️ بازگشت"

BTN_BL_ADD_KW = "➕ افزودن کلمه"
BTN_BL_ADD_RX = "➕ افزودن Regex"
BTN_BL_REMOVE = "➖ حذف الگو"

BTN_SA_STATS = "📊 آمار سراسری"
BTN_SA_GROUPS = "👥 همه گروه‌ها"
BTN_SA_ADMINS = "👤 مدیریت ادمین‌ها"
BTN_SA_RENEW = "🔄 تمدید اشتراک ادمین"
BTN_SA_AI = "🤖 تنظیمات AI"
BTN_SA_WEBHOOK = "🌐 Webhook / SSL"
BTN_SA_APIKEY = "🔑 کلید API"
BTN_SA_PROVIDER = "🏷 پرووایدر AI"
BTN_SA_BASEURL = "🔗 Base URL"
BTN_SA_MODEL = "📦 انتخاب مدل"
BTN_SA_AUTH = "✅ مجاز کردن گروه"
BTN_SA_BAN_GROUP = "🚫 مسدود کردن گروه"
BTN_SA_BAN_USER = "🔨 بن کاربر/ادمین"
BTN_SA_BANNED = "🚷 کاربران بن سراسری"
BTN_SA_AUDIT = "📋 گزارش سراسری"
BTN_SA_GROUPS_BACK = "⬅️ بازگشت به فهرست گروه‌ها"

BTN_MOD_FORGIVE = "✅ بخشیدن (حذف اخطار)"
BTN_MOD_BAN = "🔨 بن کردن"
BTN_MOD_UNBAN = "🔓 آزاد کردن"
BTN_MOD_RESTORE = "↩️ بازگرداندن پیام"

BTN_REVIEW_HARM = "⚠️ مضر — اخطار بده"
BTN_REVIEW_SAFE = "✅ غیرمضر — نادیده بگیر"
BTN_REVIEW_DELETE = "🗑 حذف پیام"

BTN_WH_POLLING = "📡 حالت Polling (پیش‌فرض)"
BTN_WH_MANUAL = "🔗 تغییر URL دستی"

PROVIDER_OPENAI = "OpenAI"
PROVIDER_GEMINI = "Google Gemini"
PROVIDER_COMPAT = "سازگار با OpenAI"

# --- Callback prompts ---

PROMPT_STRICTNESS = "سطح سختی moderation را انتخاب کنید:"
PROMPT_ACTION = "برخورد با پیام‌های مشکوک:\n_پیش‌فرض: پیام حذف نمی‌شود و فقط در پیوی ادمین بررسی می‌شود._"
PROMPT_THRESHOLD = "حداکثر تعداد اخطار قبل از بن خودکار:"
PROMPT_RULES = (
    "نوع قوانین را انتخاب کنید:\n\n"
    "🔨 **بن مستقیم** — نقض = تخلف و بن فوری\n"
    "🔍 **مشکوک** — نقض = پیام مشکوک (اخطار بر اساس تنظیمات)"
)
PROMPT_RULES_BAN = (
    "قوانین **بن مستقیم** را ارسال کنید.\n"
    "نقض هر کدام = تخلف و بن فوری کاربر.\n"
    "می‌توانید همین‌جا در گروه یا در چت خصوصی با ربات بنویسید.\n\n"
    "قوانین فعلی:\n{preview}"
)
PROMPT_RULES_SUSPECT = (
    "قوانین **مشکوک** را ارسال کنید.\n"
    "نقض هر کدام = پیام مشکوک (نه بن مستقیم).\n"
    "می‌توانید همین‌جا در گروه یا در چت خصوصی با ربات بنویسید.\n\n"
    "قوانین فعلی:\n{preview}"
)
PROMPT_RULES_NONE = "(تعریف نشده)"
PROMPT_BL_KEYWORD = (
    "کلمه یا عبارت را برای لیست سیاه ارسال کنید (بدون حساسیت به حروف).\n"
    "می‌توانید همین‌جا در گروه یا در چت خصوصی با ربات بنویسید."
)
PROMPT_BL_REGEX = (
    "الگوی Regex را برای لیست سیاه ارسال کنید.\n"
    "می‌توانید همین‌جا در گروه یا در چت خصوصی با ربات بنویسید."
)
PROMPT_BL_REMOVE = (
    "متن دقیق الگویی که می‌خواهید حذف شود را ارسال کنید.\n"
    "می‌توانید همین‌جا در گروه یا در چت خصوصی با ربات بنویسید."
)

PROMPT_SA_APIKEY = "کلید API پرووایدر را به‌صورت پیام متنی ارسال کنید."
PROMPT_SA_BASEURL = (
    "Base URL پرووایدر را ارسال کنید.\n"
    "مثال OpenAI: https://api.openai.com/v1\n"
    "مثال Gemini: https://generativelanguage.googleapis.com/v1beta\n"
    "برای پرووایderهای سازگار با OpenAI، آدرس API خود را وارد کنید."
)
PROMPT_SA_WEBHOOK_URL = "آدرس عمومی HTTPS وب‌هوک را ارسال کنید (مثلاً https://bot.example.com)."
PROMPT_SA_AUTH = "شناسه عددی گروه را برای مجاز کردن ارسال کنید (مثلاً -1001234567890)."
PROMPT_SA_BAN_GROUP = "شناسه عددی گروه را برای مسدود کردن ارسال کنید."
PROMPT_SA_BAN_USER = "شناسه عددی کاربر تلگرام را برای بن سراسری ارسال کنید."
PROMPT_SA_RENEW = (
    "شناسه عددی ادمینی که می‌خواهید اشتراکش را تمدید کنید ارسال کنید.\n"
    f"({Config.ADMIN_TRIAL_DAYS} روز به اشتراک فعلی اضافه می‌شود.)"
)

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
        user_label = escape_md(entry.get("username") or str(entry.get("user_id")))
        text_preview = escape_md((entry.get("message_text") or "")[:80])
        cls = classification_label(str(entry.get("classification", "")))
        layer = layer_label(str(entry.get("layer", "")))
        reason = escape_md(str(entry.get("reason") or ""))
        action = escape_md(str(entry.get("action_taken") or ""))
        lines.append(
            f"• **{user_label}** — {cls}\n"
            f"  _{text_preview}_\n"
            f"  دلیل: {reason}\n"
            f"  لایه: {layer} | اقدام: {action}\n",
        )
    return "\n".join(lines)


def format_global_stats(stats: dict) -> str:
    groups_list = "\n".join(
        f"• {g.get('title', g['chat_id'])} — "
        f"هفته: {g.get('messages_week', 0)} | "
        f"ماه: {g.get('messages_month', 0)} | "
        f"کل: {g.get('messages_processed', 0)}"
        for g in stats.get("groups", [])[:15]
    ) or "_گروه فعالی وجود ندارد_"
    return (
        "📊 **آمار سراسری**\n\n"
        f"گروه‌های فعال: **{stats['active_groups']}**\n"
        f"کل پیام‌های پردازش‌شده: **{stats['total_messages']}**\n"
        f"ادمین‌های ثبت‌شده: **{stats['active_admins']}**\n\n"
        f"**گروه‌ها (هفته / ماه / کل):**\n{groups_list}"
    )


def format_all_groups(groups: list[dict]) -> str:
    lines = ["👥 **فهرست همه گروه‌ها**\n"]
    for g in groups[:25]:
        auth = "✅" if g.get("is_authorized") else "🚫"
        lines.append(
            f"{auth} `{g['chat_id']}` — {g.get('title', 'نامشخص')}\n"
            f"  هفته: {g.get('messages_week', 0)} | "
            f"ماه: {g.get('messages_month', 0)} | "
            f"کل: {g.get('messages_processed', 0)}",
        )
    return "\n".join(lines)


def format_group_message_stats(group: dict, stats: dict) -> str:
    title = group.get("title") or "گروه"
    return (
        f"📊 **آمار پیام‌های گروه**\n"
        f"📌 {title}\n\n"
        f"۷ روز اخیر: **{stats['week']}** پیام\n"
        f"۳۰ روز اخیر: **{stats['month']}** پیام\n"
        f"کل پردازش‌شده: **{stats['total']}** پیام\n\n"
        "_هزینه سرویس بر اساس تعداد پیام‌های پردازش‌شده محاسبه می‌شود._"
    )


def format_registered_admins(admins: list[dict]) -> str:
    if not admins:
        return "👤 **مدیریت ادمین‌ها**\n\n_هنوز ادمینی ثبت نشده._"
    lines = ["👤 **مدیریت ادمین‌ها**\n"]
    now = datetime.now(timezone.utc)
    for admin in admins[:30]:
        expires_label = "—"
        if admin.get("is_super_admin"):
            status = "♾️ سوپرادمین"
        else:
            expires_raw = admin.get("subscription_expires_at")
            if expires_raw:
                expires = datetime.fromisoformat(expires_raw)
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                status = "✅ فعال" if expires > now else "⏳ منقضی"
                expires_label = expires.strftime("%Y-%m-%d")
            else:
                status = "⏳ بدون اشتراک"
        name = admin.get("first_name") or admin.get("username") or str(admin["telegram_id"])
        uname = f"@{admin['username']}" if admin.get("username") else ""
        lines.append(
            f"• **{name}** {uname}\n"
            f"  ID: `{admin['telegram_id']}` | {status} | "
            f"انقضا: {expires_label} | "
            f"گروه‌ها: {admin.get('group_count', 0)}",
        )
    return "\n".join(lines)


def format_global_audit(entries: list[dict]) -> str:
    if not entries:
        return "گزارشی ثبت نشده."
    lines = ["📋 **گزارش سراسری تخلفات**\n"]
    for entry in entries:
        cls = classification_label(str(entry.get("classification", "")))
        preview = escape_md((entry.get("message_text") or "")[:60])
        reason = escape_md(str(entry.get("reason") or ""))
        action = escape_md(str(entry.get("action_taken") or ""))
        lines.append(
            f"• گروه `{entry.get('chat_id')}` — "
            f"کاربر {entry.get('user_id')} — {cls}\n"
            f"  {preview}\n"
            f"  دلیل: {reason} | اقدام: {action}\n",
        )
    return "\n".join(lines)


def format_banned_users_list(
    banned: list[dict],
    *,
    total: int,
    page: int,
    page_size: int,
) -> str:
    if not banned:
        return "🔨 **کاربران بن‌شده**\n\n_هیچ کاربر بن‌شده‌ای ثبت نشده._"
    lines = [f"🔨 **کاربران بن‌شده** ({total} نفر)\n"]
    start = page * page_size
    for idx, row in enumerate(banned, start=start + 1):
        name = escape_md(row.get("first_name") or row.get("username") or str(row["user_id"]))
        uname = f"@{row['username']}" if row.get("username") else ""
        reason = escape_md(row.get("ban_reason") or "—")
        warns = row.get("warning_count", 0)
        lines.append(
            f"{idx}. **{name}** {uname}\n"
            f"   ID: `{row['user_id']}` | اخطار: {warns}\n"
            f"   دلیل: {reason}\n",
        )
    return "\n".join(lines)


def format_global_banned_users(users: list[dict]) -> str:
    if not users:
        return "🚷 **کاربران بن سراسری**\n\n_هیچ کاربری بن سراسری نشده._"
    lines = ["🚷 **کاربران بن سراسری**\n"]
    for u in users:
        name = escape_md(u.get("first_name") or u.get("username") or str(u["telegram_id"]))
        uname = f"@{u['username']}" if u.get("username") else ""
        lines.append(f"• **{name}** {uname} — ID: `{u['telegram_id']}`")
    return "\n".join(lines)


def format_admin_review_alert(
    group_title: str,
    user_name: str,
    username: str | None,
    classification: str,
    reason: str,
    text: str,
) -> str:
    uname = f"@{escape_md(username)}" if username else "ندارد"
    cls = classification_label(classification)
    return (
        f"🔍 **بررسی پیام مشکوک**\n"
        f"گروه: {escape_md(group_title)}\n"
        f"کاربر: {escape_md(user_name)} ({uname})\n"
        f"طبقه‌بندی: **{cls}**\n"
        f"دلیل AI: {escape_md(reason)}\n\n"
        f"پیام:\n_{escape_md(text[:500])}_\n\n"
        f"_پیام در گروه حذف نشده. لطفاً مضر یا غیرمضر بودن را مشخص کنید._"
    )


def format_group_delete_notice(
    user_name: str,
    username: str | None,
    reason: str,
    message_preview: str,
) -> str:
    uname = f"@{escape_md(username)}" if username else "ندارد"
    preview = escape_md(message_preview[:120]) if message_preview else "—"
    return (
        f"🗑 **پیام حذف شد**\n"
        f"کاربر: {escape_md(user_name)} ({uname})\n"
        f"دلیل: {escape_md(reason)}\n"
        f"متن: _{preview}_\n\n"
        f"_ادمین می‌تواند پیام را بازگرداند یا اخطار را ببخشد._"
    )


def format_group_warning_notice(
    user_name: str,
    username: str | None,
    reason: str,
    warn_count: int,
    threshold: int,
    deleted: bool,
) -> str:
    uname = f"@{escape_md(username)}" if username else "ندارد"
    delete_line = "پیام شما حذف شد." if deleted else "پیام شما نگه داشته شد."
    return (
        f"⚠️ **اخطار moderation**\n"
        f"کاربر: {escape_md(user_name)} ({uname})\n"
        f"{delete_line}\n"
        f"دلیل: {escape_md(reason)}\n"
        f"تعداد اخطار: **{warn_count}** از **{threshold}**\n\n"
        f"_فقط ادمین‌های گروه می‌توانند بخشیدن یا بن کنند._"
    )


def format_group_ban_notice(
    user_name: str,
    username: str | None,
    warn_count: int,
    reasons: list[str],
) -> str:
    uname = f"@{escape_md(username)}" if username else "ندارد"
    reason_lines = "\n".join(f"  • {escape_md(r)}" for r in reasons[:5]) or "  • آستانه اخطار"
    return (
        f"🔨 **کاربر بن شد**\n"
        f"کاربر: {escape_md(user_name)} ({uname})\n"
        f"پس از **{warn_count}** اخطار از گروه اخراج شد.\n\n"
        f"**دلایل تخلفات:**\n{reason_lines}\n\n"
        f"_فقط ادمین‌های گروه می‌توانند کاربر را آزاد کنند._"
    )


MSG_MOD_FORGIVEN = "✅ اخطارهای {user} توسط ادمین بخشیده شد."
MSG_MOD_BANNED = "🔨 {user} توسط ادمین بن شد."
MSG_MOD_UNBANNED = "🔓 {user} توسط ادمین آزاد شد."
MSG_MOD_RESTORED = "↩️ پیام {user} در گروه بازگردانده شد."
MSG_MOD_REVIEW_HARM = "⚠️ پیام مضر تشخیص داده شد — اخطار ثبت شد."
MSG_MOD_REVIEW_SAFE = "✅ پیام غیرمضر تشخیص داده شد — نادیده گرفته شد."
MSG_MOD_REVIEW_DONE = "این بررسی قبلاً انجام شده است."
MSG_MOD_NOT_GROUP_ADMIN = "⛔ فقط ادمین‌های گروه می‌توانند این کار را انجام دهند."
MSG_MOD_ALREADY_DONE = "این اقدام قبلاً انجام شده است."
MSG_SA_SELECT_GROUP = "👥 **گروه را برای مدیریت انتخاب کنید:**"
MSG_SA_NO_GROUPS = "هنوز گروهی ثبت نشده."


# --- Pending input confirmations ---

MSG_RULES_UPDATED = "✅ قوانین بن مستقیم ذخیره شد."
MSG_RULES_SUSPECT_UPDATED = "✅ قوانین مشکوک ذخیره شد."
MSG_KEYWORD_ADDED = "✅ کلمه اضافه شد: `{text}`"
MSG_REGEX_ADDED = "✅ Regex اضافه شد: `{text}`"
MSG_PATTERN_REMOVED = "✅ الگو حذف شد: `{text}`"
MSG_APIKEY_UPDATED = "✅ کلید API بروزرسانی شد."
MSG_PROVIDER_UPDATED = "✅ پرووایدر AI به **{provider}** تغییر کرد."
MSG_BASEURL_UPDATED = "✅ Base URL ذخیره شد: `{url}`"
MSG_MODEL_UPDATED = "✅ مدل AI به `{model}` تغییر کرد."
MSG_MODEL_LIST_ERROR = "❌ خطا در دریافت لیست مدل‌ها:\n{error}"
MSG_MODEL_LIST_EMPTY = "❌ مدلی یافت نشد. ابتدا کلید API و Base URL را تنظیم کنید."
MSG_AI_NOT_CONFIGURED = "⚠️ AI هنوز پیکربندی نشده. کلید API و مدل را تنظیم کنید."
MSG_WEBHOOK_POLLING = "✅ حالت Polling فعال شد. سرویس را ری‌استارت کنید:\n`sudo systemctl restart tg_moderator`"
MSG_WEBHOOK_URL_SAVED = "✅ URL وب‌هوک ذخیره شد. سرویس را ری‌استارت کنید:\n`sudo systemctl restart tg_moderator`"
MSG_WEBHOOK_INVALID_URL = "آدرس URL نامعتبر است. باید با https:// شروع شود."
MSG_GROUP_AUTHORIZED = "✅ گروه `{chat_id}` مجاز شد."
MSG_GROUP_BANNED = "🚫 گروه `{chat_id}` مسدود شد."
MSG_USER_BANNED = "🔨 کاربر `{user_id}` به‌صورت سراسری بن شد."
MSG_USER_UNBANNED = "🔓 بن سراسری کاربر `{user_id}` برداشته شد."
MSG_ADMIN_RENEWED = (
    "✅ اشتراک ادمین `{user_id}` تمدید شد.\n"
    "انقضای جدید: **{expires}** ({days} روز)"
)
MSG_INVALID_CHAT_ID = "شناسه گروه نامعتبر است."
MSG_INVALID_USER_ID = "شناسه کاربر نامعتبر است."
MSG_PENDING_WRONG_GROUP = "این تنظیم برای گروه دیگری است. دوباره از پنل همان گروه اقدام کنید."

# --- Admin reply commands ---

MSG_MODCMD_NO_TARGET = "پیام معتبری برای اقدام یافت نشد."
MSG_MODCMD_SELF = "نمی‌توانید روی خودتان این کار را انجام دهید."
MSG_MODCMD_PROTECTED = "⛔ ادمین اصلی/ادمین‌های گروه قابل اقدام نیستند."
MSG_MODCMD_NO_PERMISSION = "ربات دسترسی لازم (بن/حذف/محدودسازی) را ندارد."
MSG_MODCMD_RATE_LIMIT = "تلگرام محدودیت سرعت دارد. {seconds} ثانیه بعد دوباره تلاش کنید."
MSG_MODCMD_FAILED = "عملیات انجام نشد: {error}"
MSG_MODCMD_BAN = "🔨 {user} بن شد و پیام‌های اخیرش حذف شد."
MSG_MODCMD_KICK = "👢 {user} از گروه اخراج شد."
MSG_MODCMD_MUTE = "🔇 {user} سکوت شد."
MSG_MODCMD_UNMUTE = "🔊 سکوت {user} برداشته شد."
MSG_MODCMD_WARN = "⚠️ به {user} اخطار داده شد. (تعداد: {count})"
MSG_MODCMD_WARN_BAN = "🔨 {user} پس از {count} اخطار بن شد."
MSG_MODCMD_DEL = "🗑 پیام حذف شد."
MSG_MODCMD_DEL_REASON = "دلیل: حذف دستی توسط ادمین"
MSG_MODCMD_PURGE = "🧹 پیام‌های {user} پاک شد و از گروه اخراج شد."


def provider_label(provider: str) -> str:
    labels = {
        "openai": PROVIDER_OPENAI,
        "gemini": PROVIDER_GEMINI,
        "openai_compat": PROVIDER_COMPAT,
    }
    return labels.get(provider, provider)


def format_ai_settings(settings: dict, configured: bool) -> str:
    provider = provider_label(settings.get("provider", "openai"))
    model = settings.get("model") or "—"
    base_url = settings.get("base_url") or AIClassifier.get_default_base_url(settings.get("provider", "openai"))
    api_status = "✅ تنظیم شده" if settings.get("api_key") else "❌ تنظیم نشده"
    status = "✅ آماده" if configured else "⚠️ ناقص"
    return (
        f"🤖 **تنظیمات AI**\n\n"
        f"وضعیت: {status}\n"
        f"پرووایدر: **{provider}**\n"
        f"Base URL: `{base_url}`\n"
        f"مدل: `{model}`\n"
        f"کلید API: {api_status}"
    )


def format_webhook_settings(settings: dict) -> str:
    use_webhook = settings.get("use_webhook") == "true"
    mode = "Webhook" if use_webhook else "Polling"
    url = settings.get("webhook_url") or "—"
    return (
        f"🌐 **تنظیمات Webhook**\n\n"
        f"حالت: **{mode}**\n"
        f"URL: `{url}`\n\n"
        f"SSL و nginx در زمان نصب (با انتخاب دامنه) پیکربندی می‌شود."
    )

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
